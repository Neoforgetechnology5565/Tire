"""Validation of LiDAR depths against physical reference measurements + repeatability + verdict.

Reference CSV (one row per measured longitudinal groove, numbered 1..N from the viewer's LEFT to
RIGHT as seen from the sensor):  groove_index,ref_depth_mm[,note]
Each scan must contain exactly N longitudinal grooves, else the scan is EXCLUDED and reported
(pairing grooves by position without a count match would silently compare the wrong grooves).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

import numpy as np

from . import accuracy, feasibility


def read_reference_csv(path) -> dict:
    ref = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ref[int(row["groove_index"])] = float(row["ref_depth_mm"])
    if not ref:
        raise ValueError("empty reference file")
    return ref


def validate(results: list, reference: dict, cfg_validation: dict, data_origin: str = "unknown") -> dict:
    n_ref = len(reference)
    idx = sorted(reference)
    ref_vec = np.array([reference[i] for i in idx], float)
    rows, used, excluded = [], [], []
    for r in results:
        long = r.longitudinal()
        if len(long) != n_ref:
            excluded.append({"scan_id": r.scan_id, "reason": f"detected {len(long)} longitudinal grooves, reference has {n_ref}"})
            continue
        depths = np.array([g.depth_m * 1e3 for g in long])
        used.append(depths)
        for k, i in enumerate(idx):
            rows.append({"scan_id": r.scan_id, "groove_index": i, "ref_mm": reference[i],
                         "lidar_mm": float(depths[k]), "error_mm": float(depths[k] - reference[i])})
    out = {"data_origin": data_origin, "n_scans_total": len(results), "n_scans_used": len(used),
           "excluded_scans": excluded, "pairs": rows}
    if not used:
        out["feasibility"] = feasibility.assess(None, None, None, cfg_validation, data_origin)
        return out
    M = np.vstack(used)                                   # (n_scans, n_grooves)
    acc = accuracy.accuracy_metrics([x["ref_mm"] for x in rows], [x["lidar_mm"] for x in rows])
    rep = accuracy.repeatability_metrics(M)
    # accuracy of the per-groove MEAN over scans (what averaging repeated scans can buy)
    acc_mean = accuracy.accuracy_metrics(ref_vec, M.mean(axis=0))
    out.update({"accuracy_single_scan": acc, "accuracy_scan_average": acc_mean, "repeatability": rep,
                "depth_matrix_mm": M.tolist(), "reference_mm": ref_vec.tolist(),
                "groove_indices": idx})
    resolv = results[0].report["resolvability"]
    out["feasibility"] = feasibility.assess(acc, rep, [x for x in resolv if x["kind"] == "longitudinal"],
                                            cfg_validation, data_origin)
    return out
