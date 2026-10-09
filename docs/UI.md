# Desktop interface

```bash
pip install -e ".[desktop]"        # optional: pywebview for a native window (BSD-3-Clause)
treadlidar ui                      # opens the app in its own window
treadlidar ui --mode none          # only print the link (use any browser)
```

Everything runs on your computer: the app starts a small service on `127.0.0.1` (a free port, protected by a random
per-launch token and a Host-header check) and shows it in a window. Nothing is sent over the network.

**Window choice (`--mode auto`):** pywebview if installed → a Chromium/Chrome/Edge window in `--app` mode (no tabs, its own
temporary profile) → your default browser. Force one with `--mode pywebview|chromium|browser|none`; `--browser PATH` selects the Chromium binary.
Licensing note for Linux: pywebview needs a GUI backend; choose GTK (LGPL) or PySide6 (LGPL) rather than PyQt (GPL) for a commercial product,
or simply use the Chromium window.

## The ten steps (left rail) and two tools

| Step | Screen | What you do |
|---|---|---|
| 1 Load scan | Welcome / Data | Browse recorded files (choose the unit explicitly) or load a **simulated** demo |
| 2 Preview | Data | Rotate the raw cloud in 3D, colour by height or range, see the sensor position |
| 3 Register | Data | Optional: combine scans (fixed sensor) or ICP-align them (with a warning about its weakness on tread) |
| 4 Segment tire | Tread → Segmentation | See what was removed and what was kept, with a point-count funnel |
| 5 Reconstruct | Tread → Surface | Un-smoothed surface in 3D, groove centrelines, raw-vs-filtered-vs-reconstructed depth table, live cross-section |
| 6 Analyze tread | Tread → Grooves / Density | Depth map, groove table, and whether the sensor can resolve each groove |
| 7 Select area | Measure | Pin a point, or drag a box for region statistics |
| 8 Calculate depth | Measure | Depth, reference surface and groove bottom per pin, drawn in 3D with the cross-section |
| 9 Accuracy | Accuracy | Gauge readings → bias, MAE, RMSE, repeatability, **verdict** (real data only) |
| 10 Export | Export | PLY / STL / OBJ / JSON / CSV / PNG to a folder, or one zip |
| Tool | Full tire | Stitch a rotating wheel into a 360° map, measure at fixed angles, limit check |
| Tool | Sensor check | Flat-target noise and step-height tests |

Screenshots (all **simulated** data) are in `docs/images/`; regenerate them with `python scripts/make_ui_screenshots.py`.

## Design principles
* **The data origin is always visible**: a badge in the top bar says SIMULATED DATA or Real data · unvalidated; simulated exports get a note file.
* **The verdict lives in one place**: only the Accuracy step can say the L2 is suitable, and "Real" is locked while a selected scan is simulated.
* **Nothing is hidden by drawing shortcuts**: the 3D views draw a display subsample of large clouds and say so; analysis always uses all points.
* **Warnings are shown where they matter** (result panel, limit-check card), not only in logs.
* Light and dark themes (follows the system, switchable), keyboard focus rings, `Ctrl/⌘ + Enter` runs the analysis, `Esc` closes dialogs.

## Tips
* A single pin uses only the cells inside its window, so it is noisier than the per-groove depth; use the window selector, region boxes or the groove table for steadier numbers.
* The parameter panel collapses after the first run (button on the left); **Tire preset** fills sensible radius and width ranges.
* For a full tire, set the **tape-measured circumference** and the **expected groove count**; without the count a PASS is withheld.

## Architecture
`src/treadlidar/ui/server.py` (standard-library HTTP server, JSON + binary endpoints, background jobs with stage progress) and
`src/treadlidar/ui/static/` (vanilla JS, canvas charts, WebGL viewer; no framework, no CDN, works offline).
Tests: `tests/test_ui_server.py` (27 API/security tests) and `tests/test_ui_browser.py` (12 tests that drive the real UI in Chromium).
