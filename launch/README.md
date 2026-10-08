# Launch files

The ROS 2 launch files live inside the ament package so `ros2 launch` finds them after the build:

* `ros2/tire_scan_recorder/launch/record_l2.launch.py` - start the L2 driver (optional) + scan recorder
* `ros2/tire_scan_recorder/launch/analyze_bag.launch.py` - replay a recorded rosbag2

See `docs/INSTALL.md` for the build. All launch files are **untested on hardware** (no ROS 2 / L2 in the
development environment).
