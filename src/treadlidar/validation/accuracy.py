"""Accuracy and repeatability statistics against physical reference measurements."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import stats


def accuracy_metrics(ref_mm: Sequence[float], meas_mm: Sequence[float], confidence: float = 0.95) -> dict:
    """Error = measured - reference (negative => LiDAR under-reads depth)."""
    ref = np.asarray(ref_mm, float)
    meas = np.asarray(meas_mm, float)
    err = meas - ref
    n = len(err)
    out = {"n": int(n)}
    if n == 0:
        return out
    bias = float(err.mean())
    sd = float(err.std(ddof=1)) if n > 1 else float("nan")
    out.update({
        "bias_mm": bias, "std_mm": sd,
        "mae_mm": float(np.abs(err).mean()), "rmse_mm": float(np.sqrt((err ** 2).mean())),
        "max_abs_error_mm": float(np.abs(err).max()), "p95_abs_error_mm": float(np.quantile(np.abs(err), 0.95)),
        "frac_within_0p5mm": float((np.abs(err) <= 0.5).mean()),
        "frac_within_1p0mm": float((np.abs(err) <= 1.0).mean()),
    })
    if n > 1:
        h = stats.t.ppf(0.5 + confidence / 2, n - 1) * sd / np.sqrt(n)
        out["bias_ci_mm"] = [bias - float(h), bias + float(h)]
        out["limits_of_agreement_mm"] = [bias - 1.96 * sd, bias + 1.96 * sd]
        # the largest error magnitude expected for ~95% of single measurements (bias + 1.96 sd)
        out["loa95_halfwidth_mm"] = float(abs(bias) + 1.96 * sd)
    if n > 2 and np.ptp(ref) > 0:
        sl, ic, r, _, _ = stats.linregress(ref, meas)
        out.update({"slope": float(sl), "intercept_mm": float(ic), "r2": float(r * r)})
    out["errors_mm"] = err.tolist()
    return out


def repeatability_metrics(values_mm: np.ndarray) -> dict:
    """values_mm: (n_scans, n_locations) depth of the SAME physical locations over repeated scans."""
    v = np.atleast_2d(np.asarray(values_mm, float))
    n_scans, n_loc = v.shape
    if n_scans < 2:
        return {"n_scans": int(n_scans), "n_locations": int(n_loc), "error": "need >= 2 scans"}
    sd = v.std(axis=0, ddof=1)
    per = [{"location": int(i), "mean_mm": float(v[:, i].mean()), "std_mm": float(sd[i]),
            "min_mm": float(v[:, i].min()), "max_mm": float(v[:, i].max()),
            "range_mm": float(np.ptp(v[:, i]))} for i in range(n_loc)]
    pooled = float(np.sqrt(np.mean(sd ** 2)))
    return {"n_scans": int(n_scans), "n_locations": int(n_loc), "per_location": per,
            "pooled_std_mm": pooled,
            "repeatability_limit_mm": float(2.77 * pooled),      # ISO 5725 r = 1.96*sqrt(2)*s_r
            "max_range_mm": float(max(p["range_mm"] for p in per))}
