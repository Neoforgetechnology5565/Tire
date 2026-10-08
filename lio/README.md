# LiDAR-inertial odometry (moving sensor / moving vehicle) - integration notes

**Status: documented integration path, NOT executed in this repository's development environment**
(no L2, no ROS in the container). Stationary feasibility testing does *not* need this directory.

## What was verified (from the upstream READMEs, 2026-10)

| Component | Licence | ROS | Notes |
|---|---|---|---|
| `unitreerobotics/unilidar_sdk2` | BSD-3-Clause | ROS1 Noetic + **ROS2 Foxy** packages, Ubuntu 20.04 | topics `unilidar/cloud`, `unilidar/imu`; frames `unilidar_lidar`, `unilidar_imu`; Ethernet 192.168.1.2 |
| `unitreerobotics/point_lio_unilidar` | **GPL-2.0** | **ROS1 Noetic only**, Ubuntu 20.04 | has `mapping_unilidar_l2.launch`; needs `unilidar_sdk2` + Eigen + pcl-conversions |
| `hku-mars/Point-LIO` | licence not stated on the page (LICENSE file linked, not read) | ROS1 only | Livox / Velodyne / Ouster configs |
| `hku-mars/FAST_LIO` | **GPL-2.0** | page does not mention ROS2 | Livox / Velodyne / Ouster; needs per-point time |

Consequences for this project:

1. **Point-LIO for the L2 is a ROS1 (Noetic) tool**, while the L2 ROS2 driver is verified on Foxy. The
   two worlds must be bridged: record a ROS2 bag, convert/replay it into a ROS1 Noetic container
   (e.g. with the `rosbags` converter, licence to be checked), run `point_lio_unilidar`, and take its output
   (registered PCD and/or odometry) back into `treadlidar`. A native ROS2 port was not verified to exist.
2. **GPL-2.0 boundary.** Do not copy GPL code into the proprietary `treadlidar` package and do not link it.
   Running the GPL tools as separate processes that exchange files (bags / PCD / trajectory text) is the
   usual way to keep a clean boundary, but **have counsel confirm** before shipping them with a commercial product.
3. For the **stationary-tire feasibility milestone no odometry is needed**: the sensor does not move, so frames are
   concatenated in the sensor frame (`tire_scan_recorder`). ICP (`treadlidar.registration`) is only a fallback and is
   *poorly conditioned on a tread patch* (a cylinder slides around its axis) - see tests.

## Suggested workflow for a moving sensor

```
ROS2 Foxy: unitree_lidar_ros2 -> ros2 bag record unilidar/cloud unilidar/imu
bag -> ROS1 bag (conversion)           [verify the per-point `time` field survives]
Noetic container: roslaunch point_lio_unilidar mapping_unilidar_l2.launch  (+ rosbag play)
output: registered cloud (PCD) + trajectory
treadlidar analyze registered.pcd --out data/output/run --axis-hint ...
```
`docker/Dockerfile.noetic-lio` is a starting point for the Noetic side (UNTESTED).

## Interfaces already prepared for the moving-vehicle milestone

* `treadlidar.preprocessing.motion.deskew_with_gyro / deskew_constant_velocity` - per-point motion compensation (unit-tested).
* `PointCloud.transformed(T)` + per-point time `t` - apply LIO poses per frame, then concatenate.
* The tire is described in its own cylinder frame (`CylinderFit`: axis, centre, radius). For a rolling wheel the next milestone
  adds frame-to-frame tracking of that frame and unwrapping *around the full circumference*: `s` already is arc length.
* Everything downstream (reference surface, grooves, depth, mesh, validation) consumes `(s, w, dr)` and is independent of how the points were registered.
