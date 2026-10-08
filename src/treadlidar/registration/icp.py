"""Scan registration (point-to-point ICP, trimmed) for accumulating several scans.

ICP is estimated on a sub-sample for speed, but the resulting transform is applied to ALL
points, so tread detail is never discarded. For moving-sensor operation use Point-LIO/FAST-LIO2
poses instead (see docs/LIO_INTEGRATION.md); this module is the stationary-test fallback.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from scipy.spatial import cKDTree

from ..types import PointCloud


def rigid_fit(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ D @ U.T
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = cd - R @ cs
    return T


def icp(src: np.ndarray, dst: np.ndarray, init: Optional[np.ndarray] = None, max_iter: int = 60,
        max_corr: float = 0.05, trim: float = 0.9, tol: float = 1e-7, max_pts: int = 30000,
        rng_seed: int = 0):
    """Align ``src`` to ``dst``. Returns (T, rmse, fitness, converged)."""
    rng = np.random.default_rng(rng_seed)
    s = src if len(src) <= max_pts else src[rng.choice(len(src), max_pts, replace=False)]
    tree = cKDTree(dst)
    T = np.eye(4) if init is None else init.copy()
    prev = np.inf
    rmse, fit, ok = np.inf, 0.0, False
    for _ in range(max_iter):
        p = s @ T[:3, :3].T + T[:3, 3]
        d, i = tree.query(p, distance_upper_bound=max_corr)
        m = np.isfinite(d)
        if m.sum() < 10:
            break
        keep = np.flatnonzero(m)
        if trim < 1.0:
            keep = keep[np.argsort(d[keep])[: max(10, int(trim * len(keep)))]]
        dT = rigid_fit(p[keep], dst[i[keep]])
        T = dT @ T
        rmse = float(np.sqrt(np.mean(d[keep] ** 2)))
        fit = len(keep) / len(s)
        if abs(prev - rmse) < tol:
            ok = True
            break
        prev = rmse
    return T, rmse, fit, ok


def register_scans(clouds: List[PointCloud], reference_index: int = 0, **icp_kw):
    """Register all clouds to ``clouds[reference_index]``; return merged cloud and per-scan diagnostics."""
    ref = clouds[reference_index]
    out, diag = [], []
    for k, c in enumerate(clouds):
        if k == reference_index:
            out.append(c)
            diag.append({"scan": k, "T": np.eye(4).tolist(), "rmse_m": 0.0, "fitness": 1.0, "converged": True})
            continue
        T, rmse, fit, ok = icp(c.xyz, ref.xyz, **icp_kw)
        out.append(c.transformed(T))
        diag.append({"scan": k, "T": T.tolist(), "rmse_m": rmse, "fitness": fit, "converged": ok})
    return PointCloud.concat(out), diag
