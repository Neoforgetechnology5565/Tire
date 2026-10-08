# Calibration

Nothing below is pre-filled with guessed values: parameters are in `config/sensor_l2.yaml` (`null` = still to be determined).

## 1. LiDAR (range) calibration
* **Noise & density** vs distance/surface: `scripts/characterize_sensor.py plane` (flat matte board; repeat 0.4-1.0 m). Record `range_noise_mm_1sigma`.
* **Range bias / mm-step response**: `scripts/characterize_sensor.py step --known-mm <h>` on a stepped target (gauge blocks). The step error at 2/4/6/8 mm
  is the most direct predictor of tread-depth error. Do it on a rubber-like dark matte surface; intensity affects range.
* Warm-up: record after the unit has been running for the time the datasheet recommends; log temperature.

## 2. IMU calibration (moving-sensor milestone only)
* Gyro bias: record 60-120 s motionless, average. Accel bias/scale: standard 6-position test. Noise densities from Allan variance of a long (>= 2 h) static record.
* The stationary tire test does not use the IMU.

## 3. LiDAR-IMU extrinsics
The L2 integrates an IMU. Obtain the LiDAR->IMU transform from the Unitree datasheet/SDK documentation and put it in `extrinsics.lidar_to_imu_{R,t}`;
do not assume identity. If estimating it yourself, use a LIO-based calibration method (excite all axes) and validate by checking that Point-LIO's map of a flat wall stays planar.

## 4. Sensor-to-tire distance and angle
Measure with a tape/laser measure from the sensor reference point to the tread centre (+-2 mm); put it in the recorder `target_*` parameters. `treadlidar`
independently computes the distance from the fitted cylinder (`scan_metadata.scan_distance_m`); disagreement > 1 cm means a frame/aim problem.

## 5. Tire frame (coordinate system)
Fitted from the data: cylinder axis = `w`, arc length = `s`, radial height = `dr`. `+w` is to the viewer's right (from the sensor); `view_up` (default +Z) defines "up".
Groove numbering for reference CSVs follows +w.

## 6. Reference-measurement procedure
See `docs/SCANNING_PROCEDURE.md` (digital gauge, marked grooves, 3 readings x 2 operators, gauge uncertainty recorded).

## Calibration parameters to document per campaign
sensor serial/firmware, warm-up time, mounting height/aim, distance, accumulation time, range-noise/bias results, step-target results,
gauge model/resolution/calibration date, tire size/radius/tread width, ambient conditions. They belong in the dataset's metadata JSON.
