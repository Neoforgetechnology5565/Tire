"""Tire-local cylindrical frame: fit axis/centre/radius, unwrap points to (s, w, dr).

s  = arc length along the circumference [m]     (tread "longitudinal" direction)
w  = coordinate along the wheel axis [m]         (tread "lateral" direction)
dr = radial distance minus fitted radius [m]     (height of the surface; grooves are negative)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree


@dataclass
class CylinderFit:
    axis: np.ndarray        # unit
    center: np.ndarray      # a point on the axis
    radius: float
    e1: np.ndarray          # unit vectors perpendicular to the axis (e1, e2, axis right-handed)
    e2: np.ndarray
    theta0: float = 0.0     # reference angle (mean direction of the patch)
    w0: float = 0.0         # axial offset so that w=0 is the patch mean
    rms: float = float("nan")
    n_used: int = 0

    def to_local(self, P: np.ndarray):
        v = P - self.center
        a = v @ self.axis
        x, y = v @ self.e1, v @ self.e2
        rho = np.hypot(x, y)
        th = np.arctan2(y, x) - self.theta0
        th = (th + np.pi) % (2 * np.pi) - np.pi
        return self.radius * th, a - self.w0, rho - self.radius

    def to_world(self, s, w, dr) -> np.ndarray:
        th = np.asarray(s) / self.radius + self.theta0
        rho = self.radius + np.asarray(dr)
        return (self.center + (rho * np.cos(th))[:, None] * self.e1 + (rho * np.sin(th))[:, None] * self.e2
                + (np.asarray(w) + self.w0)[:, None] * self.axis)


def _basis(axis):
    axis = axis / np.linalg.norm(axis)
    t = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(axis, t)
    e1 /= np.linalg.norm(e1)
    return axis, e1, np.cross(axis, e1)


def estimate_normals(P: np.ndarray, k: int = 24):
    tree = cKDTree(P)
    _, nb = tree.query(P, k=k)
    Q = P[nb] - P[nb].mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", Q, Q)
    _, v = np.linalg.eigh(cov)
    return v[:, :, 0]


def axis_from_normals(normals: np.ndarray) -> np.ndarray:
    """Cylinder surface normals are perpendicular to the axis -> smallest eigenvector of sum(n n^T)."""
    M = normals.T @ normals
    w, v = np.linalg.eigh(M)
    return v[:, 0]


def _circle_init(xy):
    A = np.column_stack([2 * xy[:, 0], 2 * xy[:, 1], np.ones(len(xy))])
    b = (xy ** 2).sum(1)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    return sol[:2], float(np.sqrt(max(sol[2] + sol[0] ** 2 + sol[1] ** 2, 1e-12)))


def _refine(P, axis0, c0, R0, loss="soft_l1", f_scale=1e-3):
    axis0, e1, e2 = _basis(axis0)

    def unpack(p):
        ax = axis0 + p[0] * e1 + p[1] * e2
        ax /= np.linalg.norm(ax)
        c = c0 + p[2] * e1 + p[3] * e2
        return ax, c, p[4]

    def res(p):
        ax, c, R = unpack(p)
        v = P - c
        perp = v - np.outer(v @ ax, ax)
        return np.linalg.norm(perp, axis=1) - R

    sol = least_squares(res, [0, 0, 0, 0, R0], loss=loss, f_scale=f_scale, x_scale=[0.01, 0.01, 0.01, 0.01, 0.01])
    ax, c, R = unpack(sol.x)
    return ax, c, R, res(sol.x)


def _ransac_circle(xy: np.ndarray, tol: float, iters: int, rng, r_range=(0.1, 0.6)):
    """Vectorised RANSAC circle fit. Returns (centre (2,), radius, inlier_count)."""
    n = len(xy)
    idx = rng.integers(0, n, (iters, 3))
    p1, p2, p3 = xy[idx[:, 0]], xy[idx[:, 1]], xy[idx[:, 2]]
    a = p2 - p1
    b = p3 - p1
    d = 2 * (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    a2, b2 = (a ** 2).sum(1), (b ** 2).sum(1)
    cx = (b[:, 1] * a2 - a[:, 1] * b2) / d
    cy = (a[:, 0] * b2 - b[:, 0] * a2) / d
    c = p1 + np.column_stack([cx, cy])
    R = np.hypot(cx, cy)
    # plausible tire radii only -- rejects degenerate near-straight circles and small circles that
    # happen to fit flat sidewall sheets
    ok &= (R > r_range[0]) & (R < r_range[1])
    cnt = np.full(iters, -1)
    for i in np.flatnonzero(ok):
        cnt[i] = int((np.abs(np.hypot(xy[:, 0] - c[i, 0], xy[:, 1] - c[i, 1]) - R[i]) <= tol).sum())
    best = int(np.argmax(cnt))
    if cnt[best] < 0:
        return None, None, -1
    return c[best], float(R[best]), int(cnt[best])


def _candidate_axes(S, axis_hint, up, mode, normal_k):
    if axis_hint is not None:
        return [np.asarray(axis_hint, float)]
    cands = []
    if mode in ("auto", "normals"):
        # large-scale normals (neighbourhood >> groove width) so groove walls do not dominate
        rng = np.random.default_rng(1)
        cen = S[rng.choice(len(S), min(3000, len(S)), replace=False)]
        _, nb = cKDTree(S).query(cen, k=min(max(normal_k * 6, 150), len(S)))
        Q = S[nb] - S[nb].mean(axis=1, keepdims=True)
        _, v = np.linalg.eigh(np.einsum("nki,nkj->nij", Q, Q))
        cands.append(axis_from_normals(v[:, :, 0]))
    if mode in ("auto", "horizontal"):
        up = np.asarray(up, float) / np.linalg.norm(up)
        _, h1, h2 = _basis(up)
        for psi in np.radians(np.arange(0, 180, 2.0)):
            cands.append(np.cos(psi) * h1 + np.sin(psi) * h2)
    return cands


def fit_cylinder(P: np.ndarray, axis_hint=None, normal_k: int = 24, max_points: int = 40000,
                 seed: int = 0, up_fraction: float = 0.5, up=(0, 0, 1), axis_search: str = "auto",
                 ransac_tol_m: float = 0.008, half_width_m: float = None,
                 radius_range_m=(0.25, 0.65)) -> CylinderFit:
    """Fit a cylinder to a (partial, grooved, possibly contaminated) tire surface.

    1. candidate axes: the user hint, else large-scale surface normals and a sweep of horizontal axes;
    2. each candidate is scored by the inlier count of a RANSAC circle fit in the projection plane;
    3. robust least squares refines axis tilt / centre / radius; 4. a final fit on the upper
       ``up_fraction`` of radial residuals (land only) so groove bottoms do not bias the surface.
    The fit uses a random subset (``max_points``) for speed only; the frame is applied to every point.
    """
    rng = np.random.default_rng(seed)
    S = P if len(P) <= max_points else P[rng.choice(len(P), max_points, replace=False)]
    cands = _candidate_axes(S, axis_hint, up, axis_search, normal_k)
    sub = S if len(S) <= 2500 else S[rng.choice(len(S), 2500, replace=False)]
    mean = S.mean(0)
    best = (np.inf, None)
    tol_s = 0.75 * ransac_tol_m
    for ax in cands:
        axn, e1, e2 = _basis(ax)
        sc_pts = sub
        if half_width_m is not None:       # score on the tread only: sidewall sheets are planar and would win
            a = (sub - mean) @ axn
            sc_pts = sub[np.abs(a - np.median(a)) <= half_width_m]
            if len(sc_pts) < 200:
                continue
        xy = np.column_stack([(sc_pts - mean) @ e1, (sc_pts - mean) @ e2])
        c2, R2, cnt = _ransac_circle(xy, ransac_tol_m, 80, np.random.default_rng(seed), radius_range_m)
        if cnt < 0:
            continue
        # truncated-quadratic (M-estimator) cost: far more discriminating than an inlier count when
        # the visible arc is short (sagitta ~ RANSAC tolerance)
        res = np.hypot(xy[:, 0] - c2[0], xy[:, 1] - c2[1]) - R2
        cost = float(np.minimum(res ** 2, tol_s ** 2).mean())
        if cost < best[0]:
            best = (cost, axn)
    if best[1] is None:
        raise RuntimeError("cylinder fit failed: no circle within radius_range_m found for any candidate axis; "
                           "set segmentation.axis_hint or widen segmentation.radius_range_m")
    axis, e1, e2 = _basis(best[1])
    xy = np.column_stack([(S - mean) @ e1, (S - mean) @ e2])
    c2, R0, _ = _ransac_circle(xy, ransac_tol_m, 400, np.random.default_rng(seed + 1), radius_range_m)
    inl = np.abs(np.hypot(xy[:, 0] - c2[0], xy[:, 1] - c2[1]) - R0) <= ransac_tol_m
    if half_width_m is not None:
        # keep only the tread laterally: shoulders/sidewall lie lower and would bias the radius
        a = (S - mean) @ axis
        a_c = np.median(a[inl])
        lat = np.abs(a - a_c) <= half_width_m
        S, xy = S[lat], xy[lat]
        inl = inl[lat]
    c0 = mean + c2[0] * e1 + c2[1] * e2
    ax, c, R, _ = _refine(S[inl], axis, c0, R0)
    v = S - c
    r_all = np.linalg.norm(v - np.outer(v @ ax, ax), axis=1) - R
    sel = np.abs(r_all) <= 1.5 * ransac_tol_m
    ax, c, R, r = _refine(S[sel], ax, c, R)
    keep = r >= np.quantile(r, 1 - up_fraction)
    ax, c, R, r2 = _refine(S[sel][keep], ax, c, R, loss="linear")
    ax, e1, e2 = _basis(ax)
    v = P - c
    th = np.arctan2(v @ e2, v @ e1)
    th0 = float(np.arctan2(np.sin(th).mean(), np.cos(th).mean()))
    w0 = float((v @ ax).mean())
    return CylinderFit(ax, c, float(R), e1, e2, th0, w0, float(np.sqrt(np.mean(r2 ** 2))), int(keep.sum()))


def orient_frame(fit: CylinderFit, sensor_origin, up=(0, 0, 1)) -> CylinderFit:
    """Make +w point to the viewer's right (looking from the sensor to the tire, ``up`` = up)."""
    patch = fit.to_world(np.array([0.0]), np.array([0.0]), np.array([0.0]))[0]
    fwd = patch - np.asarray(sensor_origin, float)
    right = np.cross(fwd, np.asarray(up, float))
    if np.linalg.norm(right) < 1e-9 or fit.axis @ right >= 0:
        return fit
    # flip axis (and e2 to keep right-handedness; theta0 flips sign)
    return CylinderFit(-fit.axis, fit.center, fit.radius, fit.e1, -fit.e2, -fit.theta0, -fit.w0,
                       fit.rms, fit.n_used)
