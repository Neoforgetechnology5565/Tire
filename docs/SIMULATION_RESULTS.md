# Simulation sensitivity study (NOT Unitree L2 data)

**Read this first.** These numbers come from the synthetic tire generator (`treadlidar.simulation`) with *assumed* range noise σ and surface
point density. They describe what the **algorithms** can do if a sensor delivered that quality, and what quality would be *needed* for ±0.5-1.0 mm.
They say **nothing** about what the Unitree L2 actually delivers - that must be measured (`docs/SCANNING_PROCEDURE.md`).

Setup: passenger-size tread patch (R = 300 mm, 4 longitudinal grooves 10-12 mm wide × 8.0 mm deep, shoulder lateral grooves 6 mm × 7 mm, 4 mm crown,
sensor 0.6 m away, frontal view), Gaussian range noise along each ray (also on clutter points), ray-cast self-occlusion, 4 random seeds per row,
ground truth depth 8.0 mm, **single scan** (M1 pipeline, current code incl. groove-masked reference refinement).
Reproduce: `treadlidar sweep --out docs/results --noise-mm 0.5 1 2 3 4 --density 10 20 40 80 --seeds 4`.

Error = measured − true groove depth over all grooves and seeds. "runs failed" = analysis error or wrong groove count (those runs are excluded - so rows with failures flatter the statistics).

| σ (mm) | pts/cm² | runs ok/failed | bias (mm) | SD (mm) | 95% limit of \|error\| (mm) | within ±0.5 | within ±1.0 |
|---|---|---|---|---|---|---|---|
| 0.5 | 10 | 4/0 | +0.01 | 0.09 | 0.19 | 100% | 100% |
| 0.5 | 20 | 4/0 | +0.00 | 0.05 | 0.11 | 100% | 100% |
| 0.5 | 40 | 4/0 | +0.02 | 0.05 | 0.12 | 100% | 100% |
| 0.5 | 80 | 4/0 | +0.01 | 0.03 | 0.06 | 100% | 100% |
| 1.0 | 10 | 3/1 | +0.13 | 0.23 | 0.58 | 100% | 100% |
| 1.0 | 20 | 4/0 | +0.04 | 0.16 | 0.35 | 100% | 100% |
| 1.0 | 40 | 4/0 | +0.02 | 0.13 | 0.28 | 100% | 100% |
| 1.0 | 80 | 4/0 | +0.02 | 0.07 | 0.15 | 100% | 100% |
| 2.0 | 10 | 4/0 | +0.10 | 0.39 | 0.86 | 88% | 100% |
| 2.0 | 20 | 4/0 | +0.09 | 0.25 | 0.58 | 94% | 100% |
| 2.0 | 40 | 4/0 | +0.11 | 0.22 | 0.55 | 94% | 100% |
| 2.0 | 80 | 4/0 | +0.08 | 0.17 | 0.41 | 100% | 100% |
| 3.0 | 10 | 2/2 | +0.96 | 0.44 | 1.83 | 0% | 62% |
| 3.0 | 20 | 4/0 | +0.78 | 0.50 | 1.77 | 19% | 62% |
| 3.0 | 40 | 4/0 | +0.86 | 0.42 | 1.68 | 19% | 75% |
| 3.0 | 80 | 4/0 | +0.65 | 0.30 | 1.24 | 25% | 81% |
| 4.0 | 10 | 1/3 | +2.04 | 1.21 | 4.42 | 0% | 25% |
| 4.0 | 20 | 4/0 | +2.28 | 0.44 | 3.14 | 0% | 0% |
| 4.0 | 40 | 4/0 | +1.71 | 0.86 | 3.38 | 12% | 12% |
| 4.0 | 80 | 4/0 | +1.80 | 0.34 | 2.46 | 0% | 0% |

![sweep](results/sim_sweep.png)

## What this tells us (simulation only)
* **σ ≤ 1 mm:** 95 % of single-groove errors stay within about 0.1-0.35 mm (one run failed at 10 pts/cm², where the limit rises to 0.58 mm). Both ±0.5 and ±1.0 mm targets are met in simulation.
* **σ = 2 mm:** about 0.4-0.9 mm (0.41-0.58 mm at ≥ 20 pts/cm²): ±1.0 mm is met, ±0.5 mm is borderline.
* **σ = 3 mm:** 1.2-1.8 mm with a systematic **over-read of +0.65 to +0.96 mm**; **σ = 4 mm:** 2.5-4.4 mm, +1.7 to +2.3 mm. Neither target is met, and runs start to fail (the
  tool then warns/raises instead of returning a number).
* So, *if* the real sensor had no systematic bias and the surface behaved like the model: **±1.0 mm needs about σ ≲ 2 mm with ≥ 20 pts/cm²; ±0.5 mm needs about σ ≲ 1 mm (≥ 20 pts/cm²)**.
* The over-read at high noise is positive; I have not isolated the cause (plausibly noise inflating apparent groove contrast after thresholding). Compared with an earlier
  run of this study (before the groove-masked reference refinement) the high-noise over-read grew slightly (e.g. σ = 3, 40 pts/cm²: +0.55 → +0.86 mm) while σ ≤ 2 mm results are unchanged; shallow
  grooves (2-5 mm) became measurable, which is the trade made.
* Averaging more points helps random noise only; the real L2 will add systematic effects the simulation lacks. M2 (`docs/FULL_TIRE.md`) shows that accumulating many views also makes shallow grooves detectable.

## Decisive unknowns for the real L2 (to be measured)
range noise on black rubber at 0.4-1.0 m; range bias vs. incidence angle/intensity; beam footprint at the working distance (mixed pixels at groove edges); achievable accumulated
density from the L2's non-repetitive scan over 10-60 s; whether grooves narrower than the spot are seen at all.
