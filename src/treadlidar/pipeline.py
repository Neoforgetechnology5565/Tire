"""End-to-end analysis of one (accumulated) tire scan.

load -> range filter -> segmentation -> cylinder fit/unwrap -> band crop -> optional outlier filter
-> reference surface -> height map -> groove detection -> depth -> density/resolvability ->
mesh -> exports/report.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from .data_acquisition.metadata import describe_scan
from .export import report as rep
from .export import writers
from .measurement import depth as dep
from .preprocessing.filters import apply_preprocess, statistical_outlier_mask
from .reconstruction.mesh import depth_colors, heightfield_mesh
from .tire_segmentation.segment import segment_tire
from .tread_analysis import density as dens
from .tread_analysis.cylinder import CylinderFit, fit_cylinder, orient_frame
from .tread_analysis.grooves import Groove, depth_map, detect_grooves
from .tread_analysis.heightmap import HeightMap, build_heightmap, choose_cell_m, smooth_nan
from .tread_analysis.reference import ReferenceSurface, fit_reference
from .types import PointCloud


@dataclass
class AnalysisResult:
    cfg: dict
    tire_id: str
    scan_id: str
    fit: CylinderFit
    tire_xyz: np.ndarray             # points used (filtered), world/sensor frame
    raw_tire_xyz: np.ndarray         # tire candidate before band crop / outlier filter
    s: np.ndarray
    w: np.ndarray
    dr: np.ndarray
    ref: ReferenceSurface
    hm: HeightMap
    z: np.ndarray                    # height-map used for detection/mesh (smoothed iff configured)
    D: np.ndarray
    grooves: List[Groove]
    groove_mask: np.ndarray
    mesh: tuple                      # (vertices, faces, colors, depth)
    report: dict = field(default_factory=dict)
    sensor_origin: np.ndarray = None

    def longitudinal(self) -> List[Groove]:
        return dep.longitudinal_by_position(self.grooves)

    def measure_at(self, s_m: float, w_m: float, radius_m: float = 0.003) -> dict:
        return dep.measure_at(self.hm, self.ref, self.D, s_m, w_m, radius_m)

    def local_to_world(self, s, w, dr) -> np.ndarray:
        return self.fit.to_world(np.atleast_1d(s), np.atleast_1d(w), np.atleast_1d(dr))


def _per_groove_point_depths(grooves, hm, ref, s, w, dr):
    """Median point-level depth over each groove's core cells (no cell aggregation)."""
    i, j = hm.index(s, w)
    ok = (i >= 0) & (j >= 0) & (i < hm.shape[0]) & (j < hm.shape[1])
    depth_pts = ref(w, s) - dr
    out = []
    for g in grooves:
        core_mask = np.zeros(hm.shape, bool)
        # core = cells of the groove closest to its medial axis (recompute cheaply from mask)
        from scipy import ndimage
        edt = ndimage.distance_transform_edt(np.pad(g.mask, 1))[1:-1, 1:-1]
        core_mask = g.mask & (edt >= edt.max() * 0.7)
        sel = np.zeros(len(s), bool)
        sel[ok] = core_mask[i[ok], j[ok]]
        out.append(float(np.median(depth_pts[sel]) * 1e3) if sel.any() else float("nan"))
    return out


def build_frame(cand: np.ndarray, sensor_origin, cfg: dict):
    """Fit and orient the tire cylinder to segmented candidate points, crop to the tread band and centre the frame.

    Returns (fit, tread_points, radius_ok, warnings). ``s = 0`` is the direction from the axis towards the
    sensor (a fixed physical direction), ``w = 0`` the mean axial position of the retained tread points.
    """
    seg_cfg = cfg["segmentation"]
    warnings: List[str] = []
    fit = fit_cylinder(cand, seg_cfg["axis_hint"], seg_cfg["normal_k"], seg_cfg["fit_max_points"],
                       up=cfg["analysis"]["view_up"], axis_search=seg_cfg["axis_search"],
                       half_width_m=seg_cfg["tread_half_width_m"], radius_range_m=tuple(seg_cfg["radius_range_m"]))
    fit = orient_frame(fit, sensor_origin, cfg["analysis"]["view_up"])
    lo, hi = seg_cfg["radius_range_m"]
    radius_ok = bool(lo <= fit.radius <= hi and not (fit.radius < lo + 0.05 * (hi - lo) or fit.radius > hi - 0.05 * (hi - lo)))
    if not radius_ok:
        warnings.append(f"tire radius NOT determinable from this arc (fit {fit.radius * 1e3:.0f} mm vs allowed {lo * 1e3:.0f}-"
                        f"{hi * 1e3:.0f} mm): outer diameter not reported; circumferential bow is absorbed by the reference "
                        "surface, but set segmentation.axis_hint / radius_range_m or scan a longer arc for geometry")
    s0, w0_, dr0 = fit.to_local(cand)
    band = (np.abs(dr0) <= seg_cfg["cylinder_band_m"]) & (np.abs(w0_) <= seg_cfg["tread_half_width_m"])
    tread_all = cand[band]
    if len(tread_all) < 1000:
        raise RuntimeError("too few points in the tread band after cylinder fit; check cylinder_band_m/tread_half_width_m")
    s1, w1, _ = fit.to_local(tread_all)
    fit.w0 += float(w1.mean())
    vs = np.asarray(sensor_origin, float) - fit.center
    vx, vy = float(vs @ fit.e1), float(vs @ fit.e2)
    if np.hypot(vx, vy) > 0.05:
        fit.theta0 = float(np.arctan2(vy, vx))
    else:
        fit.theta0 += float(s1.mean()) / fit.radius
    return fit, tread_all, radius_ok, warnings


