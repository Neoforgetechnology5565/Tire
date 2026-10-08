"""Sensor characterisation on simple physical targets (no tire needed).

plane_noise : scan a flat, matte, rigid target (e.g. a ground board) -> range noise, point spacing, density
step_height : scan a stepped target of KNOWN heights (stacked gauge blocks / machined steps) ->
              how well the L2 resolves millimetre steps at your working distance and surface material.
These two experiments answer "can the L2 physically resolve mm-scale relief" directly, and their
numbers should be compared with the tire results.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def fit_plane(P: np.ndarray, iters: int = 300, tol: float = 0.004, seed: int = 0):
    """RANSAC then least-squares plane. Returns (normal, point_on_plane, inlier_mask)."""
    rng = np.random.default_rng(seed)
    best, bi = None, None
    for _ in range(iters):
        a, b, c = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n /= ln
        m = np.abs((P - a) @ n) <= tol
        if bi is None or m.sum() > bi.sum():
            best, bi = (n, a), m
    Q = P[bi]
    c = Q.mean(0)
    n = np.linalg.svd(Q - c, full_matrices=False)[2][-1]
    return n, c, np.abs((P - c) @ n) <= tol


def plane_noise(P: np.ndarray, tol: float = 0.01) -> dict:
    """Range-noise metrics of a flat target. ``tol`` selects plane inliers (set > 4 sigma)."""
    n, c, inl = fit_plane(P, tol=tol)
    Q = P[inl]
    res = (Q - c) @ n
    span = Q - Q.mean(0)
    ax = np.linalg.svd(span, full_matrices=False)[2]
    d, _ = cKDTree(Q).query(Q, k=2)
    # occupied-cell area (robust for any outline; a bounding box overestimates rotated rectangles)
    cell = max(3 * float(np.median(d[:, 1])), 1e-3)
    uv = np.column_stack([span @ ax[0], span @ ax[1]])
    ij = np.floor((uv - uv.min(0)) / cell).astype(np.int64)
    area = len(np.unique(ij[:, 0] * (ij[:, 1].max() + 1) + ij[:, 1])) * cell * cell
    return {"n_points": int(len(Q)), "noise_std_mm": float(res.std(ddof=1) * 1e3),
            "noise_mad_mm": float(1.4826 * np.median(np.abs(res - np.median(res))) * 1e3),
            "peak_to_peak_mm": float(np.ptp(res) * 1e3),
            "nn_spacing_median_mm": float(np.median(d[:, 1]) * 1e3),
            "density_per_cm2": float(len(Q) / (area * 1e4)) if area > 0 else float("nan"),
            "mean_distance_m": float(np.linalg.norm(Q.mean(0)))}


def step_height(P: np.ndarray, split_axis: np.ndarray = None, edge_exclusion_m: float = 0.004, tol: float = 0.02) -> dict:
    """Height of a single step between two parallel planes.

    The points are split by a coordinate along ``split_axis`` (default: the in-plane principal axis);
    a common plane normal is fitted, then the offset between the two half-planes is the step height
    (edge band +-``edge_exclusion_m`` is excluded to avoid mixed-pixel returns).
    Returns step_mm (signed, + = second half is farther along the normal) with a bootstrap-free
    standard error from the per-side scatter.
    """
    n, c, inl = fit_plane(P, tol=tol)
    Q = P[inl] - c
    # in-plane axes
    if split_axis is None:
        u = np.linalg.svd(Q - Q.mean(0), full_matrices=False)[2][0]
    else:
        u = np.asarray(split_axis, float)
    u = u - (u @ n) * n
    u /= np.linalg.norm(u)
    t = Q @ u
    h = Q @ n
    mid = np.median(t)
    a, b = t < mid - edge_exclusion_m, t > mid + edge_exclusion_m
    if a.sum() < 20 or b.sum() < 20:
        raise ValueError("not enough points on both sides of the step")
    # level each side with its own slope along u so a tilted target does not bias the step
    ca = np.polyfit(t[a], h[a], 1)
    cb = np.polyfit(t[b], h[b], 1)
    step = np.polyval(cb, mid) - np.polyval(ca, mid)
    ra, rb = h[a] - np.polyval(ca, t[a]), h[b] - np.polyval(cb, t[b])
    se = float(np.sqrt(ra.var(ddof=2) / a.sum() + rb.var(ddof=2) / b.sum()))
    return {"step_mm": float(step * 1e3), "std_error_mm": se * 1e3,
            "noise_each_side_mm": [float(ra.std() * 1e3), float(rb.std() * 1e3)],
            "n_each_side": [int(a.sum()), int(b.sum())]}
