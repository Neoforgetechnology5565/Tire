"""Tread-depth measurement from the groove map."""
from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np

from ..tread_analysis.grooves import Groove
from ..tread_analysis.heightmap import HeightMap
from ..tread_analysis.reference import ReferenceSurface


def depth_statistics(grooves: List[Groove], kinds=("longitudinal", "lateral", "other")) -> dict:
    d = np.array([g.depth_m for g in grooves if g.kind in kinds]) * 1e3
    if d.size == 0:
        return {"n_grooves": 0, "min_mm": None, "max_mm": None, "mean_mm": None, "median_mm": None, "std_mm": None}
    return {"n_grooves": int(d.size), "min_mm": float(d.min()), "max_mm": float(d.max()),
            "mean_mm": float(d.mean()), "median_mm": float(np.median(d)),
            "std_mm": float(d.std(ddof=1)) if d.size > 1 else 0.0}


def cell_depth_distribution(D: np.ndarray, groove_mask: np.ndarray, bins: int = 20) -> dict:
    v = D[groove_mask & np.isfinite(D)] * 1e3
    if v.size == 0:
        return {"n": 0}
    h, e = np.histogram(v, bins=bins)
    return {"n": int(v.size), "p05_mm": float(np.quantile(v, .05)), "p50_mm": float(np.quantile(v, .5)),
            "p95_mm": float(np.quantile(v, .95)), "hist_counts": h.tolist(), "hist_edges_mm": e.tolist()}


def measure_at(hm: HeightMap, ref: ReferenceSurface, D: np.ndarray, s_m: float, w_m: float,
               radius_m: float = 0.003) -> dict:
    """Depth at a user-selected (s, w) location: median over cells within ``radius_m``.

    ``reference_dr_mm`` and ``bottom_dr_mm`` are radial positions relative to the fitted tire
    radius; depth = reference - bottom. Choose the location inside the groove (use the viewer or
    the groove table centres); a window overlapping land reports a shallower median.
    """
    sc, wc = hm.cell_centers()
    S, W = np.meshgrid(sc, wc, indexing="ij")
    m = ((S - s_m) ** 2 + (W - w_m) ** 2 <= radius_m ** 2) & np.isfinite(D)
    if not m.any():
        return {"s_m": s_m, "w_m": w_m, "valid": False, "reason": "no data within window"}
    depth = float(np.median(D[m]))
    r_ref = float(ref(np.array([w_m]))[0])
    return {"s_m": s_m, "w_m": w_m, "valid": True, "n_cells": int(m.sum()), "n_points": int(hm.count[m].sum()),
            "depth_mm": depth * 1e3, "reference_dr_mm": r_ref * 1e3, "bottom_dr_mm": (r_ref - depth) * 1e3,
            "window_depth_min_mm": float(D[m].min() * 1e3), "window_depth_max_mm": float(D[m].max() * 1e3)}


def longitudinal_by_position(grooves: List[Groove]) -> List[Groove]:
    """Longitudinal grooves ordered by lateral position (increasing w = viewer's right)."""
    return sorted([g for g in grooves if g.kind == "longitudinal"], key=lambda g: g.w_center_m)


def groove_profile_along_length(g: Groove, D: np.ndarray, hm: HeightMap):
    """Depth vs. circumferential position along a longitudinal groove (for repeatability/uniformity)."""
    ii, jj = np.nonzero(g.mask)
    rows = np.unique(ii)
    s = hm.s0 + (rows + 0.5) * hm.cell
    d = np.array([np.nanmedian(D[r][g.mask[r]]) for r in rows])
    return s, d * 1e3
