"""Configuration: defaults + YAML overrides (deep-merged)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

import yaml

DEFAULTS = {
    "preprocess": {
        "min_range_m": 0.05,
        "max_range_m": 5.0,
        "outlier_removal": {"enabled": False, "k": 16, "std_ratio": 3.0},
        # Voxel downsampling is OFF and is never applied to the tread region.
        "voxel_size_m": 0.0,
    },
    "segmentation": {
        "roi": {"enabled": False, "center": [0.0, 0.0, 0.0], "radius_m": 3.0},
        "ground_removal": {"enabled": True, "dist_thresh_m": 0.01, "iterations": 400,
                           "max_tilt_deg": 20.0, "up": [0.0, 0.0, 1.0]},
        "cluster_voxel_m": 0.02,
        "cluster_min_points": 500,
        "cluster_select": "largest",        # largest | nearest
        "axis_hint": None,                  # e.g. [0, 1, 0] when the wheel axis is known (most robust)
        "axis_search": "horizontal",        # horizontal | normals | auto (ignored when axis_hint is set).
                                            # Horizontal = wheel axis perpendicular to analysis.view_up (level vehicle).
        "radius_range_m": [0.25, 0.50],     # plausible tire radius (set per vehicle class; passenger/SUV default)
        "cylinder_band_m": 0.03,            # keep |radial residual| <= band around fitted surface
        "tread_half_width_m": 0.12,         # keep |w| <= this (tread width / 2 + margin)
        "normal_k": 24,
        "fit_max_points": 40000,
    },
    "analysis": {
        "cell_mm": "auto",                  # height-map cell [mm] or "auto" (aims at target_points_per_cell)
        "target_points_per_cell": 4.0, "cell_min_mm": 0.5, "cell_max_mm": 5.0,
        "reference": {"method": "global_poly", "poly_degree": 2, "w_bin_mm": 2.0,
                      "envelope_quantile": 0.75, "land_tol_init_mm": 3.0,
                      "land_tol_min_mm": 1.0, "land_tol_max_mm": 4.0, "land_sigma_k": 2.5, "iterations": 8,
                      "min_bin_points": 5, "bow_correction": True,
                      "first_pass_sigma_k": 1.5, "masking_iterations": 2},
        "groove": {"threshold_mm": 1.6, "min_cells": 6, "close_iterations": 1,
                   "open_iterations": 0, "min_points_per_cell": 1,
                   "orientation_ratio": 3.0, "core_fraction": 0.7,
                   "fill_sigma_cells": 1.5, "detect_sigma_cells": 0.8,
                   "long_min_length_mm": 20.0, "lat_min_length_mm": 12.0,
                   "min_threshold_sigma": 3.0},
        "smoothing_sigma_cells": 0.0,       # 0 = no smoothing (default, fidelity first)
        "view_up": [0.0, 0.0, 1.0],
    },
    "reconstruction": {"method": "heightfield", "edge_jump_mm": 30.0, "min_points_per_cell": 1},
    "density": {"min_points_across_groove": 3.0, "min_depth_over_noise": 3.0, "max_groove_width_mm": 40.0},
    "validation": {"target_tight_mm": 0.5, "target_loose_mm": 1.0, "limited_mm": 2.0,
                   "min_pairs": 10, "min_scans": 3},
}


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Optional[str] = None, overrides: Optional[dict] = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(Path(path)) as f:
            cfg = _merge(cfg, yaml.safe_load(f) or {})
    if overrides:
        cfg = _merge(cfg, overrides)
    return cfg
