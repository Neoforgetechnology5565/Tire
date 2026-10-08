"""Can the sensor resolve the tread? Point spacing, density, noise and per-groove resolvability."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .heightmap import HeightMap


def nn_spacing(P: np.ndarray, max_points: int = 60000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    S = P if len(P) <= max_points else P[rng.choice(len(P), max_points, replace=False)]
    d, _ = cKDTree(P).query(S, k=2)
    nn = d[:, 1]
    return {"nn_median_mm": float(np.median(nn) * 1e3), "nn_mean_mm": float(nn.mean() * 1e3),
            "nn_p90_mm": float(np.quantile(nn, 0.9) * 1e3)}


def density_stats(hm: HeightMap, n_points: int) -> dict:
    occ = hm.count > 0
    area_cm2 = occ.sum() * (hm.cell * 100) ** 2
    cell_cm2 = (hm.cell * 100) ** 2
    dens = hm.count[occ] / cell_cm2
    return {"occupied_area_cm2": float(area_cm2),
            "density_per_cm2_mean": float(n_points / area_cm2) if area_cm2 > 0 else float("nan"),
            "density_per_cm2_median_cell": float(np.median(dens)) if dens.size else float("nan"),
            "empty_cell_fraction_in_bbox": float(1 - occ.mean()),
            "effective_spacing_mm": float(10.0 / np.sqrt(n_points / area_cm2)) if area_cm2 > 0 else float("nan")}


def land_cell_noise(hm: HeightMap, D: np.ndarray, groove_mask: np.ndarray, land_tol_m: float) -> dict:
    """Per-cell scatter of points on land cells (upper bound on range noise: includes roughness/registration)."""
    sel = np.isfinite(hm.z_std) & (hm.count >= 4) & (~groove_mask) & (np.abs(np.nan_to_num(D, nan=1)) < land_tol_m)
    if sel.sum() < 5:
        return {"cell_noise_std_mm": float("nan"), "n_cells": int(sel.sum())}
    return {"cell_noise_std_mm": float(np.median(hm.z_std[sel]) * 1e3), "n_cells": int(sel.sum())}


def groove_resolvability(grooves, hm: HeightMap, sigma_land_m: float, spacing_eff_mm: float, cfg: dict):
    """Per-groove verdict: enough points across the width AND depth sufficiently above the noise."""
    out = []
    for g in grooves:
        width_mm = g.width_m * 1e3
        depth_mm = g.depth_m * 1e3
        n_across = width_mm / spacing_eff_mm if spacing_eff_mm > 0 else float("nan")
        n_core = max(g.n_points_core, 1)
        sig_depth_mm = sigma_land_m * 1e3 / np.sqrt(n_core)       # statistical depth uncertainty (random part only)
        snr = depth_mm / (sigma_land_m * 1e3) if sigma_land_m > 0 else float("inf")
        ok_w = n_across >= cfg["min_points_across_groove"]
        ok_d = snr >= cfg["min_depth_over_noise"]
        out.append({"groove_id": g.id, "kind": g.kind, "width_mm": width_mm, "depth_mm": depth_mm,
                    "points_across_width": float(n_across), "points_in_core": int(g.n_points_core),
                    "single_point_noise_mm": float(sigma_land_m * 1e3),
                    "depth_random_uncertainty_mm": float(sig_depth_mm),
                    "depth_over_noise": float(snr),
                    "resolved_width": bool(ok_w), "resolved_depth": bool(ok_d), "resolved": bool(ok_w and ok_d)})
    return out
