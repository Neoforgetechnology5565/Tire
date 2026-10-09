"""Local backend for the desktop UI (standard library only: no web framework, no new licences).

Security model (it is a localhost server that can read files and write exports):
* binds 127.0.0.1 only; every request must carry the per-launch random token (``X-Token`` header, or ``?t=`` for the
  first page load) and a ``Host`` header of 127.0.0.1/localhost (blocks DNS-rebinding);
* the filesystem browser lists directories and point-cloud files only; exports are written only where the user asks.
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import tempfile
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import numpy as np

from .. import __version__
from ..calibration.targets import plane_noise, step_height
from ..config import DEFAULTS, load_config
from ..data_acquisition.loaders import load_points
from ..export.report import _clean, write_csv, write_json
from ..fulltire.mesh import fulltire_mesh
from ..fulltire.protocol import run_protocol
from ..fulltire.workflow import analyze_rotating_wheel, export_fulltire
from ..pipeline import AnalysisResult, analyze_scan, export_result
from ..registration.icp import register_scans
from ..types import PointCloud
from ..validation import workflow as val_workflow

STATIC = Path(__file__).parent / "static"
EXTS = {".npy", ".npz", ".xyz", ".txt", ".csv", ".ply", ".pcd"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ parameters
DEFAULT_PARAMS = {
    "tire": {"axis_hint": None, "tread_half_width_mm": 120.0, "radius_min_mm": 250.0, "radius_max_mm": 500.0,
             "expected_grooves": None},
    "filter": {"outlier_enabled": False, "outlier_k": 16, "outlier_std": 3.0},
    "recon": {"cell_mm": "auto", "smoothing_sigma": 0.0, "edge_jump_mm": 30.0},
    "detect": {"threshold_mm": 1.6, "min_threshold_sigma": 3.0, "ref_method": "global_poly", "poly_degree": 2},
}


def params_to_cfg(p: Optional[dict]) -> dict:
    p = {k: {**DEFAULT_PARAMS[k], **((p or {}).get(k) or {})} for k in DEFAULT_PARAMS}
    ax = p["tire"]["axis_hint"]
    if isinstance(ax, str):
        ax = [float(x) for x in ax.replace(";", ",").split(",") if x.strip()] or None
    if ax is not None and (len(ax) != 3 or not np.linalg.norm(ax) > 0):
        raise ApiError("axis hint must be three numbers 'x,y,z' (non-zero)")
    cfg = load_config(overrides={
        "preprocess": {"outlier_removal": {"enabled": bool(p["filter"]["outlier_enabled"]), "k": int(p["filter"]["outlier_k"]),
                                           "std_ratio": float(p["filter"]["outlier_std"])}},
        "segmentation": {"axis_hint": ax, "tread_half_width_m": float(p["tire"]["tread_half_width_mm"]) * 1e-3,
                         "radius_range_m": [float(p["tire"]["radius_min_mm"]) * 1e-3, float(p["tire"]["radius_max_mm"]) * 1e-3]},
        "analysis": {"cell_mm": p["recon"]["cell_mm"] if p["recon"]["cell_mm"] == "auto" else float(p["recon"]["cell_mm"]),
                     "smoothing_sigma_cells": float(p["recon"]["smoothing_sigma"]),
                     "reference": {"method": p["detect"]["ref_method"], "poly_degree": int(p["detect"]["poly_degree"])},
                     "groove": {"threshold_mm": float(p["detect"]["threshold_mm"]),
                                "min_threshold_sigma": float(p["detect"]["min_threshold_sigma"])}},
        "reconstruction": {"edge_jump_mm": float(p["recon"]["edge_jump_mm"])},
    })
    return cfg


# ------------------------------------------------------------------ session state
class Job:
    def __init__(self, kind: str):
        self.id = secrets.token_hex(6)
        self.kind = kind
        self.status = "running"
        self.progress = 0.0
        self.message = "Starting"
        self.result = None
        self.error = None
        self.started = time.time()
        self.finished = None

    def public(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status, "progress": self.progress, "message": self.message,
                "result": self.result, "error": self.error, "elapsed_s": (self.finished or time.time()) - self.started}


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.scans: Dict[str, dict] = {}
        self.results: Dict[str, dict] = {}
        self.fulltires: Dict[str, dict] = {}
        self.jobs: Dict[str, Job] = {}
        self.cache: Dict[tuple, str] = {}

    # --- scans
    def add_scan(self, pc: PointCloud, name: str, path: str = "", sidecar: Optional[dict] = None, scale: float = 1.0) -> dict:
        sidecar = sidecar or {}
        sid = secrets.token_hex(4)
        if "sensor_origin" in sidecar:
            pc.sensor_origin = np.array(sidecar["sensor_origin"], float)
        entry = {"id": sid, "name": name, "path": path, "pc": pc, "simulated": bool(sidecar.get("simulated", False)),
                 "wheel_angle_deg": sidecar.get("wheel_angle_deg"), "circumference_m": sidecar.get("circumference_m"),
                 "scale": scale, "origin_from_sidecar": "sensor_origin" in sidecar}
        with self.lock:
            self.scans[sid] = entry
        return entry

    def scan(self, sid: str) -> dict:
        try:
            return self.scans[sid]
        except KeyError:
            raise ApiError(f"unknown scan {sid}", 404)

    def scan_public(self, e: dict) -> dict:
        xyz = e["pc"].xyz
        lo, hi = xyz.min(0), xyz.max(0)
        return {"id": e["id"], "name": e["name"], "path": e["path"], "n_points": int(len(xyz)), "simulated": e["simulated"],
                "bbox_min": lo.tolist(), "bbox_max": hi.tolist(), "sensor_origin": e["pc"].sensor_origin.tolist(),
                "origin_from_sidecar": e["origin_from_sidecar"], "wheel_angle_deg": e["wheel_angle_deg"],
                "circumference_m": e["circumference_m"], "has_intensity": e["pc"].intensity is not None,
                "has_point_time": e["pc"].t is not None, "scale": e["scale"]}

    # --- results
    def result(self, rid: str) -> dict:
        try:
            return self.results[rid]
        except KeyError:
            raise ApiError(f"unknown result {rid}", 404)

    def run_analysis(self, scan_id: str, params: dict, tire_id: str = "TIRE_001", progress=None) -> str:
        key = (scan_id, json.dumps(params, sort_keys=True), tuple(self.scan(scan_id)["pc"].sensor_origin.round(6)))
        with self.lock:
            if key in self.cache and self.cache[key] in self.results:
                return self.cache[key]
        e = self.scan(scan_id)
        cfg = params_to_cfg(params)
        res = analyze_scan(e["pc"], cfg, tire_id, e["name"], export=False, progress=progress)
        rid = secrets.token_hex(5)
        with self.lock:
            self.results[rid] = {"id": rid, "scan_id": scan_id, "name": e["name"], "res": res, "params": params,
                                 "simulated": e["simulated"], "created": time.time()}
            self.cache[key] = rid
        return rid

    def result_public(self, rid: str) -> dict:
        r = self.result(rid)
        res: AnalysisResult = r["res"]
        rep = {k: v for k, v in res.report.items() if k not in ("config",)}
        gr = []
        for g in res.grooves:
            d = g.summary()
            cl = g.centerline
            step = max(1, len(cl) // 60)
            d["centerline_mm"] = (cl[::step] * 1e3).tolist()
            d["position_index"] = (res.longitudinal().index(g) + 1) if g in res.longitudinal() else None
            gr.append(d)
        rep["grooves"] = gr
        hm = res.hm
        return _clean({"id": rid, "scan_id": r["scan_id"], "name": r["name"], "simulated": r["simulated"], "report": rep,
                       "map": {"rows": hm.shape[0], "cols": hm.shape[1], "cell_mm": hm.cell * 1e3, "s0_mm": hm.s0 * 1e3,
                               "w0_mm": hm.w0 * 1e3}})


S = Session()


def reset_session() -> None:
    """Forget all scans/results/jobs (used by tests and by 'new session')."""
    with S.lock:
        for d in (S.scans, S.results, S.fulltires, S.jobs, S.cache):
            d.clear()


# ------------------------------------------------------------------ jobs
def start_job(kind: str, fn) -> Job:
    job = Job(kind)
    S.jobs[job.id] = job

    def prog(frac, msg):
        job.progress, job.message = float(frac), str(msg)

    def run():
        try:
            job.result = _clean(fn(prog))
            job.status, job.progress, job.message = "done", 1.0, "Done"
        except ApiError as e:
            job.status, job.error = "error", str(e)
        except Exception as e:  # surface every failure to the UI, with the traceback in the server log
            traceback.print_exc()
            job.status, job.error = "error", f"{type(e).__name__}: {e}"
        job.finished = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job


# ------------------------------------------------------------------ binary helpers
def f32(a) -> bytes:
    return np.ascontiguousarray(a, dtype="<f4").tobytes()


# ------------------------------------------------------------------ route handlers
def fs_list(path: str) -> dict:
    p = Path(path or "~").expanduser()
    try:
        p = p.resolve()
    except OSError as e:
        raise ApiError(str(e))
    if p.is_file():
        p = p.parent
    if not p.is_dir():
        raise ApiError(f"not a directory: {p}", 404)
    items = []
    try:
        for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if c.name.startswith("."):
                continue
            try:
                if c.is_dir():
                    items.append({"name": c.name, "kind": "dir"})
                elif c.suffix.lower() in EXTS:
                    items.append({"name": c.name, "kind": "file", "size": c.stat().st_size, "ext": c.suffix.lower()})
            except OSError:
                continue
    except PermissionError:
        raise ApiError(f"permission denied: {p}", 403)
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None, "items": items,
            "home": str(Path.home()), "sep": os.sep}


def read_sidecar(path: Path) -> dict:
    side = path.with_suffix("").with_suffix(".sensor.json")
    try:
        return json.loads(side.read_text()) if side.exists() else {}
    except (OSError, ValueError):
        return {}


def load_scans(body: dict) -> list:
    out = []
    scale = float(body.get("scale", 1.0) or 1.0)
    for pth in body.get("paths", []):
        p = Path(pth).expanduser()
        if p.suffix.lower() not in EXTS or not p.is_file():
            raise ApiError(f"unsupported or missing file: {p}", 400)
        try:
            pc = load_points(p, scale=scale)
        except Exception as e:
            raise ApiError(f"could not read {p.name}: {e}")
        if len(pc) < 100:
            raise ApiError(f"{p.name}: only {len(pc)} valid points")
        out.append(S.scan_public(S.add_scan(pc, p.stem, str(p), read_sidecar(p), scale)))
    return out


_DEMO_COUNTER = [0]


def make_demo(kind: str) -> list:
    from ..simulation.synthetic import SensorSim, TreadSpec, generate_scan

    out_dir = Path(tempfile.mkdtemp(prefix="treadlidar_demo_"))
    res = []
    if kind == "wheel":
        spec = TreadSpec(lateral_pitches_m=[0.034, 0.040, 0.046, 0.040, 0.036, 0.044])
        depths = [3.0, 5.0, 6.0, 4.0]
        spec.longitudinal = [(y, w, d * 1e-3) for (y, w, _), d in zip(spec.longitudinal, depths)]
        n, step = 18, 20.0
    else:
        spec, n, step = TreadSpec(), 1, 0.0
        _DEMO_COUNTER[0] += 1               # each demo scan has different noise, so repeated loads give real repeatability
    for k in range(n):
        ang = k * step
        pc, _ = generate_scan(spec, SensorSim(range_noise_mm=1.0, density_per_cm2=40), arc_length_m=0.18 if n > 1 else 0.16,
                              seed=k if n > 1 else 100 + _DEMO_COUNTER[0], wheel_angle_deg=ang)
        side = {"sensor_origin": pc.sensor_origin.tolist(), "simulated": True}
        if n > 1:
            side.update(wheel_angle_deg=ang, circumference_m=2 * np.pi * spec.radius_m)
        name = f"sim_wheel_{k + 1:02d}" if n > 1 else f"sim_scan_demo_{_DEMO_COUNTER[0]}"
        np.save(out_dir / f"{name}.npy", pc.xyz.astype(np.float32))
        (out_dir / f"{name}.sensor.json").write_text(json.dumps(side))
        res.append(S.scan_public(S.add_scan(pc, name, str(out_dir / f"{name}.npy"), side)))
    return res


def points_payload(sid: str, max_pts: int):
    e = S.scan(sid)
    xyz = e["pc"].xyz
    n = len(xyz)
    if n > max_pts:
        idx = np.random.default_rng(0).choice(n, max_pts, replace=False)
        xyz = xyz[idx]
    lo, hi = e["pc"].xyz.min(0), e["pc"].xyz.max(0)
    return f32(xyz), {"n": int(len(xyz)), "n_total": int(n), "bbox_min": lo.tolist(), "bbox_max": hi.tolist(),
                      "sensor_origin": e["pc"].sensor_origin.tolist()}


def result_points(rid: str, max_pts: int):
    res: AnalysisResult = S.result(rid)["res"]
    xyz, s, w, dr = res.tire_xyz, res.s, res.w, res.dr
    depth = (res.ref(w, s) - dr) * 1e3
    n = len(xyz)
    if n > max_pts:
        idx = np.random.default_rng(0).choice(n, max_pts, replace=False)
        xyz, depth = xyz[idx], depth[idx]
    return f32(xyz) + f32(depth), {"n": int(len(xyz)), "n_total": int(n)}


def result_mesh(rid: str):
    v, f, col, depth = S.result(rid)["res"].mesh
    meta = {"nv": int(len(v)), "nf": int(len(f))}
    return f32(v) + f32(depth * 1e3) + np.ascontiguousarray(f, dtype="<u4").tobytes(), meta


def result_depthmap(rid: str):
    res: AnalysisResult = S.result(rid)["res"]
    D = res.D * 1e3
    hm = res.hm
    meta = {"rows": hm.shape[0], "cols": hm.shape[1], "cell_mm": hm.cell * 1e3, "s0_mm": hm.s0 * 1e3, "w0_mm": hm.w0 * 1e3}
    return f32(D), meta


def result_profile(rid: str, s_mm: float, half_mm: float) -> dict:
    res: AnalysisResult = S.result(rid)["res"]
    s0, half = s_mm * 1e-3, half_mm * 1e-3
    m = np.abs(res.s - s0) <= half
    wsel, drsel = res.w[m], res.dr[m]
    if len(wsel) > 4000:
        idx = np.random.default_rng(0).choice(len(wsel), 4000, replace=False)
        wsel, drsel = wsel[idx], drsel[idx]
    hm = res.hm
    i = int(np.clip(np.floor((s0 - hm.s0) / hm.cell), 0, hm.shape[0] - 1))
    wc = hm.w0 + (np.arange(hm.shape[1]) + 0.5) * hm.cell
    wg = np.linspace(res.w.min(), res.w.max(), 240)
    spans = []
    row = np.zeros(hm.shape[1], bool)
    for g in res.grooves:
        row |= g.mask[i]
    j = 0
    while j < len(row):
        if row[j]:
            k = j
            while k + 1 < len(row) and row[k + 1]:
                k += 1
            spans.append([float(wc[j] * 1e3), float(wc[k] * 1e3)])
            j = k + 1
        else:
            j += 1
    ref_row = res.ref.lateral(wc) + res.ref.bow_at(s0)
    return _clean({"s_mm": s_mm, "n_points": int(m.sum()), "raw": {"w_mm": wsel * 1e3, "dr_mm": drsel * 1e3},
                   "reference": {"w_mm": wg * 1e3, "dr_mm": (res.ref(wg, np.full_like(wg, s0))) * 1e3},
                   "heightmap": {"w_mm": wc * 1e3, "dr_mm": res.z[i] * 1e3}, "reference_row_mm": ref_row * 1e3,
                   "groove_spans_mm": spans})


def region_stats(rid: str, s0, s1, w0, w1) -> dict:
    res: AnalysisResult = S.result(rid)["res"]
    hm = res.hm
    sc, wc = hm.cell_centers()
    S_, W_ = np.meshgrid(sc, wc, indexing="ij")
    m = (S_ >= min(s0, s1)) & (S_ <= max(s0, s1)) & (W_ >= min(w0, w1)) & (W_ <= max(w0, w1)) & np.isfinite(res.D)
    if not m.any():
        return {"valid": False, "reason": "no data in the selected region"}
    v = res.D[m] * 1e3
    return {"valid": True, "n_cells": int(m.sum()), "n_points": int(hm.count[m].sum()), "mean_mm": float(v.mean()), "median_mm": float(np.median(v)),
            "min_mm": float(v.min()), "max_mm": float(v.max()), "std_mm": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "p05_mm": float(np.quantile(v, .05)), "p95_mm": float(np.quantile(v, .95))}


# ------------------------------------------------------------------ analysis / validation / full tire jobs
def job_analyze(body: dict):
    ids = body.get("scan_ids") or []
    if not ids:
        raise ApiError("select at least one scan")
    params = body.get("params") or {}
    params_to_cfg(params)                                    # validate early, in the request thread
    tire_id = body.get("tire_id") or "TIRE_001"

    def fn(prog):
        out = []
        for k, sid in enumerate(ids):
            base = k / len(ids)
            rid = S.run_analysis(sid, params, tire_id, lambda f, m, b=base: prog(b + f / len(ids), m if len(ids) == 1 else f"{S.scan(sid)['name']}: {m}"))
            out.append(S.result_public(rid))
        return {"results": out}
    return start_job("analyze", fn)


def job_validate(body: dict):
    ids = body.get("scan_ids") or []
    ref_rows = body.get("reference") or []
    origin = body.get("origin", "unknown")
    if origin not in ("real", "simulated", "unknown"):
        raise ApiError("origin must be real, simulated or unknown")
    if origin == "real" and any(S.scan(i)["simulated"] for i in ids):
        raise ApiError("refusing origin 'real': at least one selected scan is marked simulated")
    try:
        reference = {int(r["groove_index"]): float(r["ref_depth_mm"]) for r in ref_rows if r.get("ref_depth_mm") not in (None, "")}
    except (ValueError, KeyError):
        raise ApiError("reference rows need integer groove_index and numeric ref_depth_mm")
    if not reference:
        raise ApiError("enter at least one reference depth")
    if not ids:
        raise ApiError("select at least one scan")
    params = body.get("params") or {}
    cfg = params_to_cfg(params)
    if body.get("targets"):
        cfg["validation"].update({k: float(v) for k, v in body["targets"].items() if k in cfg["validation"]})

    def fn(prog):
        results = []
        for k, sid in enumerate(ids):
            rid = S.run_analysis(sid, params, body.get("tire_id") or "TIRE_001",
                                 lambda f, m, b=k / len(ids): prog(0.9 * (b + f / len(ids)), f"Scan {k + 1}/{len(ids)}: {m}"))
            results.append(S.result(rid)["res"])
        prog(0.95, "Computing accuracy and repeatability")
        v = val_workflow.validate(results, reference, cfg["validation"], origin)
        return {"validation": v}
    return start_job("validate", fn)


def job_fulltire(body: dict):
    ids = body.get("scan_ids") or []
    if len(ids) < 2:
        raise ApiError("select at least two views of the rotating wheel")
    angles = body.get("angles")
    if angles is not None:
        angles = [float(a) for a in angles]
        if len(angles) != len(ids):
            raise ApiError("one wheel angle per selected view is required")
    circ = body.get("circumference_mm")
    circ_m = float(circ) * 1e-3 if circ else None
    proto = body.get("protocol") or {}
    cfg = params_to_cfg(body.get("params") or {})

    def fn(prog):
        clouds = [S.scan(i)["pc"] for i in ids]
        stitch_kw = {} if angles is not None else {"blind_step_deg": float(body.get("blind_step_deg") or 20.0)}
        fm, results, fit = analyze_rotating_wheel(clouds, cfg, angles, circ_m, "TIRE_001", stitch_kw, progress=prog)
        prog(0.95, "Running the measurement protocol")
        pc = {"n_positions": int(proto.get("n_positions", 8)), "limit_mm": float(proto.get("limit_mm", 1.6)),
              "uncertainty_mm": (float(proto["uncertainty_mm"]) if proto.get("uncertainty_mm") not in (None, "") else None),
              "expected_grooves": (int(proto["expected_grooves"]) if proto.get("expected_grooves") not in (None, "") else None)}
        rep = run_protocol(fm, pc)
        fid = secrets.token_hex(5)
        simulated = any(S.scan(i)["simulated"] for i in ids)
        cov = np.isfinite(fm.D).mean(axis=1)
        deg = np.interp(np.arange(360) + 0.5, np.linspace(0, 360, len(cov), endpoint=False), cov)
        with S.lock:
            S.fulltires[fid] = {"id": fid, "fm": fm, "report": rep, "simulated": simulated, "views": [S.scan(i)["name"] for i in ids]}
        return {"id": fid, "simulated": simulated, "report": rep, "coverage_deg": np.round(deg, 3).tolist(),
                "map": {"rows": fm.D.shape[0], "cols": fm.D.shape[1], "cell_mm": fm.cell * 1e3, "w0_mm": fm.w0 * 1e3,
                        "circumference_mm": fm.circumference_m * 1e3},
                "grooves": rep["grooves"]}
    return start_job("fulltire", fn)


def tool_run(body: dict) -> dict:
    e = S.scan(body.get("scan_id", ""))
    P = e["pc"].xyz
    roi = body.get("roi")
    if roi and roi.get("center") and float(roi.get("radius_m") or 0) > 0:
        c = np.array([float(x) for x in roi["center"]])
        P = P[np.linalg.norm(P - c, axis=1) <= float(roi["radius_m"])]
        if len(P) < 200:
            raise ApiError(f"only {len(P)} points inside the crop sphere; check its centre and radius")
    tol = float(body.get("tol_mm", 10)) * 1e-3
    if body.get("tool") == "plane":
        return {"tool": "plane", **plane_noise(P, tol)}
    if body.get("tool") == "step":
        out = step_height(P, tol=tol)
        known = body.get("known_mm")
        if known not in (None, ""):
            out["known_mm"] = float(known)
            out["error_mm"] = abs(out["step_mm"]) - float(known)
        return {"tool": "step", **out}
    raise ApiError("unknown tool")


def merge_scans(body: dict) -> dict:
    ids = body.get("scan_ids") or []
    if len(ids) < 2:
        raise ApiError("select at least two scans to merge")
    clouds = [S.scan(i)["pc"] for i in ids]
    method = body.get("method", "concat")
    diag = None
    if method == "icp":
        merged, diag = register_scans(clouds)
    else:
        merged = PointCloud.concat(clouds)
    merged.sensor_origin = clouds[0].sensor_origin.copy()
    sim = any(S.scan(i)["simulated"] for i in ids)
    e = S.add_scan(merged, f"merged_{len(ids)}_{method}", "", {"simulated": sim})
    e["pc"].sensor_origin = clouds[0].sensor_origin.copy()
    return {"scan": S.scan_public(e), "diagnostics": diag, "note": (
        "Stationary sensor: frames concatenated in the sensor frame." if method == "concat" else
        "ICP is poorly constrained on a tread patch (a cylinder slides around its axis): check the residuals; prefer a fixed sensor pose.")}


def export_result_files(rid: str, directory: str, tire_id: str, scan_id: str) -> dict:
    r = S.result(rid)
    res: AnalysisResult = r["res"]
    out = Path(directory).expanduser()
    if not directory:
        raise ApiError("choose an output folder")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ApiError(f"cannot create {out}: {e}")
    res.tire_id, res.scan_id = tire_id or res.tire_id, scan_id or res.scan_id
    paths = export_result(res, out)
    if r["simulated"]:
        (out / f"{res.tire_id}_{res.scan_id}_SIMULATED_DATA.txt").write_text("These files were produced from SIMULATED data (not a real L2 scan).\n")
    return {"dir": str(out), "files": [{"name": Path(p).name, "kind": k, "size": Path(p).stat().st_size} for k, p in paths.items()]}


def zip_result(rid: str) -> bytes:
    res: AnalysisResult = S.result(rid)["res"]
    with tempfile.TemporaryDirectory() as d:
        export_result(res, d)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(Path(d).iterdir()):
                z.write(f, f.name)
        return buf.getvalue()


def fulltire_public(fid: str) -> dict:
    try:
        return S.fulltires[fid]
    except KeyError:
        raise ApiError(f"unknown full-tire result {fid}", 404)


# ------------------------------------------------------------------ HTTP layer
class Handler(BaseHTTPRequestHandler):
    server_version = "treadlidar-ui"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("TREADLIDAR_UI_LOG"):
            super().log_message(fmt, *args)

    # -- helpers
    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(_clean(obj)).encode(), "application/json")

    def _bin(self, data: bytes, meta: dict):
        self._send(200, data, "application/octet-stream", {"X-Meta": json.dumps(meta)})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024 * 1024:
            raise ApiError("request too large", 413)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            raise ApiError("invalid JSON body")

    def _authorised(self, query: dict) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        tok = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(tok, self.server.token)

    # -- dispatch
    def _dispatch(self, method: str):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        path = url.path
        try:
            if not path.startswith("/api/"):
                return self._static(path, q)
            if not self._authorised(q):
                raise ApiError("forbidden", 403)
            body = self._body() if method in ("POST", "PATCH", "PUT") else {}
            self._api(method, path, q, body)
        except ApiError as e:
            self._json({"error": str(e)}, e.status)
        except BrokenPipeError:
            pass
        except Exception as e:
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _static(self, path: str, q: dict):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return self._send(403, b"forbidden", "text/plain")
        if path in ("/", "/index.html"):
            tok = (q.get("t") or [""])[0]
            if not secrets.compare_digest(tok, self.server.token):
                return self._send(403, b"Open the app through the link printed by `treadlidar ui` (missing/invalid token).", "text/plain")
            path = "/index.html"
        f = (STATIC / path.lstrip("/")).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        self._send(200, f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))

    def _api(self, method: str, path: str, q: dict, body: dict):
        g = lambda k, d=None: (q.get(k) or [d])[0]
        m = None

        def route(pattern):
            nonlocal m
            m = re.fullmatch(pattern, path)
            return m is not None

        if method == "GET" and path == "/api/info":
            return self._json({"version": __version__, "home": str(Path.home()), "cwd": os.getcwd(), "exts": sorted(EXTS),
                               "defaults": DEFAULT_PARAMS, "targets": {"tight": 0.5, "loose": 1.0, "limited": 2.0},
                               "pipeline_defaults": {"validation": DEFAULTS["validation"], "density": DEFAULTS["density"]}})
        if method == "GET" and path == "/api/fs":
            return self._json(fs_list(g("path", "")))
        if method == "GET" and path == "/api/scans":
            return self._json({"scans": [S.scan_public(e) for e in S.scans.values()]})
        if method == "POST" and path == "/api/scans/load":
            return self._json({"scans": load_scans(body)})
        if method == "POST" and path == "/api/scans/demo":
            return self._json({"scans": make_demo(body.get("kind", "single"))})
        if method == "POST" and path == "/api/scans/merge":
            return self._json(merge_scans(body))
        if route(r"/api/scans/(\w+)"):
            sid = m.group(1)
            if method == "DELETE":
                S.scan(sid)
                with S.lock:
                    S.scans.pop(sid, None)
                return self._json({"ok": True})
            if method == "PATCH":
                e = S.scan(sid)
                if "sensor_origin" in body:
                    o = [float(x) for x in body["sensor_origin"]]
                    if len(o) != 3:
                        raise ApiError("sensor origin needs x, y, z")
                    e["pc"].sensor_origin = np.array(o)
                    e["origin_from_sidecar"] = False
                if "wheel_angle_deg" in body:
                    e["wheel_angle_deg"] = None if body["wheel_angle_deg"] in (None, "") else float(body["wheel_angle_deg"])
                if "name" in body and str(body["name"]).strip():
                    e["name"] = str(body["name"]).strip()
                return self._json({"scan": S.scan_public(e)})
        if route(r"/api/scans/(\w+)/points") and method == "GET":
            data, meta = points_payload(m.group(1), int(g("max", 80000)))
            return self._bin(data, meta)
        if method == "POST" and path == "/api/analyze":
            return self._json({"job": job_analyze(body).public()})
        if method == "POST" and path == "/api/validate":
            return self._json({"job": job_validate(body).public()})
        if method == "POST" and path == "/api/fulltire":
            return self._json({"job": job_fulltire(body).public()})
        if route(r"/api/jobs/(\w+)") and method == "GET":
            try:
                return self._json(S.jobs[m.group(1)].public())
            except KeyError:
                raise ApiError("unknown job", 404)
        if route(r"/api/results/(\w+)") and method == "GET":
            return self._json(S.result_public(m.group(1)))
        if route(r"/api/results/(\w+)/depthmap") and method == "GET":
            return self._bin(*result_depthmap(m.group(1)))
        if route(r"/api/results/(\w+)/points") and method == "GET":
            return self._bin(*result_points(m.group(1), int(g("max", 80000))))
        if route(r"/api/results/(\w+)/mesh") and method == "GET":
            return self._bin(*result_mesh(m.group(1)))
        if route(r"/api/results/(\w+)/profile") and method == "GET":
            return self._json(result_profile(m.group(1), float(g("s", 0)), float(g("half", 2))))
        if route(r"/api/results/(\w+)/measure") and method == "GET":
            res = S.result(m.group(1))["res"]
            s_m, w_m = float(g("s")) * 1e-3, float(g("w")) * 1e-3
            out = res.measure_at(s_m, w_m, float(g("r", 3)) * 1e-3)
            if out.get("valid"):
                r_ref = float(res.ref(np.array([w_m]), np.array([s_m]))[0])
                out["world_reference"] = res.local_to_world(s_m, w_m, r_ref)[0].tolist()
                out["world_bottom"] = res.local_to_world(s_m, w_m, r_ref - out["depth_mm"] * 1e-3)[0].tolist()
            return self._json(out)
        if route(r"/api/results/(\w+)/groovelines") and method == "GET":
            from ..mesh_utils import groove_lines
            gl = groove_lines(S.result(m.group(1))["res"])
            seg = gl["segments"]
            pts = gl["points"][seg.reshape(-1)] if len(seg) else np.zeros((0, 3))
            return self._bin(f32(pts), {"n": int(len(pts))})
        if route(r"/api/results/(\w+)/region") and method == "GET":
            return self._json(region_stats(m.group(1), *(float(g(k)) * 1e-3 for k in ("s0", "s1", "w0", "w1"))))
        if route(r"/api/results/(\w+)/export") and method == "POST":
            return self._json(export_result_files(m.group(1), body.get("dir", ""), body.get("tire_id", ""), body.get("scan_id", "")))
        if route(r"/api/results/(\w+)/bundle\.zip") and method == "GET":
            data = zip_result(m.group(1))
            return self._send(200, data, "application/zip", {"Content-Disposition": "attachment; filename=treadlidar_export.zip"})
        if route(r"/api/fulltires/(\w+)/map") and method == "GET":
            fm = fulltire_public(m.group(1))["fm"]
            return self._bin(f32(fm.D * 1e3), {"rows": fm.D.shape[0], "cols": fm.D.shape[1], "cell_mm": fm.cell * 1e3,
                                                "w0_mm": fm.w0 * 1e3, "circumference_mm": fm.circumference_m * 1e3})
        if route(r"/api/fulltires/(\w+)/mesh") and method == "GET":
            fm = fulltire_public(m.group(1))["fm"]
            v, f, col, depth = fulltire_mesh(fm)
            return self._bin(f32(v) + f32(depth * 1e3) + np.ascontiguousarray(f, dtype="<u4").tobytes(),
                             {"nv": int(len(v)), "nf": int(len(f))})
        if route(r"/api/fulltires/(\w+)/export") and method == "POST":
            e = fulltire_public(m.group(1))
            if not body.get("dir"):
                raise ApiError("choose an output folder")
            paths = export_fulltire(e["fm"], e["report"], Path(body["dir"]).expanduser(), body.get("tire_id") or "TIRE_001")
            return self._json({"dir": str(Path(body["dir"]).expanduser()), "files": [{"name": Path(p).name, "kind": k, "size": Path(p).stat().st_size}
                                                                                    for k, p in paths.items()]})
        if method == "POST" and path == "/api/tools":
            return self._json(tool_run(body))
        raise ApiError(f"no such endpoint: {method} {path}", 404)


class UiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 0):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(24)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/?t={self.token}"


def create_server(port: int = 0) -> UiServer:
    return UiServer(port)