def analyze_scan(pc: PointCloud, cfg: dict, tire_id: str = "TIRE_001", scan_id: str = "SCAN_001",
                 out_dir: Optional[str] = None, n_frames: int = 1, export: bool = True,
                 fixed_fit: Optional[CylinderFit] = None, progress=None) -> AnalysisResult:
    """``fixed_fit``: reuse a cylinder frame fitted elsewhere (e.g. pooled over all views of a rotating wheel)
    instead of fitting this scan alone; no per-view re-centring is done in that case."""
    _p = progress or (lambda frac, msg: None)
    warnings: List[str] = []
    cfg = copy.deepcopy(cfg)
    _p(0.03, "Filtering points")
    pre_cfg = copy.deepcopy(cfg["preprocess"])
    sor = pre_cfg["outlier_removal"]
    sor_enabled, sor["enabled"] = sor["enabled"], False      # SOR is applied after segmentation, see below
    pre, pre_info = apply_preprocess(pc, pre_cfg)

    seg_cfg = cfg["segmentation"]
    _p(0.10, "Segmenting the tire (ground removal, clustering)")
    idx, seg_info = segment_tire(pre.xyz, seg_cfg, pre.sensor_origin)
    if len(idx) < 1000:
        raise RuntimeError(f"tire segmentation found only {len(idx)} points ({seg_info}); check ROI/ground params")
    cand = pre.xyz[idx]

    _p(0.25, "Fitting the tire cylinder")
    if fixed_fit is not None:
        fit = copy.deepcopy(fixed_fit)                       # already oriented and centred (see build_frame)
        s0, w0_, dr0 = fit.to_local(cand)
        band = (np.abs(dr0) <= seg_cfg["cylinder_band_m"]) & (np.abs(w0_) <= seg_cfg["tread_half_width_m"])
        tread_all = cand[band]
        if len(tread_all) < 1000:
            raise RuntimeError("too few points in the tread band for the supplied frame")
        radius_ok = True
    else:
        fit, tread_all, radius_ok, frame_warn = build_frame(cand, pre.sensor_origin, cfg)
        warnings += frame_warn
    raw_s, raw_w, raw_dr = fit.to_local(tread_all)

    # optional statistical outlier removal (applied to the tread band only; reported, never silent)
    tread = tread_all
    n_sor_removed = 0
    if sor_enabled:
        keep = statistical_outlier_mask(tread_all, sor["k"], sor["std_ratio"])
        tread = tread_all[keep]
        n_sor_removed = int((~keep).sum())
        if n_sor_removed > 0.02 * len(tread_all):
            warnings.append(f"outlier filter removed {n_sor_removed} points ({100 * n_sor_removed / len(tread_all):.1f}%); "
                            "check it is not eating groove-bottom points (compare depth_by_stage in the report)")
    s, w, dr = fit.to_local(tread)

    a = cfg["analysis"]
    _p(0.45, "Estimating the reference surface")
    rcfg = dict(a["reference"])
    first_cfg = {**rcfg, "land_sigma_k": rcfg.get("first_pass_sigma_k", rcfg["land_sigma_k"])}
    ref = fit_reference(w, dr, first_cfg, s)
    if a["cell_mm"] == "auto":
        cell_m = choose_cell_m(s, w, a["target_points_per_cell"], a["cell_min_mm"] * 1e-3, a["cell_max_mm"] * 1e-3)
    else:
        cell_m = float(a["cell_mm"]) * 1e-3
    hm = build_heightmap(s, w, dr, cell_m, cfg["reconstruction"]["min_points_per_cell"])
    z = smooth_nan(hm.z, a["smoothing_sigma_cells"])
    _p(0.65, "Detecting grooves")
    occ = hm.count[hm.count > 0]
    sigma_cell_mm = ref.sigma_land_m * 1e3 / np.sqrt(max(float(np.median(occ)), 1.0))
    gcfg = dict(a["groove"])
    thr_eff = max(gcfg["threshold_mm"], gcfg["min_threshold_sigma"] * sigma_cell_mm)
    if thr_eff > gcfg["threshold_mm"] + 1e-9:
        warnings.append(f"groove threshold raised from {gcfg['threshold_mm']} to {thr_eff:.2f} mm "
                        f"(= {gcfg['min_threshold_sigma']} x per-cell noise {sigma_cell_mm:.2f} mm) to avoid noise-induced false grooves; "
                        "shallow grooves below this are NOT detectable with this data")
        gcfg["threshold_mm"] = thr_eff
    grooves, gmask, D = detect_grooves(hm, ref, gcfg, z)
    # Groove-masked refinement: refit the reference WITHOUT the points that fall in detected groove cells (dilated
    # by one cell), so groove bottoms cannot pull the reference down (matters when depth is only a few sigma).
    from scipy import ndimage
    ii, jj = hm.index(s, w)
    inb = (ii >= 0) & (jj >= 0) & (ii < hm.shape[0]) & (jj < hm.shape[1])
    for _ in range(int(rcfg.get("masking_iterations", 2))):
        if not gmask.any():
            break
        excl = np.zeros(len(s), bool)
        excl[inb] = ndimage.binary_dilation(gmask, iterations=1)[ii[inb], jj[inb]]
        if (~excl).sum() < 1000:
            break
        try:
            ref = fit_reference(w[~excl], dr[~excl], rcfg, s[~excl])
        except ValueError:
            break
        grooves, gmask, D = detect_grooves(hm, ref, gcfg, z)
    if a["smoothing_sigma_cells"] > 0:
        warnings.append(f"height-map smoothing sigma={a['smoothing_sigma_cells']} cells is ON; depths may be reduced")
    if not any(g.kind == "longitudinal" for g in grooves):
        warnings.append("no longitudinal grooves detected: either the tread is not resolved at this noise/density "
                        f"(land noise {ref.sigma_land_m * 1e3:.2f} mm, ~{sigma_cell_mm:.2f} mm per cell, effective threshold "
                        f"{gcfg['threshold_mm']:.2f} mm) or segmentation/axis parameters are wrong")
    _p(0.82, "Measuring density, noise and resolvability")
    spacing = dens.nn_spacing(tread)
    dstats = dens.density_stats(hm, len(tread))
    noise_cell = dens.land_cell_noise(hm, D, gmask, 0.5e-3 + ref.sigma_land_m)
    resolv = dens.groove_resolvability(grooves, hm, ref.sigma_land_m, dstats["effective_spacing_mm"], cfg["density"])

    _p(0.92, "Reconstructing the surface")
    mesh = heightfield_mesh(hm, fit, z, D, cfg["reconstruction"]["edge_jump_mm"] * 1e-3)

    # RAW vs FILTERED vs RECONSTRUCTED comparison of the depth of each groove
    depth_raw = _per_groove_point_depths(grooves, hm, ref, raw_s, raw_w, raw_dr)
    depth_filt = _per_groove_point_depths(grooves, hm, ref, s, w, dr)
    by_stage = [{"groove_id": g.id, "kind": g.kind, "raw_points_mm": r, "filtered_points_mm": f,
                 "reconstructed_mm": g.depth_m * 1e3} for g, r, f in zip(grooves, depth_raw, depth_filt)]

    long = dep.longitudinal_by_position(grooves)
    meta = describe_scan(scan_id, pre, n_frames, target=fit.to_world(np.array([0.]), np.array([0.]), np.array([0.]))[0],
                         density_per_cm2=dstats["density_per_cm2_mean"])
    meta.n_points = int(len(tread))
    land_w = w[(dr - ref(w, s)) > -ref.sigma_land_m * 2.5]
    report = {
        "tire_id": tire_id, "scan_id": scan_id,
        "mean_tread_depth_mm": dep.depth_statistics(long)["mean_mm"],
        "min_tread_depth_mm": dep.depth_statistics(long)["min_mm"],
        "max_tread_depth_mm": dep.depth_statistics(long)["max_mm"],
        "median_tread_depth_mm": dep.depth_statistics(long)["median_mm"],
        "depth_statistics_longitudinal": dep.depth_statistics(long),
        "depth_statistics_lateral": dep.depth_statistics(grooves, ("lateral",)),
        "depth_distribution": dep.cell_depth_distribution(D, gmask),
        "grooves": [dict(g.summary(), position_index=(long.index(g) + 1 if g in long else None)) for g in grooves],
        "geometry": {
            "fitted_radius_mm": fit.radius * 1e3, "outer_diameter_mm": (2 * (fit.radius + float(ref(np.array([0.0]), np.array([0.0]))[0])) * 1e3) if radius_ok else None,
            "radius_determined": radius_ok,
            "tread_land_width_mm": float((land_w.max() - land_w.min()) * 1e3) if land_w.size else None,
            "axis": fit.axis.tolist(), "center": fit.center.tolist(), "fit_rms_mm": fit.rms * 1e3,
            "arc_covered_mm": float((s.max() - s.min()) * 1e3), "width_covered_mm": float((w.max() - w.min()) * 1e3),
            "note": "Radius/diameter are from a partial-arc cylinder fit of the land surface; accuracy is not validated.",
        },
        "reference_surface": {"method": ref.method, "sigma_land_mm": ref.sigma_land_m * 1e3, "n_land_points": ref.n_land},
        "density": {**spacing, **dstats, **noise_cell},
        "resolvability": resolv,
        "depth_by_stage": by_stage,
        "segmentation": seg_info, "preprocess": pre_info,
        "n_points": {"input": len(pc), "tire_candidate": len(cand), "tread_band": len(tread_all),
                     "analysed": len(tread), "removed_by_outlier_filter": n_sor_removed},
        "scan_metadata": meta.to_dict(),
        "config": cfg, "warnings": warnings,
    }
    res = AnalysisResult(cfg, tire_id, scan_id, fit, tread, tread_all, s, w, dr, ref, hm, z, D, grooves, gmask,
                         mesh, report, pre.sensor_origin)
    if out_dir is not None and export:
        export_result(res, out_dir)
    return res


