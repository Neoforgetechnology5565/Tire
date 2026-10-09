"""Drive the real UI in Chromium (WebGL via SwiftShader). Skipped where Playwright/Chromium are unavailable."""
import os
import threading
from pathlib import Path

import numpy as np
import pytest

pw = pytest.importorskip("playwright.sync_api")
from treadlidar.ui import server as ui_server  # noqa: E402

CHROMIUM = os.environ.get("TREADLIDAR_TEST_CHROMIUM") or next((p for p in ("/opt/pw-browsers/chromium",) if Path(p).exists()), None)
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"]


@pytest.fixture(scope="module")
def srv():
    ui_server.reset_session()
    s = ui_server.create_server()
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s
    s.shutdown()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=CHROMIUM, args=ARGS) if CHROMIUM else p.chromium.launch(args=ARGS)
        except Exception as e:  # no browser installed
            pytest.skip(f"Chromium not available: {e}")
        yield b
        b.close()


@pytest.fixture()
def page(browser, srv):
    ui_server.reset_session()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    pg = ctx.new_page()
    pg.errors = []
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: pg.errors.append("PAGEERROR " + str(e)))
    pg.goto(srv.url)
    pg.wait_for_function("window.__ready===true")
    yield pg
    ctx.close()


def load_demo(pg, label="Load demo scan"):
    pg.click(f"text={label}")
    pg.wait_for_selector(".scan-card")


def run_analysis(pg):
    pg.click("text=Continue to tread analysis")
    pg.get_by_role("button", name="Run analysis").first.click()
    pg.wait_for_selector(".tile", timeout=90000)


def test_welcome_screen_and_clean_console(page):
    assert page.locator("h1").inner_text().startswith("Measure tire tread depth")
    for t in ("Browse files…", "Load demo scan", "Load demo wheel"):
        assert page.get_by_role("button", name=t).count() == 1
    assert page.locator("#rail .step").count() == 12                       # 10 workflow steps + 2 tools
    assert page.errors == []


def test_empty_state_highlights_step_one(page):
    cur = page.locator('#rail .step[aria-current="step"] .lbl').all_inner_texts()
    assert cur == ["Load scan"]
    assert "Step 1 of 10" in page.locator("#topbar").inner_text()


def test_demo_flow_load_analyse_and_measure(page):
    load_demo(page)
    assert "SIMULATED DATA" in page.locator("#topbar").inner_text()          # the data origin is never hidden
    page.wait_for_timeout(1200)
    run_analysis(page)
    tiles = page.locator(".tile").all_inner_texts()
    mean = [t for t in tiles if t.startswith("Mean depth")][0]
    val = float(mean.split("\n")[1].replace("mm", ""))
    assert 7.5 < val < 8.6
    for tab in ("Surface", "Grooves", "Density"):
        page.click(f'role=tab[name="{tab}"]')
        page.wait_for_timeout(1200)
    assert page.locator("text=Can the sensor resolve each groove?").count() == 1
    page.click("text=Select area")
    page.wait_for_selector("canvas")
    page.click('button:has-text("Groove centres")')
    page.wait_for_function("document.querySelectorAll('.scan-card').length>=4", timeout=20000)
    depths = [float(x.split("\n")[0]) for x in page.locator(".scan-card b.num").all_inner_texts()]
    assert len(depths) == 4 and all(6.0 < d < 10.0 for d in depths)
    assert page.evaluate("App.State.pins.length") == 4
    assert page.errors == []


def test_webgl_preview_is_not_blank(page):
    load_demo(page)
    page.wait_for_function("document.querySelector('.pane canvas') && document.querySelector('.pane .chip')", timeout=20000)
    page.wait_for_timeout(1500)
    shot = page.locator(".pane").first.screenshot()
    from PIL import Image  # noqa: WPS433
    import io
    arr = np.asarray(Image.open(io.BytesIO(shot)).convert("L"), float)
    assert arr.std() > 12                                                   # something is drawn (not a flat colour)


def test_accuracy_locks_real_for_simulated_data(page):
    load_demo(page)
    page.click("nav >> text=Accuracy")
    real = page.get_by_role("button", name="Real", exact=True)
    assert real.is_disabled()
    assert page.locator("text=so “Real” is locked").count() == 1


def test_accuracy_run_gives_not_assessed(page):
    for _ in range(2):
        page.click("text=Load demo scan") if page.locator("text=Load demo scan").count() else page.get_by_role("button", name="Demo scan").click()
        page.wait_for_selector(".scan-card")
        page.wait_for_timeout(300)
    page.get_by_role("button", name="Demo scan").click()
    page.wait_for_function("document.querySelectorAll('.scan-card').length>=3")
    page.click("nav >> text=Accuracy")
    page.get_by_role("button", name="Demo readings").click()
    page.get_by_role("button", name="Simulated", exact=True).click()
    page.get_by_role("button", name="Run validation").click()
    page.wait_for_function("document.body.innerText.includes('Paired measurements')", timeout=240000)
    body = page.locator("#view").inner_text()
    assert "Not assessed" in body and "origin: simulated" in body
    assert "Result A" not in body and "Result B" not in body


def test_theme_toggle_persists_across_reload(page, srv):
    page.get_by_role("button", name="Toggle light/dark theme").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.reload()
    page.wait_for_function("window.__ready===true")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"


def test_file_browser_loads_a_chosen_file(page, tmp_path):
    pts = np.random.default_rng(0).uniform(-1, 1, (2000, 3)).astype(np.float32)
    np.save(tmp_path / "myscan.npy", pts)
    page.get_by_role("button", name="Browse files…").click()
    page.wait_for_selector(".modal")
    page.fill('input[aria-label="Folder path"]', str(tmp_path))
    page.keyboard.press("Enter")
    page.wait_for_selector("text=myscan.npy")
    page.click("text=myscan.npy")
    page.get_by_role("button", name="Add 1 file").click()
    page.wait_for_selector(".scan-card")
    assert page.locator(".scan-card .nm").inner_text() == "myscan"
    assert page.locator(".scan-card .badge").inner_text() == "REAL"          # not marked simulated
    assert "Real data" in page.locator("#topbar").inner_text()


def test_fulltire_needs_several_views(page):
    page.click("nav >> text=Full tire")
    assert "needs several views" in page.locator("#view").inner_text()
    page.get_by_role("button", name="Load demo wheel").click()
    page.wait_for_selector("text=18 views", timeout=20000)             # (the nav also says "Rotating wheel": wait on the badge)
    assert page.locator("#view >> text=Rotating wheel").count() >= 1


@pytest.mark.parametrize("size", [(1280, 800), (1920, 1080)])
def test_no_horizontal_overflow(browser, srv, size):
    ui_server.reset_session()
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]})
    pg = ctx.new_page()
    pg.goto(srv.url)
    pg.wait_for_function("window.__ready===true")
    load_demo(pg)
    pg.wait_for_timeout(800)
    for nav in ("Preview", "Segment tire", "Accuracy", "Export", "Sensor check"):
        pg.click(f"nav >> text={nav}")
        pg.wait_for_timeout(250)
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), nav
    ctx.close()


def test_depth_map_hover_readout(page):
    load_demo(page)
    page.wait_for_timeout(800)
    run_analysis(page)
    page.click('role=tab[name="Grooves"]')
    page.wait_for_timeout(1500)
    box = page.locator(".pane canvas").first.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    page.wait_for_timeout(300)
    assert "depth" in page.locator(".pane .chip.num").first.inner_text()
