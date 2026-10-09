import json
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import pytest

from treadlidar.ui.server import create_server, params_to_cfg, ApiError
from treadlidar.ui import launcher


@pytest.fixture(scope="module")
def srv():
    s = create_server()
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield s
    s.shutdown()


class Client:
    def __init__(self, srv):
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.tok = srv.token

    def call(self, method, path, body=None, raw=False, token=True, headers=None):
        h = dict(headers or {})
        if token:
            h["X-Token"] = self.tok
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=h)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            data = e.read()
            try:
                return e.code, json.loads(data), e.headers
            except ValueError:
                return e.code, data, e.headers
        d = r.read()
        return r.status, (d if raw else json.loads(d)), r.headers

    def job(self, method, path, body, timeout=240):
        s, d, _ = self.call(method, path, body)
        assert s == 200, d
        jid = d["job"]["id"]
        t0 = time.time()
        while time.time() - t0 < timeout:
            s, j, _ = self.call("GET", "/api/jobs/" + jid)
            if j["status"] != "running":
                return j
            time.sleep(0.2)
        raise TimeoutError


@pytest.fixture(scope="module")
def c(srv):
    return Client(srv)


@pytest.fixture(scope="module")
def demo(c):
    s, d, _ = c.call("POST", "/api/scans/demo", {"kind": "single"})
    assert s == 200
    return d["scans"][0]


@pytest.fixture(scope="module")
def analysed(c, demo):
    j = c.job("POST", "/api/analyze", {"scan_ids": [demo["id"]], "params": {"tire": {"tread_half_width_mm": 95}}})
    assert j["status"] == "done", j
    return j["result"]["results"][0]


# ------------------------------------------------------------------ security
def test_api_requires_token(c):
    assert c.call("GET", "/api/info", token=False)[0] == 403
    assert c.call("GET", "/api/info", headers={"X-Token": "wrong"}, token=False)[0] == 403


def test_index_requires_token_and_serves_with_it(c):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(c.base + "/")
    assert e.value.code == 403
    html = urllib.request.urlopen(f"{c.base}/?t={c.tok}").read().decode()
    assert "<title>TreadLidar</title>" in html


