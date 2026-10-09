"""Rotating-wheel workflow: pooled frame fit -> per-view analysis -> stitching -> protocol -> exports."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from ..export import report as rep
from ..export import writers
from ..pipeline import analyze_scan, build_frame
from ..preprocessing.filters import apply_preprocess
from ..tire_segmentation.segment import segment_tire
from ..types import PointCloud
from . import plots
from .mesh import fulltire_mesh
from .protocol import run_protocol
from .stitch import FullTireMap, stitch_views


def analyze_rotating_wheel(clouds: Sequence[PointCloud], cfg: dict, angles_deg: Optional[Sequence[float]] = None,
                           circumference_m: Optional[float] = None, tire_id: str = "TIRE_001",
                           stitch_kwargs: Optional[dict] = None, progress=None):
    """Fixed sensor, wheel turned between views. Returns (FullTireMap, per-view AnalysisResults, pooled CylinderFit).

    The wheel axis/centre/radius are identical in every view, so ONE cylinder is fitted to the pooled tire points
    of all views and every view is analysed in that common frame (per-view fits of a short arc disagree by mm).
    """
    _p = progress or (lambda frac, msg: None)
    pre_cfg = copy.deepcopy(cfg["preprocess"])
    pre_cfg["outlier_removal"]["enabled"] = False
    cands = []
    for k, pc in enumerate(clouds):
        _p(0.02 + 0.2 * k / len(clouds), f"Segmenting view {k + 1}/{len(clouds)}")
        pre, _ = apply_preprocess(pc, pre_cfg)
        idx, _ = segment_tire(pre.xyz, cfg["segmentation"], pre.sensor_origin)
        cands.append(pre.xyz[idx])
    if min(len(c) for c in cands) < 1000:
        raise RuntimeError("a view has too few tire points after segmentation")
    _p(0.25, "Fitting one cylinder to all views")
    fit, _, radius_ok, fit_warn = build_frame(np.vstack(cands), clouds[0].sensor_origin, cfg)
    results = []
    for i, pc in enumerate(clouds):
        _p(0.28 + 0.6 * i / len(clouds), f"Analysing view {i + 1}/{len(clouds)}")
        results.append(analyze_scan(pc, cfg, tire_id, f"VIEW_{i:03d}", export=False, fixed_fit=fit))
    _p(0.9, "Stitching the views")
    kw = {"common_frame": True, **(stitch_kwargs or {})}
    fm = stitch_views(results, angles_deg, circumference_m, **kw)
    fm.warnings = fit_warn + fm.warnings
    return fm, results, fit


def export_fulltire(fm: FullTireMap, protocol_report: dict, out_dir, tire_id: str = "TIRE_001") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{tire_id}_fulltire"
    V, F, col, depth = fulltire_mesh(fm)
    meta = {"tire_id": tire_id, "units": "metre", "circumference_mm": f"{fm.circumference_m * 1e3:.1f}",
            "note": "full-circumference tread height field; unvalidated unless a real-data validation report exists"}
    paths = {
        "mesh_ply": writers.write_ply_mesh(out / f"{stem}_mesh.ply", V, F, None, col, {"depth_mm": depth * 1e3}, meta),
        "mesh_stl": writers.write_stl(out / f"{stem}_mesh.stl", V, F, stem),
        "mesh_obj": writers.write_obj(out / f"{stem}_mesh.obj", V, F, writers.vertex_normals(V, F), meta),
        "protocol_json": rep.write_json(out / f"{stem}_protocol.json", protocol_report),
        "measurements_csv": rep.write_csv(out / f"{stem}_measurements.csv", protocol_report["measurements"]),
    }
    plots.plot_unrolled(out / f"{stem}_unrolled.png", fm, protocol_report)
    paths["unrolled_png"] = out / f"{stem}_unrolled.png"
    return {k: str(p) for k, p in paths.items()}
