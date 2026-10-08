"""Point filtering. Defaults are conservative: nothing here removes tread detail unless enabled."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def range_filter(xyz, origin, rmin, rmax) -> np.ndarray:
    r = np.linalg.norm(xyz - np.asarray(origin), axis=1)
    return (r >= rmin) & (r <= rmax)


def statistical_outlier_mask(xyz: np.ndarray, k: int = 16, std_ratio: float = 3.0) -> np.ndarray:
    """True for inliers. Mean kNN distance must be < mean + std_ratio*std (global)."""
    if len(xyz) <= k + 1:
        return np.ones(len(xyz), bool)
    d, _ = cKDTree(xyz).query(xyz, k=k + 1)
    m = d[:, 1:].mean(axis=1)
    return m <= m.mean() + std_ratio * m.std()


def voxel_downsample(xyz: np.ndarray, voxel: float) -> np.ndarray:
    """Return indices of one point per voxel (first occurrence). NOT used on the tread region."""
    if voxel <= 0:
        return np.arange(len(xyz))
    key = np.floor(xyz / voxel).astype(np.int64)
    _, idx = np.unique(key, axis=0, return_index=True)
    return np.sort(idx)


def apply_preprocess(pc, cfg: dict):
    """Range filter + optional SOR. Returns (cloud, info)."""
    info = {"n_in": len(pc)}
    m = range_filter(pc.xyz, pc.sensor_origin, cfg["min_range_m"], cfg["max_range_m"])
    pc = pc.select(m)
    info["n_after_range"] = len(pc)
    sor = cfg["outlier_removal"]
    if sor["enabled"]:
        m = statistical_outlier_mask(pc.xyz, sor["k"], sor["std_ratio"])
        pc = pc.select(m)
    info["n_out"] = len(pc)
    return pc, info
