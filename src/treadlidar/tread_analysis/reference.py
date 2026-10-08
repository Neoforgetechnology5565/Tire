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

    def __call__(self, w):
        w = np.asarray(w, float)
        if self.method == "global_poly":
            return np.polyval(self.coef, np.clip(w, self.w_knots[0], self.w_knots[-1]))
        return np.interp(w, self.w_knots, self.r_knots)


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


def fit_reference(w: np.ndarray, dr: np.ndarray, cfg: dict) -> ReferenceSurface:
    """Fit the reference from all points (w, dr in metres)."""
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
    return ref


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
