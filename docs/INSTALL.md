# Installation

## Environments

| Part | Requirement | Status |
|---|---|---|
| Analysis package `treadlidar` | Python >= 3.9 (developed/tested on **3.13**), numpy, scipy, matplotlib, pyyaml. Pure Python, **no C++ build**. | tested (70 tests) |
| Viewer | `pip install open3d` + a display with OpenGL/EGL (`libegl1`, `libgl1`) | **untested here** (no GL in the dev container) |
| L2 driver | **Ubuntu 20.04** + **ROS 2 Foxy** (or ROS1 Noetic), PCL 1.10, CMake/C++ toolchain | versions are those verified in the `unilidar_sdk2` README; **untested here** |
| Point-LIO (moving sensor) | Ubuntu 20.04 + **ROS1 Noetic**, Eigen, pcl-conversions (GPL-2.0) | **untested here**; not needed for the stationary milestone |

`treadlidar` itself runs on any OS with Python; ROS is only required for live acquisition / bag reading.

## Analysis package

```bash
git clone <repo> && cd Tire
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"        # numpy scipy matplotlib pyyaml pytest
pip install open3d              # optional viewer
pytest -q                       # 70 tests, ~30 s, no sensor needed
bash scripts/run_demo.sh        # simulated end-to-end demo -> data/output/demo
```

## L2 acquisition (ROS 2 Foxy, Ubuntu 20.04)

1. Follow the `unilidar_sdk2` README to build `unitree_lidar_ros2` (needs PCL 1.10). Set the PC's Ethernet interface to the
   address the README specifies (the L2's default target IP is **192.168.1.2**), then verify
   `ros2 topic list` shows `unilidar/cloud` and `unilidar/imu`.
2. Build the recorder: `cp -r ros2/tire_scan_recorder ~/ws/src && cd ~/ws && colcon build --packages-select tire_scan_recorder`.
3. `ros2 launch tire_scan_recorder record_l2.launch.py tire_id:=TIRE_001 scan_id:=SCAN_001 duration_s:=30 target_x:=0.6`
   writes `data/raw/TIRE_001_SCAN_001.npy` (+ `.sensor.json`, `_imu.npy`).
4. Alternative: `ros2 bag record unilidar/cloud unilidar/imu`, then read with `treadlidar.data_acquisition.ros2_bag.bag_to_scans`.
5. Docker starting points: `docker/Dockerfile.ros2-foxy`, `docker/Dockerfile.noetic-lio`, `docker/Dockerfile.treadlidar` (the first two **untested**).

Data directories: `data/raw` (recorded clouds), `data/rosbag`, `data/processed`, `data/reference` (manual measurements CSV), `data/output`.
Raw data is never modified by any step.
