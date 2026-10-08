"""Isolate the tire from the environment.

Stages (each optional via config): ROI crop -> ground-plane RANSAC removal -> voxel-occupancy
Euclidean clustering (labels mapped back to the FULL-resolution points) -> after a cylinder fit,
a band/width crop (see pipeline). Clustering uses a coarse occupancy grid only to *label* points;
no point is discarded by the grid itself.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def roi_mask(xyz, center, radius) -> np.ndarray:
    return np.linalg.norm(xyz - np.asarray(center, float), axis=1) <= radius


def ransac_plane(xyz, dist_thresh=0.01, iterations=400, seed=0, max_tilt_deg=None, up=(0, 0, 1)):
    """Largest plane (optionally near-horizontal). Returns (normal, d, inlier_mask) or None."""
    rng = np.random.default_rng(seed)
    n = len(xyz)
    if n < 100:
        return None
    best, best_cnt = None, 0
    up = np.asarray(up, float)
    for _ in range(iterations):
        a, b, c = xyz[rng.choice(n, 3, replace=False)]
        nrm = np.cross(b - a, c - a)
        ln = np.linalg.norm(nrm)
        if ln < 1e-9:
            continue
        nrm /= ln
        if max_tilt_deg is not None and abs(nrm @ up) < np.cos(np.radians(max_tilt_deg)):
            continue
        d = -nrm @ a
        cnt = int((np.abs(xyz @ nrm + d) <= dist_thresh).sum())
        if cnt > best_cnt:
            best, best_cnt = (nrm, d), cnt
    if best is None:
        return None
    nrm, d = best
    return nrm, d, np.abs(xyz @ nrm + d) <= dist_thresh


def cluster_labels(xyz: np.ndarray, voxel: float) -> np.ndarray:
    """Connected components (26-neighbourhood) of occupied voxels, mapped back to each point."""
    key = np.floor((xyz - xyz.min(0)) / voxel).astype(np.int64)
    dims = key.max(0) + 3
    grid = np.zeros(dims, bool)
    grid[key[:, 0] + 1, key[:, 1] + 1, key[:, 2] + 1] = True
    lab, _ = ndimage.label(grid, structure=np.ones((3, 3, 3)))
    return lab[key[:, 0] + 1, key[:, 1] + 1, key[:, 2] + 1]


def segment_tire(xyz: np.ndarray, cfg: dict, sensor_origin=(0, 0, 0)):
    """Return (indices into xyz of the tire candidate cluster, info dict)."""
    idx = np.arange(len(xyz))
    info = {"n_in": len(xyz)}
    roi = cfg["roi"]
    if roi["enabled"]:
        m = roi_mask(xyz[idx], roi["center"], roi["radius_m"])
        idx = idx[m]
    info["n_after_roi"] = len(idx)
    gr = cfg["ground_removal"]
    if gr["enabled"] and len(idx) > 100:
        res = ransac_plane(xyz[idx], gr["dist_thresh_m"], gr["iterations"],
                           max_tilt_deg=gr["max_tilt_deg"], up=gr["up"])
        if res is not None:
            idx = idx[~res[2]]
            info["ground_normal"] = res[0].tolist()
            info["n_ground_removed"] = int(res[2].sum())
    info["n_after_ground"] = len(idx)
    if len(idx) == 0:
        return idx, info
    lab = cluster_labels(xyz[idx], cfg["cluster_voxel_m"])
    counts = np.bincount(lab)
    counts[0] = 0
    valid = np.flatnonzero(counts >= cfg["cluster_min_points"])
    info["n_clusters"] = int(len(valid))
    if len(valid) == 0:
        return idx[:0], info
    if cfg["cluster_select"] == "nearest":
        dist = [np.linalg.norm(xyz[idx[lab == c]].mean(0) - np.asarray(sensor_origin)) for c in valid]
        pick = valid[int(np.argmin(dist))]
    else:
        pick = valid[int(np.argmax(counts[valid]))]
    idx = idx[lab == pick]
    info["n_cluster"] = int(len(idx))
    return idx, info
