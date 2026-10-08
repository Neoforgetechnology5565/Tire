"""Full-circumference (360 deg) depth map from several partial-arc views of a rotating wheel.

Set-up assumed (stationary sensor, wheel turned in steps, e.g. jacked up, marked with tape):
every view sees the same patch of space; the wheel angle differs. Each view is analysed on its own
(cylinder fit, reference surface, depth map D). Views are then merged in *tire-fixed arc coordinates*

    u = s - R_eff * wheel_angle          (mod C),   C = circumference

Why depth maps and not points: every view has its own reference surface (with bow/crown correction), so
D is the common currency; merging D never re-introduces the per-view cylinder-fit error.

Why a measured circumference: a ~30 deg arc cannot determine the radius to better than a few mm (=> tens
of mm of circumference). Give ``circumference_m`` (tape measure at the tread centre) or the nominal radius.

Nominal wheel angles may be refined (conservatively: high correlation, unique peak, >= 60 mm overlap) by cross-correlating the circumferential depth profile (lateral grooves)
of each new view with the map built so far. Uniform pitch patterns are ambiguous (the correlation repeats
every pitch), so the refinement window is limited and a low-confidence flag is raised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from ..tread_analysis.heightmap import HeightMap
from ..tread_analysis.reference import ReferenceSurface


@dataclass
class FullTireMap:
    circumference_m: float
    cell: float
    w0: float                       # lateral coordinate of column 0's lower edge [m]
    D: np.ndarray                   # (N_rows over u, N_cols over w): depth below reference [m], NaN = uncovered
    n: np.ndarray                   # number of contributing view-cells
    crown: np.ndarray               # (N_cols,) lateral reference shape [m], relative to its mid value
    view_info: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def radius_eff_m(self) -> float:
        return self.circumference_m / (2 * np.pi)

    def u_centers(self) -> np.ndarray:
        return (np.arange(self.D.shape[0]) + 0.5) * self.cell

    def w_centers(self) -> np.ndarray:
        return self.w0 + (np.arange(self.D.shape[1]) + 0.5) * self.cell

    def coverage(self) -> dict:
        rows = np.isfinite(self.D).any(axis=1)
        full = np.isfinite(self.D).mean(axis=1) > 0.5
        return {"rows_covered_fraction": float(rows.mean()), "rows_mostly_covered_fraction": float(full.mean()),
                "uncovered_arc_mm": float((~full).sum() * self.cell * 1e3)}

    def as_heightmap(self) -> HeightMap:
        """View as a HeightMap with z = -D and a zero reference, so groove code can be reused."""
        return HeightMap(self.cell, 0.0, self.w0, self.n.astype(float), -self.D, np.full_like(self.D, np.nan))

    def zero_reference(self) -> ReferenceSurface:
        w = self.w_centers()
        return ReferenceSurface("global_poly", np.array([w[0], w[-1]]), np.zeros(2), 0.0, 0, np.zeros(3))


def _group_median(rows, cols, vals, shape):
    flat = rows * shape[1] + cols
    order = np.argsort(flat, kind="stable")
    fs, vs = flat[order], vals[order]
    uniq, start, cnt = np.unique(fs, return_index=True, return_counts=True)
    out = np.full(shape[0] * shape[1], np.nan)
    num = np.zeros_like(out)
    for u, a, k in zip(uniq, start, cnt):
        out[u] = np.median(vs[a:a + k])
        num[u] = k
    return out.reshape(shape), num.reshape(shape)


def _view_samples(res, cell_valid=True):
    """Valid depth-map cells of one analysed view as (s, w, D) samples."""
    sc, wc = res.hm.cell_centers()
    S, W = np.meshgrid(sc, wc, indexing="ij")
    m = np.isfinite(res.D) & (res.hm.count > 0)
    return S[m], W[m], res.D[m]


def _profile(rows, cols, vals, n_rows, min_cols=3):
    """Mean depth over w per u-row from scattered samples (mean-removed later)."""
    sums = np.bincount(rows, weights=vals, minlength=n_rows)
    cnt = np.bincount(rows, minlength=n_rows)
    p = np.full(n_rows, np.nan)
    ok = cnt >= min_cols
    p[ok] = sums[ok] / cnt[ok]
    return p


def _circ_xcorr_shift(p_ref, p_new, max_shift, min_overlap):
    """Best integer shift k (rows) such that p_new(u+k) ~ p_ref(u); returns (k, corr, second_best_corr, overlap)."""
    n = len(p_ref)
    best = (0, -2.0, -2.0, 0)
    scores = {}
    for k in range(-max_shift, max_shift + 1):
        q = np.roll(p_new, k)
        m = np.isfinite(p_ref) & np.isfinite(q)
        ov = int(m.sum())
        if ov < min_overlap:
            continue
        a, b = p_ref[m] - p_ref[m].mean(), q[m] - q[m].mean()
        den = np.linalg.norm(a) * np.linalg.norm(b)
        scores[k] = (float(a @ b / den) if den > 1e-12 else -2.0, ov)
    if not scores:
        return best
    ks = sorted(scores, key=lambda k: scores[k][0], reverse=True)
    k0 = ks[0]
    # second best must be a different local maximum: at least 3 rows away
    second = next((scores[k][0] for k in ks[1:] if abs(k - k0) >= 3), -2.0)
    return k0, scores[k0][0], second, scores[k0][1]


def stitch_views(results: Sequence, angles_deg: Optional[Sequence[float]] = None, circumference_m: float = None,
                 cell_mm: float = 3.0, refine: bool = True, search_mm: float = 10.0, min_corr: float = 0.8,
                 blind_step_deg: Optional[float] = None, blind_search_mm: float = None,
                 min_overlap_mm: float = 60.0, common_frame: bool = False, min_margin: float = 0.1) -> FullTireMap:
    """Merge analysed views. ``results``: AnalysisResult list (fixed sensor, wheel rotated between views).

    angles_deg  : wheel rotation of each view from view 0 (+ = tread at the sensor moves downward / +s).
    blind_step_deg: if angles are unknown, assume views advance by this nominal step (+ search window).
    """
    warnings: List[str] = []
    n_views = len(results)
    if circumference_m is None:
        circumference_m = 2 * np.pi * float(np.median([r.fit.radius for r in results]))
        warnings.append("circumference_m not given: using the cylinder-fit radius, which is weakly determined by a short arc "
                        f"(2*pi*R = {circumference_m * 1e3:.0f} mm); measure the circumference with a tape")
    if angles_deg is None:
        if blind_step_deg is None:
            raise ValueError("give angles_deg, or blind_step_deg for a nominal constant step")
        angles_deg = [k * blind_step_deg for k in range(n_views)]
        search_mm = blind_search_mm or search_mm
        warnings.append("blind alignment: wheel angles were not provided; correlation of the lateral-groove pattern decides "
                        "(ambiguous for uniform pitch)")
    angles = np.asarray(angles_deg, float)
    if len(angles) != n_views:
        raise ValueError("angles_deg must have one entry per view")
    C = float(circumference_m)
    R = C / (2 * np.pi)
    g = cell_mm * 1e-3
    n_rows = int(round(C / g))
    g = C / n_rows                                            # exact tiling of the circumference

    # lateral alignment (w offsets) from longitudinal-groove centres, relative to view 0
    def centres(r):
        return np.array([x.w_center_m for x in r.longitudinal()])
    c0 = centres(results[0])
    dw = np.zeros(n_views)
    for i, r in enumerate(results):
        ci = centres(r)
        if common_frame:
            continue                       # all views already share one cylinder frame: no lateral offsets
        if i and len(ci) == len(c0) and len(c0) >= 2:
            dw[i] = float(np.median(c0 - ci))
        elif i:
            warnings.append(f"view {i}: groove count {len(ci)} != view 0 ({len(c0)}); lateral offset left at 0")

    samples = [_view_samples(r) for r in results]
    w_all = np.concatenate([s[1] + dw[i] for i, s in enumerate(samples)])
    w0 = float(w_all.min() - 0.5 * g)
    n_cols = int(np.ceil((w_all.max() - w0) / g)) + 1

    rows_l, cols_l, vals_l, info = [], [], [], []
    merged_profile = None
    deltas = np.zeros(n_views)
    for i, (s, w, d) in enumerate(samples):
        u0 = s * (R / results[i].fit.radius) - R * np.radians(angles[i])    # arc length on the measured circumference
        rows = np.floor(u0 / g).astype(np.int64) % n_rows
        cols = np.floor((w + dw[i] - w0) / g).astype(np.int64)
        shift_rows = 0
        ov = 0
        corr = second = float("nan")
        flagged = False
        if refine and i > 0 and merged_profile is not None:
            p_new = _profile(rows, cols, d, n_rows)
            k, corr, second, ov = _circ_xcorr_shift(merged_profile, p_new, int(round(search_mm * 1e-3 / g)), min_overlap=int(np.ceil(min_overlap_mm * 1e-3 / g)))
            if ov < int(np.ceil(min_overlap_mm * 1e-3 / g)):
                flagged = True
                warnings.append(f"view {i}: overlap with the map so far is < {min_overlap_mm:.0f} mm; refinement skipped, nominal angle "
                                f"{angles[i]:.1f} deg used. Use >= 25 % overlap between neighbouring views.")
            elif corr >= min_corr and second <= corr - min_margin:
                shift_rows = k
            else:
                flagged = True
                warnings.append(f"view {i}: refinement rejected (corr {corr:.2f}, runner-up {second:.2f}); nominal angle "
                                f"{angles[i]:.1f} deg kept (alignment then depends on the accuracy of the wheel angle, "
                                f"~{np.degrees(g / R):.1f} deg per cell).")
        rows = (rows + shift_rows) % n_rows
        deltas[i] = shift_rows * g
        rows_l.append(rows); cols_l.append(cols); vals_l.append(d)
        p = _profile(rows, cols, d, n_rows)
        if merged_profile is None:
            merged_profile = p
        else:
            merged_profile = np.where(np.isfinite(merged_profile), np.where(np.isfinite(p), 0.5 * (merged_profile + p), merged_profile), p)
        info.append({"view": i, "nominal_angle_deg": float(angles[i]), "refinement_mm": float(deltas[i] * 1e3),
                     "refined_angle_deg": float(angles[i] + np.degrees(deltas[i] / R)), "correlation": None if np.isnan(corr) else float(corr),
                     "runner_up": None if np.isnan(second) else float(second), "flagged": flagged, "dw_mm": float(dw[i] * 1e3),
                     "n_cells": int(len(d))})
    shape = (n_rows, n_cols)
    D, n = _group_median(np.concatenate(rows_l), np.concatenate(cols_l), np.concatenate(vals_l), shape)
    # lateral crown (mean of per-view lateral references on the global w grid), relative to the centre
    wc = w0 + (np.arange(n_cols) + 0.5) * g
    crowns = []
    for i, r in enumerate(results):
        wi = wc - dw[i]
        inside = (wi >= r.w.min()) & (wi <= r.w.max())
        c = np.where(inside, r.ref.lateral(np.clip(wi, r.w.min(), r.w.max())), np.nan)
        crowns.append(c - np.nanmedian(c))
    with np.errstate(all="ignore"):
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore", RuntimeWarning)
            crown = np.nanmean(np.vstack(crowns), axis=0)
    crown = np.where(np.isfinite(crown), crown, 0.0)
    fm = FullTireMap(C, g, w0, D, n, crown - crown[len(crown) // 2], info, warnings)
    cov = fm.coverage()
    if cov["uncovered_arc_mm"] > 0.5 * 1e3 * g:
        warnings.append(f"{cov['uncovered_arc_mm']:.0f} mm of the circumference is not covered (e.g. contact patch / missed angles): "
                        "measurements there are reported as missing, never interpolated")
    return fm
