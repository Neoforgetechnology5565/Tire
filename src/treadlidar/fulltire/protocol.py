"""Automated measurement protocol on a full-circumference depth map.

Measures every longitudinal groove at N equally spaced positions around the tire, then summarises depth,
wear unevenness (across the tread and around the circumference) and a limit check.

The limit check is INDICATIVE unless a validated measurement uncertainty is supplied (from
``treadlidar validate`` on real data). With an uncertainty u it reports PASS (min - u >= limit),
FAIL (min + u < limit) or INDETERMINATE. It is an engineering aid, not a legal inspection result.
"""
from __future__ import annotations

import warnings
from typing import List, Optional

import numpy as np

from .stitch import FullTireMap

DEFAULT_PROTOCOL = {"n_positions": 8, "window_s_mm": 8.0, "min_cell_fraction": 0.5, "groove_threshold_mm": 0.8,
                    "min_groove_width_mm": 3.0, "limit_mm": 1.6, "uncertainty_mm": None, "expected_grooves": None}


def find_longitudinal_grooves(fm: FullTireMap, threshold_mm: float = 1.6, min_width_mm: float = 3.0) -> List[dict]:
    """Groove centres/widths from the lateral profile (median over the circumference, covered rows only)."""
    D = fm.D
    row_ok = np.isfinite(D).mean(axis=1) > 0.5
    if not row_ok.any():
        return []
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        P = np.nanmedian(D[row_ok], axis=0) * 1e3
    m = np.nan_to_num(P, nan=-1) > threshold_mm
    wc = fm.w_centers()
    out, j = [], 0
    while j < len(m):
        if not m[j]:
            j += 1
            continue
        k = j
        while k + 1 < len(m) and m[k + 1]:
            k += 1
        width = (k - j + 1) * fm.cell
        if width * 1e3 >= min_width_mm:
            w = P[j:k + 1] - threshold_mm
            out.append({"w_center_m": float(np.average(wc[j:k + 1], weights=np.clip(w, 1e-6, None))), "width_m": float(width),
                        "col0": j, "col1": k})
        j = k + 1
    for i, g in enumerate(out):
        g["groove_index"] = i + 1
    return out