def test_foreign_host_header_is_rejected(c):
    s, d, _ = c.call("GET", "/api/info", headers={"Host": "evil.example.com"})
    assert s == 403
    req = urllib.request.Request(f"{c.base}/style.css", headers={"Host": "evil.example.com"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403


def test_static_path_traversal_blocked(c):
    for p in ("/../server.py", "/%2e%2e/server.py", "/static/../../server.py"):
        req = urllib.request.Request(c.base + p)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code in (403, 404)


def test_server_binds_loopback_only(srv):
    assert srv.server_address[0] == "127.0.0.1"


# ------------------------------------------------------------------ basics
def test_info_and_fs(c, tmp_path):
    s, info, _ = c.call("GET", "/api/info")
    assert s == 200 and info["version"] and "tire" in info["defaults"] and ".pcd" in info["exts"]
    (tmp_path / "a.npy").write_bytes(b"x")
    (tmp_path / "notes.txt.bak").write_text("x")
    (tmp_path / "sub").mkdir()
    s, d, _ = c.call("GET", "/api/fs?path=" + str(tmp_path))
    names = {i["name"]: i["kind"] for i in d["items"]}
    assert names == {"sub": "dir", "a.npy": "file"}                        # only dirs and supported point-cloud files
    assert c.call("GET", "/api/fs?path=/definitely/not/here")[0] == 404


def test_load_real_file_with_units_and_sidecar(c, tmp_path):
    pts = np.random.default_rng(0).uniform(0, 1000, (500, 3))               # millimetres
    np.save(tmp_path / "s.npy", pts)
    (tmp_path / "s.sensor.json").write_text(json.dumps({"sensor_origin": [1.0, 2.0, 3.0]}))
    s, d, _ = c.call("POST", "/api/scans/load", {"paths": [str(tmp_path / "s.npy")], "scale": 0.001})
    sc = d["scans"][0]
    assert sc["n_points"] == 500 and sc["simulated"] is False and sc["origin_from_sidecar"]
    assert sc["sensor_origin"] == [1.0, 2.0, 3.0] and max(sc["bbox_max"]) <= 1.0 + 1e-9    # mm -> m honoured


def test_load_errors_are_reported(c, tmp_path):
    (tmp_path / "bad.foo").write_text("1 2 3")
    assert c.call("POST", "/api/scans/load", {"paths": [str(tmp_path / "bad.foo")]})[0] == 400
    np.save(tmp_path / "tiny.npy", np.zeros((5, 3)))
    s, d, _ = c.call("POST", "/api/scans/load", {"paths": [str(tmp_path / "tiny.npy")]})
    assert s == 400 and "valid points" in d["error"]


def test_scan_points_binary_matches_meta(c, demo):
    s, b, h = c.call("GET", f"/api/scans/{demo['id']}/points?max=5000", raw=True)
    meta = json.loads(h["X-Meta"])
    assert meta["n"] == 5000 and len(b) == 5000 * 12 and meta["n_total"] == demo["n_points"]


def test_patch_sensor_origin_and_name(c, demo):
    s, d, _ = c.call("PATCH", f"/api/scans/{demo['id']}", {"sensor_origin": [0.5, 0, 0.8], "name": "renamed"})
    assert d["scan"]["sensor_origin"] == [0.5, 0, 0.8] and d["scan"]["name"] == "renamed"
    assert c.call("PATCH", f"/api/scans/{demo['id']}", {"sensor_origin": [1, 2]})[0] == 400
    c.call("PATCH", f"/api/scans/{demo['id']}", {"sensor_origin": demo["sensor_origin"]})


def test_params_validation():
    with pytest.raises(ApiError):
        params_to_cfg({"tire": {"axis_hint": "1,2"}})
    cfg = params_to_cfg({"tire": {"axis_hint": "0,1,0", "tread_half_width_mm": 80}, "recon": {"smoothing_sigma": 1.5}})
    assert cfg["segmentation"]["axis_hint"] == [0.0, 1.0, 0.0] and cfg["segmentation"]["tread_half_width_m"] == pytest.approx(0.08)
    assert cfg["analysis"]["smoothing_sigma_cells"] == 1.5


# ------------------------------------------------------------------ analysis
def test_analysis_job_result_and_progress(analysed):
    rep = analysed["report"]
    assert abs(rep["mean_tread_depth_mm"] - 8.0) < 0.5
    assert len([g for g in rep["grooves"] if g["kind"] == "longitudinal"]) == 4
    assert "config" not in rep and analysed["simulated"] is True
    assert analysed["map"]["rows"] > 10 and all("centerline_mm" in g for g in rep["grooves"])


def test_job_progress_stages_are_reported(c, demo):
    seen = []
    s, d, _ = c.call("POST", "/api/analyze", {"scan_ids": [demo["id"]], "params": {"tire": {"tread_half_width_mm": 95}, "detect": {"threshold_mm": 1.7}}})
    jid = d["job"]["id"]
    while True:
        s, j, _ = c.call("GET", "/api/jobs/" + jid)
        seen.append(j["message"])
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["progress"] == 1.0 and len(set(seen)) >= 2


def test_failed_analysis_surfaces_a_clear_error(c):
    s, d, _ = c.call("POST", "/api/scans/load", {"paths": []})
    rng = np.random.default_rng(1)
    import tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "noise.npy")
    np.save(p, rng.uniform(-1, 1, (3000, 3)))
    s, d, _ = c.call("POST", "/api/scans/load", {"paths": [p]})
    j = c.job("POST", "/api/analyze", {"scan_ids": [d["scans"][0]["id"]], "params": {}})
    assert j["status"] == "error" and j["error"]                                  # not a tire: loud error, not garbage


def test_binary_geometry_endpoints_have_consistent_sizes(c, analysed):
    rid = analysed["id"]
    s, b, h = c.call("GET", f"/api/results/{rid}/depthmap", raw=True)
    m = json.loads(h["X-Meta"])
    assert len(b) == m["rows"] * m["cols"] * 4
    D = np.frombuffer(b, "<f4")
    assert np.nanmax(D) > 6 and np.isfinite(D).mean() > 0.8
    s, b, h = c.call("GET", f"/api/results/{rid}/mesh", raw=True)
    m = json.loads(h["X-Meta"])
    assert len(b) == m["nv"] * 16 + m["nf"] * 12
    f = np.frombuffer(b[m["nv"] * 16:], "<u4")
    assert f.max() < m["nv"]
    s, b, h = c.call("GET", f"/api/results/{rid}/points?max=3000", raw=True)
    assert len(b) == json.loads(h["X-Meta"])["n"] * 16
    s, b, h = c.call("GET", f"/api/results/{rid}/groovelines", raw=True)
    assert len(b) == json.loads(h["X-Meta"])["n"] * 12 and len(b) > 0


def test_measure_region_profile_endpoints(c, analysed):
    rid = analysed["id"]
    g = [x for x in analysed["report"]["grooves"] if x["kind"] == "longitudinal"][1]
    s, m, _ = c.call("GET", f"/api/results/{rid}/measure?s={g['s_center_m'] * 1e3}&w={g['w_center_m'] * 1e3}&r=6")
    assert m["valid"] and abs(m["depth_mm"] - 8.0) < 1.0 and len(m["world_reference"]) == 3
    top, bottom = np.array(m["world_reference"]), np.array(m["world_bottom"])
    assert abs(np.linalg.norm(top - bottom) * 1e3 - m["depth_mm"]) < 0.05           # 3D pin spans exactly the depth
    s, m2, _ = c.call("GET", f"/api/results/{rid}/measure?s=9999&w=9999&r=3")
    assert m2["valid"] is False
    s, r, _ = c.call("GET", f"/api/results/{rid}/region?s0=-20&s1=20&w0={g['w_center_m'] * 1e3 - 3}&w1={g['w_center_m'] * 1e3 + 3}")
    assert r["valid"] and abs(r["median_mm"] - 8.0) < 1.0
    s, p, _ = c.call("GET", f"/api/results/{rid}/profile?s=0&half=2")
    assert p["n_points"] > 20 and len(p["reference"]["w_mm"]) == 240 and p["groove_spans_mm"]


def test_unknown_ids_are_404(c):
    for path in ("/api/results/nope", "/api/results/nope/mesh", "/api/jobs/nope", "/api/scans/nope/points", "/api/fulltires/nope/map"):
        assert c.call("GET", path)[0] == 404


# ------------------------------------------------------------------ export
def test_export_and_zip(c, analysed, tmp_path):
    rid = analysed["id"]
    s, d, _ = c.call("POST", f"/api/results/{rid}/export", {"dir": str(tmp_path / "out"), "tire_id": "T9", "scan_id": "S9"})
    names = {f["name"] for f in d["files"]}
    assert {"T9_S9_mesh.stl", "T9_S9_mesh.ply", "T9_S9_mesh.obj", "T9_S9_report.json", "T9_S9_points.ply"} <= names
    assert (tmp_path / "out" / "T9_S9_SIMULATED_DATA.txt").exists()                  # simulated exports are labelled on disk
    s, z, h = c.call("GET", f"/api/results/{rid}/bundle.zip", raw=True)
    assert s == 200 and z[:2] == b"PK" and len(z) > 10000
    assert c.call("POST", f"/api/results/{rid}/export", {"dir": ""})[0] == 400


# ------------------------------------------------------------------ validation guards
def _val(c, ids, origin, ref):
    return c.job("POST", "/api/validate", {"scan_ids": ids, "reference": ref, "origin": origin, "params": {"tire": {"tread_half_width_mm": 95}}})


def test_validation_refuses_real_for_simulated(c, demo):
    s, d, _ = c.call("POST", "/api/validate", {"scan_ids": [demo["id"]], "reference": [{"groove_index": 1, "ref_depth_mm": 8}], "origin": "real"})
    assert s == 400 and "simulated" in d["error"]


def test_validation_pipeline_and_not_assessed(c):
    ids = []
    for _ in range(3):
        s, d, _ = c.call("POST", "/api/scans/demo", {"kind": "single"})
        ids.append(d["scans"][0]["id"])
    ref = [{"groove_index": i, "ref_depth_mm": 8.0} for i in (1, 2, 3, 4)]
    j = _val(c, ids, "simulated", ref)
    assert j["status"] == "done", j
    v = j["result"]["validation"]
    assert v["feasibility"]["result"] == "NOT_ASSESSED" and v["n_scans_used"] == 3
    assert v["accuracy_single_scan"]["rmse_mm"] < 0.5 and v["repeatability"]["pooled_std_mm"] < 0.5
    assert len(v["pairs"]) == 12


def test_validation_input_errors(c, demo):
    assert c.call("POST", "/api/validate", {"scan_ids": [demo["id"]], "reference": [], "origin": "unknown"})[0] == 400
    assert c.call("POST", "/api/validate", {"scan_ids": [], "reference": [{"groove_index": 1, "ref_depth_mm": 8}], "origin": "unknown"})[0] == 400
    assert c.call("POST", "/api/validate", {"scan_ids": [demo["id"]], "reference": [{"groove_index": "x", "ref_depth_mm": "y"}], "origin": "unknown"})[0] == 400
    assert c.call("POST", "/api/validate", {"scan_ids": [demo["id"]], "reference": [{"groove_index": 1, "ref_depth_mm": 8}], "origin": "bogus"})[0] == 400


# ------------------------------------------------------------------ full tire + tools + merge
def test_fulltire_job_api(c):
    s, d, _ = c.call("POST", "/api/scans/demo", {"kind": "wheel"})
    scans = d["scans"]
    assert len(scans) == 18 and all(x["simulated"] and x["wheel_angle_deg"] is not None for x in scans)
    ids = [x["id"] for x in scans[:6]]                                              # 6 views: partial coverage on purpose
    j = c.job("POST", "/api/fulltire", {"scan_ids": ids, "circumference_mm": 1885, "angles": [x["wheel_angle_deg"] for x in scans[:6]],
                                        "protocol": {"n_positions": 12, "expected_grooves": 4}, "params": {"tire": {"tread_half_width_mm": 95}}}, timeout=400)
    assert j["status"] == "done", j
    r = j["result"]
    assert r["simulated"] and r["report"]["coverage"]["rows_covered_fraction"] < 0.6 and len(r["coverage_deg"]) == 360
    assert r["report"]["summary"]["n_missing"] > 0
    s, b, h = c.call("GET", f"/api/fulltires/{r['id']}/map", raw=True)
    m = json.loads(h["X-Meta"])
    assert len(b) == m["rows"] * m["cols"] * 4
    s, b, h = c.call("GET", f"/api/fulltires/{r['id']}/mesh", raw=True)
    mm = json.loads(h["X-Meta"])
    assert len(b) == mm["nv"] * 16 + mm["nf"] * 12


def test_fulltire_input_errors(c, demo):
    assert c.call("POST", "/api/fulltire", {"scan_ids": [demo["id"]]})[0] == 400
    assert c.call("POST", "/api/fulltire", {"scan_ids": [demo["id"], demo["id"]], "angles": [0]})[0] == 400


def test_sensor_tools_with_crop(c, demo):
    s, d, _ = c.call("POST", "/api/tools", {"tool": "plane", "scan_id": demo["id"], "tol_mm": 10})
    assert d["tool"] == "plane" and d["noise_std_mm"] > 0
    assert c.call("POST", "/api/tools", {"tool": "plane", "scan_id": demo["id"], "roi": {"center": [50, 50, 50], "radius_m": 0.1}})[0] == 400
    assert c.call("POST", "/api/tools", {"tool": "nope", "scan_id": demo["id"]})[0] == 400


def test_merge_scans(c):
    ids = []
    for _ in range(2):
        s, d, _ = c.call("POST", "/api/scans/demo", {"kind": "single"})
        ids.append(d["scans"][0])
    s, m, _ = c.call("POST", "/api/scans/merge", {"scan_ids": [i["id"] for i in ids], "method": "concat"})
    assert m["scan"]["n_points"] == sum(i["n_points"] for i in ids) and m["scan"]["simulated"]
    assert c.call("POST", "/api/scans/merge", {"scan_ids": [ids[0]["id"]]})[0] == 400


# ------------------------------------------------------------------ launcher
def test_launcher_finds_chromium_only_when_present(tmp_path):
    assert launcher.find_chromium(str(tmp_path / "nonexistent")) is None
    fake = tmp_path / "chrome"
    fake.write_text("#!/bin/sh\n")
    assert launcher.find_chromium(str(fake)) == str(fake)


def test_cli_registers_ui_command(capsys):
    from treadlidar import cli
    with pytest.raises(SystemExit):
        cli.main(["ui", "--help"])
    assert "--mode" in capsys.readouterr().out
