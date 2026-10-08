"""Closed-ring height-field mesh of the whole tread from a FullTireMap (no smoothing, no hole filling)."""
from __future__ import annotations

import numpy as np

from ..reconstruction.mesh import depth_colors
from .stitch import FullTireMap


def fulltire_mesh(fm: FullTireMap, edge_jump_m: float = 0.03, vmax_mm: float = 10.0):
    """Return (vertices, faces, colors, depth). Axis = +Y, tire centre at origin; radius at the tread centre = C/2pi.
    Faces wrap around the circumference; cells without data leave holes."""
    N, W = fm.D.shape
    R = fm.radius_eff_m
    valid = np.isfinite(fm.D)
    vid = -np.ones((N, W), np.int64)
    vid[valid] = np.arange(valid.sum())
    u = fm.u_centers()
    w = fm.w_centers()
    U, Wg = np.meshgrid(u, w, indexing="ij")
    rho = R + fm.crown[None, :] - np.where(valid, fm.D, 0.0)
    th = U / R
    X = rho * np.cos(th)
    Z = rho * np.sin(th)
    V = np.column_stack([X[valid], Wg[valid], Z[valid]])
    a = vid
    b = np.roll(vid, -1, axis=0)
    c = np.roll(np.roll(vid, -1, axis=0), -1, axis=1)
    d = np.roll(vid, -1, axis=1)
    ok = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    ok[:, -1] = False                                           # no wrap across the lateral direction
    z0 = np.where(valid, fm.D, 0.0)
    zs = np.stack([z0, np.roll(z0, -1, 0), np.roll(np.roll(z0, -1, 0), -1, 1), np.roll(z0, -1, 1)])
    ok &= (zs.max(0) - zs.min(0)) <= edge_jump_m
    a, b, c, d = a[ok], b[ok], c[ok], d[ok]
    F = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])]).astype(np.int64)
    depth = fm.D[valid]
    return V, F, depth_colors(depth, vmax_mm), depth
