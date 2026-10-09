#!/usr/bin/env python3
"""Regenerate docs/images/*.png by driving the real UI in headless Chromium (needs `pip install playwright`).

All screenshots show SIMULATED demo data. Usage: python scripts/make_ui_screenshots.py [--chromium PATH]
"""
import argparse
import sys
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402

from treadlidar.ui import server  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--chromium", default="/opt/pw-browsers/chromium")
ap.add_argument("--out", default=str(root / "docs" / "images"))
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
srv = server.create_server()
threading.Thread(target=srv.serve_forever, daemon=True).start()
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=a.chromium if Path(a.chromium).exists() else None, args=ARGS)

    def new(theme="light", w=1440, h=900):
        server.reset_session()
        ctx = b.new_context(viewport={"width": w, "height": h}, color_scheme=theme)
        pg = ctx.new_page()
        pg.goto(srv.url)
        pg.wait_for_function("window.__ready===true")
        return pg

    def shot(pg, name, wait=1500):
        pg.wait_for_timeout(wait)
        pg.screenshot(path=str(out / f"{name}.png"))
        print("wrote", name)

    pg = new()
    shot(pg, "01-welcome", 300)
    pg.click("text=Load demo scan"); pg.wait_for_selector(".scan-card")
    for _ in range(3):
        pg.get_by_role("button", name="Demo scan").click(); pg.wait_for_timeout(500)
    pg.click(".scan-card >> nth=0"); shot(pg, "02-data-preview", 2000)
    pg.click("text=Continue to tread analysis"); pg.wait_for_timeout(400)
    shot(pg, "03-parameters", 400)
    pg.get_by_role("button", name="Run analysis").first.click(); pg.wait_for_selector(".tile", timeout=90000)
    shot(pg, "04-segmentation", 2500)
    for tab, name in (("Surface", "05-surface"), ("Grooves", "06-grooves"), ("Density", "07-density")):
        pg.click(f'role=tab[name="{tab}"]'); shot(pg, name, 2200)
    pg.click("nav >> text=Select area"); pg.wait_for_timeout(2000)
    pg.click('button:has-text("Groove centres")'); pg.wait_for_timeout(2500)
    box = pg.locator(".pane canvas").first.bounding_box()
    pg.get_by_label("Region: drag a box for statistics").click()
    pg.mouse.move(box["x"] + box["width"] * .30, box["y"] + box["height"] * .25); pg.mouse.down()
    pg.mouse.move(box["x"] + box["width"] * .55, box["y"] + box["height"] * .45, steps=6); pg.mouse.up()
    shot(pg, "08-measure", 1500)
    pg.click("nav >> text=Accuracy"); pg.get_by_role("button", name="Demo readings").click(); pg.get_by_role("button", name="Simulated", exact=True).click()
    pg.get_by_role("button", name="Run validation").click(); pg.wait_for_function("document.body.innerText.includes('Paired measurements')", timeout=240000)
    shot(pg, "09-accuracy", 1500)
    pg.click("nav >> text=Export"); pg.fill('input[aria-label="Output folder"]', "/tmp/treadlidar_ui_export"); pg.get_by_role("button", name="Export all formats").click(); shot(pg, "10-export", 2200)
    pg.click("nav >> text=Sensor check"); pg.get_by_role("button", name="Run check").click(); shot(pg, "11-sensor-check", 1500)
    pg.context.close()

    pg = new(h=1250)
    pg.click("text=Load demo wheel"); pg.wait_for_selector(".scan-card"); pg.click("nav >> text=Full tire"); pg.wait_for_timeout(500)
    pg.fill('input[placeholder="needed for PASS"]', "4"); pg.get_by_role("button", name="Run full-tire analysis").click()
    pg.wait_for_function("document.body.innerText.includes('Whole-tire depth map')", timeout=300000); shot(pg, "12-full-tire", 2500)
    pg.get_by_role("button", name="3D ring").click(); shot(pg, "13-full-tire-3d", 2500)
    pg.context.close()

    pg = new("dark")
    pg.click("text=Load demo scan"); pg.wait_for_selector(".scan-card"); pg.click("text=Continue to tread analysis")
    pg.get_by_role("button", name="Run analysis").first.click(); pg.wait_for_selector(".tile", timeout=90000)
    pg.click("nav >> text=Select area"); pg.wait_for_timeout(2000); pg.click('button:has-text("Groove centres")'); shot(pg, "14-dark-measure", 2500)
    b.close()
