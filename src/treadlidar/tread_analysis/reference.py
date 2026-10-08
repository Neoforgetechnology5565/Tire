"""Robust estimate of the local tread reference ("unworn") surface r_ref(w).

Never the highest single point: land points are classified by iterative asymmetric trimming
(reject points BELOW the surface), so groove bottoms are excluded from the reference.

Methods
-------
global_poly : one low-order polynomial in w (captures the crown curvature)
rib_local   : a straight line fitted per rib (contiguous land region), interpolated across grooves;
              follows uneven wear between ribs
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ReferenceSurface:
    method: str
    w_knots: np.ndarray          # piecewise-linear knots (rib_local) or sampling grid (global_poly)
    r_knots: np.ndarray
    sigma_land_m: float          # robust std of land points about the reference (noise + roughness)
    n_land: int
    coef: np.ndarray = None
    bow: np.ndarray = None       # (b1, b2): circumferential correction b1*s + b2*s^2 (absorbs cylinder-fit error)

    def lateral(self, w):
        w = np.asarray(w, float)
        if self.method == "global_poly":
            return np.polyval(self.coef, np.clip(w, self.w_knots[0], self.w_knots[-1]))
        return np.interp(w, self.w_knots, self.r_knots)

    def bow_at(self, s):
        if self.bow is None:
            return 0.0
        s = np.asarray(s, float)
        return self.bow[0] * s + self.bow[1] * s * s

    def __call__(self, w, s=None):
        """Reference radial height at lateral position w (and circumferential s, if given)."""
        r = self.lateral(w)
        return r if s is None else r + self.bow_at(s)

    def on_grid(self, s_centres, w_centres):
        """(Ns, Nw) reference on a regular grid."""
        return self.lateral(w_centres)[None, :] + np.asarray(self.bow_at(s_centres))[:, None]


def _mad_sigma(x):
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def _envelope(w, dr, bin_m, q, min_pts):
    edges = np.arange(w.min(), w.max() + bin_m, bin_m)
    b = np.clip(np.digitize(w, edges) - 1, 0, len(edges) - 2)
    wc, ev = [], []
    for i in np.unique(b):
        sel = b == i
        if sel.sum() >= min_pts:
            wc.append(w[sel].mean())
            ev.append(np.quantile(dr[sel], q))
    return np.array(wc), np.array(ev)


def _fit_lateral(w: np.ndarray, dr: np.ndarray, cfg: dict):
    """Lateral reference r(w) from all points (w, dr in metres). Returns (ReferenceSurface, land_mask)."""
    bin_m = cfg["w_bin_mm"] * 1e-3
    deg = int(cfg["poly_degree"])
    wc, ev = _envelope(w, dr, bin_m, cfg["envelope_quantile"], cfg["min_bin_points"])
    if len(wc) < deg + 2:
        raise ValueError("not enough lateral coverage to fit a reference surface")
    # stage 1: asymmetric robust polynomial through the upper envelope (groove bins are rejected)
    keep = np.ones(len(wc), bool)
    for _ in range(10):
        coef = np.polyfit(wc[keep], ev[keep], deg)
        res = ev - np.polyval(coef, wc)
        tol = max(cfg["land_tol_min_mm"] * 1e-3, 3 * _mad_sigma(res[keep]))
        new = (res > -tol) & (res < 3 * tol)
        if new.sum() < deg + 2 or (new == keep).all():
            break
        keep = new
    # stage 2: land = points within tol below the reference. The noise level is estimated ONLY from
    # points above the reference (half-normal median), which grooves cannot contaminate; tol is
    # clamped so the estimate cannot run away into the groove population when noise ~ groove depth.
    tol_min, tol_max = cfg["land_tol_min_mm"] * 1e-3, cfg["land_tol_max_mm"] * 1e-3
    tol = min(max(cfg["land_tol_init_mm"] * 1e-3, tol_min), tol_max)
    sig = np.nan
    for _ in range(int(cfg["iterations"])):
        res = dr - np.polyval(coef, np.clip(w, wc.min(), wc.max()))
        land = (res > -tol) & (res < 3 * tol)
        if land.sum() < 10 * (deg + 1):
            break
        coef = np.polyfit(w[land], dr[land], deg)
        res = dr - np.polyval(coef, np.clip(w, wc.min(), wc.max()))
        up = res[(res > 0) & (res < 4 * tol_max)]
        if up.size < 20:
            break
        sig = float(np.median(up) / 0.6745)
        tol = float(np.clip(cfg["land_sigma_k"] * sig, tol_min, tol_max))
    res = dr - np.polyval(coef, np.clip(w, wc.min(), wc.max()))
    land = (res > -tol) & (res < 3 * tol)
    sigma = float(sig) if np.isfinite(sig) else float(_mad_sigma(res[land]))
    wg = np.linspace(w.min(), w.max(), 200)
    ref = ReferenceSurface("global_poly", wg, np.polyval(coef, wg), sigma, int(land.sum()), coef)
    if cfg["method"] == "rib_local":
        ref = _rib_local(w, dr, land, bin_m, ref, cfg)
    return ref, land


def _rib_local(w, dr, land, bin_m, base: ReferenceSurface, cfg) -> ReferenceSurface:
    edges = np.arange(w.min(), w.max() + bin_m, bin_m)
    b = np.clip(np.digitize(w, edges) - 1, 0, len(edges) - 2)
    nb = len(edges) - 1
    tot = np.bincount(b, minlength=nb)
    lan = np.bincount(b[land], minlength=nb)
    land_bin = (tot >= cfg["min_bin_points"]) & (lan >= 0.3 * np.maximum(tot, 1))
    # contiguous runs of land bins = ribs
    knots_w, knots_r = [], []
    i = 0
    while i < nb:
        if not land_bin[i]:
            i += 1
            continue
        j = i
        while j + 1 < nb and land_bin[j + 1]:
            j += 1
        sel = land & (b >= i) & (b <= j)
        if sel.sum() >= 20 and j > i:
            c = np.polyfit(w[sel], dr[sel], 1)
            w0, w1 = w[sel].min(), w[sel].max()
            knots_w += [w0, w1]
            knots_r += list(np.polyval(c, [w0, w1]))
        i = j + 1
    if len(knots_w) < 2:
        return base
    order = np.argsort(knots_w)
    return ReferenceSurface("rib_local", np.array(knots_w)[order], np.array(knots_r)[order],
                            base.sigma_land_m, base.n_land)


def _s_envelope_bow(s, dr, bin_m=0.005, q=0.75, min_pts=8):
    """Initial circumferential bow from the upper envelope along s (robust to grooves)."""
    edges = np.arange(s.min(), s.max() + bin_m, bin_m)
    b = np.clip(np.digitize(s, edges) - 1, 0, len(edges) - 2)
    sc, ev = [], []
    for i in np.unique(b):
        m = b == i
        if m.sum() >= min_pts:
            sc.append(s[m].mean())
            ev.append(np.quantile(dr[m], q))
    sc, ev = np.array(sc), np.array(ev)
    if len(sc) < 6:
        return np.zeros(2)
    keep = np.ones(len(sc), bool)
    for _ in range(8):
        c = np.polyfit(sc[keep], ev[keep], 2)
        res = ev - np.polyval(c, sc)
        tol = max(1e-3, 3 * _mad_sigma(res[keep]))
        new = (res > -tol) & (res < 3 * tol)
        if new.sum() < 5 or (new == keep).all():
            break
        keep = new
    return np.array([c[1], c[0]])           # b1, b2 (constant term is absorbed by the lateral polynomial)


def fit_reference(w: np.ndarray, dr: np.ndarray, cfg: dict, s: np.ndarray = None) -> ReferenceSurface:
    """Robust local unworn-tread reference surface r_ref(w, s) = r_lat(w) + b1*s + b2*s^2.

    The bow term (disabled if ``s`` is None or cfg['bow_correction'] is False) absorbs the error of a
    cylinder fitted to a short arc (radius/centre/tilt), which otherwise leaves a circumferential
    sag of up to ~1 mm per 5% radius error over a 160 mm patch.
    """
    if s is None or not cfg.get("bow_correction", True):
        return _fit_lateral(w, dr, cfg)[0]
    bow = _s_envelope_bow(s, dr)
    ref = None
    for _ in range(3):
        bw = bow[0] * s + bow[1] * s * s
        ref, land = _fit_lateral(w, dr - bw, cfg)
        resid = dr - ref.lateral(w)
        A = np.column_stack([s[land], s[land] ** 2])
        sol, *_ = np.linalg.lstsq(A, resid[land], rcond=None)
        if np.abs(sol - bow).max() < 1e-6 and np.abs(sol[0]) < 1e-9:
            bow = sol
            break
        bow = sol
    bw = bow[0] * s + bow[1] * s * s
    ref, land = _fit_lateral(w, dr - bw, cfg)
    ref.bow = bow
    return ref