def export_result(res: AnalysisResult, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{res.tire_id}_{res.scan_id}"
    meta = {"tire_id": res.tire_id, "scan_id": res.scan_id, "units": "metre",
            "mean_tread_depth_mm": f"{res.report['mean_tread_depth_mm']:.3f}" if res.report["mean_tread_depth_mm"] is not None else "n/a"}
    v, f, col, depth = res.mesh
    # point-level depth + radial normals for the point cloud
    d_pts = res.ref(res.w, res.s) - res.dr
    th = res.s / res.fit.radius + res.fit.theta0
    nrm = np.cos(th)[:, None] * res.fit.e1 + np.sin(th)[:, None] * res.fit.e2
    paths = {
        "points_ply": writers.write_ply_points(out / f"{stem}_points.ply", res.tire_xyz, nrm,
                                              depth_colors(d_pts), {"depth_mm": d_pts * 1e3}, meta),
        "mesh_ply": writers.write_ply_mesh(out / f"{stem}_mesh.ply", v, f, None, col, {"depth_mm": depth * 1e3}, meta),
        "mesh_stl": writers.write_stl(out / f"{stem}_mesh.stl", v, f, stem),
        "mesh_obj": writers.write_obj(out / f"{stem}_mesh.obj", v, f, writers.vertex_normals(v, f), meta),
        "report_json": rep.write_json(out / f"{stem}_report.json", res.report),
        "grooves_csv": rep.write_csv(out / f"{stem}_grooves.csv", res.report["grooves"]),
    }
    from .viewer import plots

    plots.plot_depth_map(out / f"{stem}_depth_map.png", res.hm, res.D, res.grooves, title=f"{stem} depth map")
    if res.longitudinal():
        sc = float(np.median(res.s))
        plots.plot_cross_section(out / f"{stem}_cross_section.png", res.s, res.w, res.dr, res.ref, sc,
                                 z_filtered=res.z, hm=res.hm, title=f"{stem}: raw points vs height-map at s={sc * 1e3:.0f} mm")
        paths["depth_map_png"] = out / f"{stem}_depth_map.png"
        paths["cross_section_png"] = out / f"{stem}_cross_section.png"
    return {k: str(p) for k, p in paths.items()}
