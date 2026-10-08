"""Start the Unitree L2 driver (optional) and the scan recorder.  UNTESTED on hardware.

  ros2 launch tire_scan_recorder record_l2.launch.py tire_id:=TIRE_001 scan_id:=SCAN_001 duration_s:=30 \
       target_x:=0.6 target_y:=0.0 target_z:=0.0

The driver package name / launch file follow the unilidar_sdk2 README (unitree_lidar_ros2, launch.py);
set start_driver:=false if you already run the driver.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    args = [DeclareLaunchArgument(k, default_value=v) for k, v in {
        "start_driver": "true", "tire_id": "TIRE_001", "scan_id": "SCAN_001", "output_dir": "data/raw",
        "duration_s": "30.0", "n_frames": "0", "cloud_topic": "unilidar/cloud", "imu_topic": "unilidar/imu",
        "target_x": "0.6", "target_y": "0.0", "target_z": "0.0"}.items()]
    driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare("unitree_lidar_ros2"), "launch", "launch.py"])),
        condition=IfCondition(LaunchConfiguration("start_driver")))
    rec = Node(package="tire_scan_recorder", executable="scan_recorder", output="screen", parameters=[{
        "cloud_topic": LaunchConfiguration("cloud_topic"), "imu_topic": LaunchConfiguration("imu_topic"),
        "output_dir": LaunchConfiguration("output_dir"), "tire_id": LaunchConfiguration("tire_id"),
        "scan_id": LaunchConfiguration("scan_id"),
        "duration_s": LaunchConfiguration("duration_s"), "n_frames": LaunchConfiguration("n_frames"),
        "target_xyz": [LaunchConfiguration("target_x"), LaunchConfiguration("target_y"), LaunchConfiguration("target_z")],
    }])
    return LaunchDescription(args + [driver, rec])
