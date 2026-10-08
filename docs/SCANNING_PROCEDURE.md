# Data collection and reference-measurement procedure (stationary feasibility test)

The goal is to produce **paired** data: LiDAR depths and independent physical depths for the *same grooves*, repeated.
Nothing in this software can establish accuracy without it.

## 0. Characterise the sensor first (1-2 h, no tire)
1. **Flat target** (matte rigid board): record 30 s at 0.4, 0.6, 0.8, 1.0 m:
   `scripts/characterize_sensor.py plane board_0p6m.npy` -> range noise (std/MAD), spacing, density.
2. **Step target of known height** (stack gauge blocks / machined steps at 2, 4, 6, 8 mm; dark rubber-like or matte-black surface to mimic tread):
   `scripts/characterize_sensor.py step steps.npy --known-mm 4` -> the L2's actual ability to measure millimetre steps.
   **If the L2 cannot measure an 8 mm step to better than +-1 mm here, no tire algorithm will fix that.**
3. Put the results in `config/sensor_l2.yaml` (range_noise_mm_1sigma, range_bias_mm).

## 1. Prepare the tire
* Mount on a vehicle or stand, wheel straight, brake on. Mark 3-4 measurement grooves with paint pens/tape at known circumferential positions.
* Record tire size code (radius, tread width) -> `radius_range_m` (+-10 %) and `tread_half_width_m` in the config. Provide the wheel axis direction if known (`--axis-hint`).
* Clean the tread (stones/mud change the surface). Same temperature/lighting between scans (L2 is laser based; avoid direct strong sunlight).

## 2. Reference measurements (the truth)
* Use a **digital tread-depth gauge** (resolution 0.01 mm, calibrated) at the SAME marked locations: 3 readings each by 2 operators, take the mean.
  Record the groove numbering from the sensor's point of view, **left to right (1..N)**: `data/reference/<tire>.csv`:
  ```
  groove_index,ref_depth_mm
  1,7.62
  2,7.95
  ```
* The gauge's own uncertainty (typ. +-0.1 mm) and operator spread bound what can be claimed; record them.

## 3. LiDAR scans
* Sensor stationary on a rigid tripod, 0.4-0.8 m from the tread, aimed at the tread centre; vary **one factor at a time**:
  distance (0.4/0.6/0.8 m), azimuth around the tire (0, 20, 40 deg), accumulation time (5/15/30/60 s).
* `ros2 launch tire_scan_recorder record_l2.launch.py ... duration_s:=30 target_x:=<distance>` (records position/distance/angle/timestamp/points/frames to the metadata JSON).
* **Repeat each configuration >= 5 times** (re-aim the sensor between repeats; do not move the tire) -> repeatability.
* Then **different tires/wear levels** (new, half-worn, worn; >= 3 tires) -> accuracy across the depth range.
* Record ambient notes (temperature, tire wet/dry, wheel position).

## 4. Process and judge
```bash
treadlidar analyze data/raw/TIRE_001_SCAN_001.npy --out data/output/t1s1 --axis-hint 0,1,0 --tread-half-width-mm 85
treadlidar validate data/raw/TIRE_001_SCAN_0*.npy --reference data/reference/TIRE_001.csv --origin real --out data/output/val_t1
```
See `docs/VALIDATION.md` for how RESULT A/B/C is decided and what is reported.

## Coordinate systems
* Sensor frame (`unilidar_lidar`): as published by the driver.
* Tire frame (`treadlidar`): fitted cylinder axis = **w**; **s** = arc length along the circumference; **dr** = radial height (grooves negative).
  +w points to the **viewer's right** when looking from the sensor at the tire (`view_up` = +Z by default).

## 5. Full-tire scans (Milestone 2)
Wheel free to rotate (stand/jack), sensor fixed, tape mark on the tire. Record one view every 20 deg (`wheel_angle_deg:=<angle>`; positive = tread at the sensor
moves downward), >= 25 % overlap between neighbouring views, 18 views for 360 deg. Measure the circumference with a tape at the tread centre. Reference depths:
digital gauge at every groove at, say, 8 positions (e.g. every 45 deg), recorded per groove/position; use them to validate the protocol output
(`measurements.csv`) the same way as for M1. See `docs/FULL_TIRE.md`.