def _window_value(fm, u_m, g, half_s_m, min_frac):
    h = int(round(half_s_m / fm.cell))
    i0 = int(round(u_m / fm.cell))
    rows = np.arange(i0 - h, i0 + h + 1) % fm.D.shape[0]
    c0 = g["col0"] + max(0, (g["col1"] - g["col0"]) // 4)
    c1 = g["col1"] - max(0, (g["col1"] - g["col0"]) // 4)
    blk = fm.D[np.ix_(rows, np.arange(c0, c1 + 1))]
    if np.isfinite(blk).mean() < min_frac:
        return float("nan"), int(np.isfinite(blk).sum())
    return float(np.nanmedian(blk) * 1e3), int(np.isfinite(blk).sum())


def run_protocol(fm: FullTireMap, cfg: Optional[dict] = None) -> dict:
    c = {**DEFAULT_PROTOCOL, **(cfg or {})}
    grooves = find_longitudinal_grooves(fm, c["groove_threshold_mm"], c["min_groove_width_mm"])
    C = fm.circumference_m
    pos_u = (np.arange(c["n_positions"]) * C / c["n_positions"]).tolist()
    table = []
    mat = np.full((len(grooves), c["n_positions"]), np.nan)
    for gi, g in enumerate(grooves):
        for k, u in enumerate(pos_u):
            v, n = _window_value(fm, u, g, c["window_s_mm"] * 1e-3 / 2, c["min_cell_fraction"])
            mat[gi, k] = v
            table.append({"groove_index": g["groove_index"], "position_index": k, "angle_deg": 360.0 * k / c["n_positions"],
                          "arc_mm": u * 1e3, "depth_mm": v, "n_cells": n, "measured": bool(np.isfinite(v))})
    ok = np.isfinite(mat)
    rep = {"circumference_mm": C * 1e3, "outer_diameter_mm": C / np.pi * 1e3,
           "grooves": [{k: v for k, v in g.items() if k not in ("col0", "col1")} for g in grooves],
           "protocol": c, "measurements": table, "coverage": fm.coverage(), "views": fm.view_info,
           "warnings": list(fm.warnings)}
    if not grooves or not ok.any():
        rep["summary"] = None
        rep["warnings"].append("no groove measurements could be made")
        return rep
    per_groove = []
    for gi, g in enumerate(grooves):
        v = mat[gi][ok[gi]]
        per_groove.append({"groove_index": g["groove_index"], "w_center_mm": g["w_center_m"] * 1e3,
                           "n_measured": int(v.size), "n_missing": int((~ok[gi]).sum()),
                           "min_mm": float(v.min()) if v.size else None, "mean_mm": float(v.mean()) if v.size else None,
                           "max_mm": float(v.max()) if v.size else None,
                           "around_range_mm": float(np.ptp(v)) if v.size else None})
    allv = mat[ok]
    imin = np.unravel_index(np.nanargmin(np.where(ok, mat, np.inf)), mat.shape)
    # unevenness across the tread at each position (needs >= 2 measured grooves)
    across = [float(np.ptp(mat[:, k][ok[:, k]])) for k in range(mat.shape[1]) if ok[:, k].sum() >= 2]
    shoulder = None
    if len(grooves) >= 3 and ok.any():
        outer = np.nanmean(np.where(ok[[0, -1]], mat[[0, -1]], np.nan))
        inner = np.nanmean(np.where(ok[1:-1], mat[1:-1], np.nan))
        shoulder = float(outer - inner)                       # negative = shoulders more worn than centre
    half = len(grooves) // 2
    lr = None
    if half >= 1:
        left = np.nanmean(np.where(ok[:half], mat[:half], np.nan))
        right = np.nanmean(np.where(ok[-half:], mat[-half:], np.nan))
        lr = float(left - right)
    u_unc, lim = c["uncertainty_mm"], c["limit_mm"]
    mn = float(allv.min())
    if u_unc is None:
        status, validated = ("PASS" if mn >= lim else "FAIL"), False
    else:
        status = "PASS" if mn - u_unc >= lim else ("FAIL" if mn + u_unc < lim else "INDETERMINATE")
        validated = True
    # A PASS is only meaningful if no groove can have been missed. Guard against the dangerous failure mode
    # "the most worn groove was not detected".
    guard = []
    if c["expected_grooves"] is not None and c["expected_grooves"] != len(grooves):
        guard.append(f"detected {len(grooves)} longitudinal grooves but {c['expected_grooves']} were expected")
    if c["expected_grooves"] is None:
        guard.append("groove count not verified (pass expected_grooves / --expected-grooves)")
    if c["groove_threshold_mm"] > 0.5 * lim:
        guard.append(f"groove detection floor {c['groove_threshold_mm']} mm is more than half the limit {lim} mm: "
                     "grooves near the limit may be invisible")
    if guard and status == "PASS":
        status = "INDETERMINATE"
    rep["warnings"] += [f"limit check guard: {g}" for g in guard]
    rep["summary"] = {
        "n_measurements": int(ok.sum()), "n_missing": int((~ok).sum()),
        "min_mm": mn, "min_at": {"groove_index": grooves[imin[0]]["groove_index"], "angle_deg": 360.0 * imin[1] / c["n_positions"]},
        "mean_mm": float(allv.mean()), "median_mm": float(np.median(allv)), "max_mm": float(allv.max()), "std_mm": float(allv.std(ddof=1)) if allv.size > 1 else 0.0,
        "per_groove": per_groove, "max_across_tread_range_mm": float(max(across)) if across else None,
        "shoulder_minus_centre_mm": shoulder, "left_minus_right_mm": lr,
        "limit_check": {"limit_mm": lim, "uncertainty_mm": u_unc, "status": status, "validated_uncertainty": validated,
                        "guards": guard,
                        "note": "indicative only: no validated measurement uncertainty supplied" if not validated else
                                "status accounts for the supplied uncertainty; not a legal inspection result"}}
    if not validated:
        rep["warnings"].append("limit check uses NO validated uncertainty (run treadlidar validate on real data and pass --uncertainty-mm)")
    if (~ok).any():
        rep["warnings"].append(f"{int((~ok).sum())} of {ok.size} protocol positions have insufficient data and are reported missing")
    return rep
