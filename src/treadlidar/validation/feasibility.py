"""Turn measured evidence into RESULT A / B / C. Never fabricates: simulated or missing data cannot
produce a verdict about the sensor."""
from __future__ import annotations

from typing import Optional


def assess(validation: Optional[dict], repeatability: Optional[dict], resolvability: Optional[list],
           cfg: dict, data_origin: str = "unknown") -> dict:
    tight, loose, limited = cfg["target_tight_mm"], cfg["target_loose_mm"], cfg["limited_mm"]
    reasons, notes = [], []
    res = {"data_origin": data_origin, "targets_mm": {"tight": tight, "loose": loose}}
    if data_origin != "real":
        res.update(result="NOT_ASSESSED",
                   summary="Data origin is not 'real' (physical L2 + physical tire). No statement about the "
                           "Unitree L2 can be made from simulated/unknown data.")
        return res
    if not validation or validation.get("n", 0) < cfg["min_pairs"]:
        res.update(result="INCONCLUSIVE",
                   summary=f"Need >= {cfg['min_pairs']} paired reference/LiDAR measurements "
                           f"(have {0 if not validation else validation.get('n', 0)}).")
        return res
    if not repeatability or repeatability.get("n_scans", 0) < cfg["min_scans"] or "pooled_std_mm" not in repeatability:
        res.update(result="INCONCLUSIVE",
                   summary=f"Need >= {cfg['min_scans']} repeated scans of the same tire for repeatability.")
        return res
    loa = validation["loa95_halfwidth_mm"]
    rep = repeatability["pooled_std_mm"]
    res.update(loa95_halfwidth_mm=loa, repeatability_std_mm=rep, bias_mm=validation["bias_mm"])
    resolved_frac = None
    if resolvability:
        resolved_frac = sum(r["resolved"] for r in resolvability) / len(resolvability)
        res["resolved_groove_fraction"] = resolved_frac
        if resolved_frac < 1.0:
            notes.append(f"{(1 - resolved_frac) * 100:.0f}% of detected grooves are not resolved "
                         f"(too few points across width or depth within noise).")
    res["achievable_tight"] = bool(loa <= tight and rep <= tight / 2)
    res["achievable_loose"] = bool(loa <= loose and rep <= loose / 2)
    if res["achievable_loose"] and (resolved_frac is None or resolved_frac >= 0.8):
        res["result"] = "A"
        reasons.append(f"95% of single measurements within +-{loa:.2f} mm (<= {loose} mm); repeatability SD {rep:.2f} mm.")
    elif loa <= limited:
        res["result"] = "B"
        reasons.append(f"Usable but limited: 95% of single measurements within +-{loa:.2f} mm "
                       f"(target {loose} mm); repeatability SD {rep:.2f} mm.")
    else:
        res["result"] = "C"
        reasons.append(f"95% of single measurements within +-{loa:.2f} mm exceeds the {limited} mm usability limit.")
    if abs(validation["bias_mm"]) > 0.25 * loose:
        notes.append(f"Systematic bias {validation['bias_mm']:+.2f} mm; may be correctable by calibration, "
                     f"but validate the correction on independent tires.")
    res["summary"] = " ".join(reasons)
    res["notes"] = notes
    return res
