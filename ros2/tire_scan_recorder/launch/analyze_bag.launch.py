"""Convenience: play a recorded bag (so the recorder / Point-LIO can consume it).  UNTESTED.

  ros2 launch tire_scan_recorder analyze_bag.launch.py bag:=data/rosbag/tire1_scan1
then, offline and without ROS:
  python -m treadlidar.cli analyze data/raw/TIRE_001_SCAN_001.npy --out data/output/run1
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("bag", default_value="data/rosbag/bag"),
        ExecuteProcess(cmd=["ros2", "bag", "play", LaunchConfiguration("bag"), "--rate", "1.0"], output="screen"),
    ])
