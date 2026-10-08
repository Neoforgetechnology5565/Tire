# Accuracy validation, repeatability and the A/B/C verdict

## Inputs
* Scans: `>= 3` (better `>= 5`) repeated scans of the same tire, same setup.
* Reference CSV (`groove_index,ref_depth_mm`), `>= 10` paired measurements in total (e.g. 4 grooves x 3 scans, better 3 tires).
* `--origin real` (physical L2 on a physical tire). The tool **refuses** `--origin real` for files marked simulated
  (`.sensor.json` has `"simulated": true`) and returns `NOT_ASSESSED` for `simulated`/`unknown` origins.

## What is computed (`validation_report.json`)
Per pair: reference, LiDAR depth, error = LiDAR - reference (negative = under-read).
Single-scan accuracy: bias, std, MAE, RMSE, max |error|, 95th-percentile |error|, share within +-0.5 / +-1.0 mm,
95 % CI of the bias (t-distribution), limits of agreement (bias +- 1.96 sd), regression slope/intercept (does the error grow with depth?).
Scan-average accuracy: error of the per-groove mean over scans (what averaging buys; random error only).
Repeatability: per-location mean, SD, min, max, range over scans; pooled SD; repeatability limit 2.77 x SD (ISO 5725 style).
Figures: `accuracy.png` (LiDAR vs reference, error vs reference, +-0.5/+-1 mm bands), `repeatability.png`.
Scans whose detected longitudinal-groove count differs from the reference count are **excluded and listed** (no silent mis-pairing).

## Verdict (thresholds in `config/pipeline.yaml: validation`)
Let `LoA95 = |bias| + 1.96 sd` (the error magnitude 95 % of single measurements stay within) and `rep` = pooled repeatability SD.

| Result | Rule | Meaning |
|---|---|---|
| **A - suitable** | `LoA95 <= 1.0 mm` and `rep <= 0.5 mm` (and >= 80 % of grooves resolved). `achievable_tight` is reported separately (`LoA95 <= 0.5` and `rep <= 0.25`). | +-1.0 mm (and possibly +-0.5 mm) is demonstrated |
| **B - usable, limited** | `LoA95 <= 2.0 mm` (or A's rule failed on resolvability) | works, but state the achieved +-x mm honestly |
| **C - insufficient** | otherwise | the L2 (at this setup) cannot give usable tread depth |
| INCONCLUSIVE | < 10 pairs or < 3 scans | collect more data |
| NOT_ASSESSED | data not marked `real` | no statement about the L2 |

Not hidden: bias, resolvability failures, excluded scans and warnings are in the report. A systematic bias is flagged
(it may be correctable by calibration, but must then be re-validated on independent tires).

## Point-density/resolvability (`report.json -> resolvability`)
For each groove: width, points across the width, points in the core, single-point noise, depth/noise, random depth uncertainty
(sigma / sqrt(n_core)), and `resolved` = (>= 3 points across width) and (depth >= 3 sigma) and plausible width. A groove that is not
resolved must not be trusted even if a number is printed.
**Random-uncertainty caveat:** `depth_random_uncertainty_mm` only covers independent noise; systematic effects (beam footprint,
occlusion in narrow deep grooves, range bias on black rubber, registration error) are what the real validation measures.

## Interpreting a negative result
Typical reasons, in the order to check: (1) step-target test shows noise/bias too large -> sensor limit; (2) grooves not resolved (density/width) -> longer
accumulation, closer range; (3) occlusion (lateral grooves vanish at oblique angles; narrow grooves seen from the side) -> view angle; (4) segmentation/axis
wrong (see warnings) -> `--axis-hint`; (5) reference/gauge mismatch -> re-measure. Report RESULT B/C plainly rather than tuning thresholds.
