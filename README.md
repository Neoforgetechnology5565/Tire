# Unitree L2 tire-tread 3D reconstruction & measurement - Milestone 1 (feasibility prototype)

Python package `treadlidar` + ROS 2 recorder + docs to find out, **from real scans and physical reference measurements**, whether a
Unitree L2 can resolve tire tread and measure its depth to ±0.5-1.0 mm. The software never assumes the answer.

## Honest status

| Item | Status |
|---|---|
| Pipeline (segment → cylinder fit → reference surface → height-map → grooves → depth → mesh → PLY/STL/OBJ/JSON/CSV) | **implemented, 134 automated tests pass** (`pytest -q`, ~2.5 min, no sensor; the browser tests skip if Playwright/Chromium are absent) |
| Validation module (error/MAE/RMSE/SD/bias/CI, repeatability, A/B/C verdict), point-density/resolvability, sensor characterisation tools | implemented + tested on synthetic data |
| **Results on real Unitree L2 data** | **none yet - no sensor or physical tire was available. The verdict for the L2 is `NOT_ASSESSED`/pending.** |
| Simulation-based sensitivity (what noise/density *would* be needed) | done: `docs/SIMULATION_RESULTS.md` (assumed sensor parameters, not L2 measurements) |
| L2 driver / ROS 2 recorder / Point-LIO bridge | written from the upstream READMEs; **untested on hardware** |
| **Desktop UI** (`treadlidar ui`): 10-step workflow, 3D views, depth map, pins/regions, accuracy, full tire, export | **implemented; 27 API + 12 real-browser tests pass** (headless Chromium). The native-window wrapper (pywebview / Chromium app window) is untested here (no display) |
| Open3D viewer (`treadlidar view`) | superseded by the UI for most uses; **window/picking untested** (no GL in the dev container) |
| **M2: full 360° tire** (rotating wheel, fixed sensor): stitching, automated measurement protocol, wear metrics, limit check with guards, closed-ring mesh | **implemented, tested on simulated data only** - see `docs/FULL_TIRE.md`; unvalidated until real data passes M1 |
| Moving-vehicle scanning | **not attempted** (by design); interfaces prepared (`lio/README.md`) |

The feasibility result (A suitable / B limited / C insufficient) can only be produced by running `treadlidar validate ... --origin real`
on real data, following `docs/SCANNING_PROCEDURE.md`. Simulated data can never yield A/B/C (enforced in code and tests).

## Desktop interface
```bash
pip install -e ".[desktop]"   # pywebview is optional; a Chromium/Chrome/Edge window or your browser also work
treadlidar ui                    # the whole workflow in one window: load → segment → measure → accuracy → export
```
See `docs/UI.md` and the screenshots in `docs/images/` (all simulated data). The interface keeps the data origin visible and only lets the Accuracy step produce a verdict.

## Quick start (no sensor)
```bash
pip install -e ".[test]" && pytest -q
bash scripts/run_demo.sh                     # simulated end-to-end demo -> data/output/demo
treadlidar analyze examples/sim_data/sim_scan_01.npy --out out --tread-half-width-mm 95
treadlidar measure examples/sim_data/sim_scan_01.npy --tread-half-width-mm 95 --at 0,-54      # depth at (s mm, w mm)
```
Real data: record with `ros2 launch tire_scan_recorder record_l2.launch.py ...` (or read a bag), then
```bash
treadlidar analyze data/raw/TIRE_001_SCAN_001.npy --out data/output/t1 --axis-hint 0,1,0 --tread-half-width-mm 85
treadlidar validate data/raw/TIRE_001_SCAN_0*.npy --reference data/reference/TIRE_001.csv --origin real --out data/output/val
treadlidar view data/raw/TIRE_001_SCAN_001.npy        # Open3D: 1 raw, 2 filtered, 3 mesh, 4 grooves, +/- point size, P pick&measure
```

## Full tire (Milestone 2, simulated data only so far)
```bash
bash scripts/run_fulltire_demo.sh                      # 18 simulated views of a rotating wheel -> data/output/fulltire_demo
treadlidar fulltire data/raw/TIRE_001_SCAN_*.npy --out data/output/t1 --circumference-mm 1885 --axis-hint 0,1,0 \
    --tread-half-width-mm 85 --expected-grooves 4      # angles from the .sensor.json sidecars (wheel_angle_deg)
```
Outputs: `*_fulltire_mesh.ply/.stl/.obj`, `*_fulltire_protocol.json/.csv` (depth of every groove at N positions around the tire, wear metrics,
limit check), `*_fulltire_unrolled.png`. The limit check never reports PASS if the groove count is unverified (`docs/FULL_TIRE.md`).

## Workflow ↔ commands
load/preview `info`,`view` · register `analyze` (`--register icp` for several files) · segment / reconstruct / analyze / measure `analyze`,`measure` ·
accuracy `validate` · export (PLY points+mesh, STL, OBJ, JSON, CSV, PNG) `analyze`. Configuration: `config/pipeline.yaml`, sensor/calibration parameters: `config/sensor_l2.yaml`.

## What the outputs contain
`*_points.ply` (raw tire points: normals, depth colours, per-point `depth_mm`), `*_mesh.ply/.stl/.obj`, `*_report.json` (depth stats, per-groove table, geometry, density/noise,
resolvability, **raw-vs-filtered-vs-reconstructed depth per groove**, scan metadata, config, warnings), `*_grooves.csv`, `*_depth_map.png`, `*_cross_section.png`
(raw points vs reference vs height-map: over-smoothing is visible), validation: `validation_report.json`, `validation_pairs.csv`, `accuracy.png`, `repeatability.png`, `feasibility.json`.

## Layout
```
config/  docker/  docs/  examples/sim_data/  launch/  lio/  ros2/tire_scan_recorder/  scripts/  tests/
src/treadlidar/{data_acquisition,preprocessing,registration,tire_segmentation,reconstruction,tread_analysis,
                measurement,validation,export,calibration,simulation,viewer}
data/{raw,rosbag,processed,reference,output}
```
Docs: UI · FULL_TIRE · INSTALL · SCANNING_PROCEDURE · CALIBRATION · VALIDATION · ARCHITECTURE (design decisions, defects found, limitations) · LIO_INTEGRATION ·
LICENSES · SIMULATION_RESULTS · TROUBLESHOOTING.

## Licensing
Custom code: yours as the commercial owner (add your licence header). Dependencies are permissive; GPL-2.0 LIO software (Point-LIO adaptation) is kept out of the package and run as
a separate process - see `docs/LICENSES.md` (also: no freedom-to-operate analysis of tread-measurement patents was done).
`treadscan` (MIT) was evaluated and is **not** applicable to LiDAR (it is camera/image based, 2D unwrapping only).
