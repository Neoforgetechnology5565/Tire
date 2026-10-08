"""Read Unitree L2 PointCloud2 + IMU from a ROS 2 bag (rosbag2).

UNTESTED against a real L2 bag in this repository's CI (no ROS 2 / sensor available).
Requires a sourced ROS 2 environment (rosbag2_py, rclpy, sensor_msgs_py). Imports are lazy so
the rest of the package works without ROS.

Topic defaults follow the Unitree unilidar_sdk2 README: ``unilidar/cloud`` and ``unilidar/imu``.
Verify with ``ros2 topic list`` on your device.
"""
from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

import numpy as np

from ..types import PointCloud


def _pc2_to_cloud(msg) -> PointCloud:
    from sensor_msgs_py import point_cloud2 as pc2  # type: ignore

    names = [f.name for f in msg.fields]
    want = [n for n in ("x", "y", "z", "intensity", "time") if n in names]
    arr = pc2.read_points(msg, field_names=want, skip_nans=True)
    cols = {n: np.asarray(arr[n], dtype=np.float64) for n in want}
    xyz = np.column_stack([cols["x"], cols["y"], cols["z"]])
    stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
    return PointCloud(xyz, cols.get("intensity"), cols.get("time"), stamp, msg.header.frame_id)


def iter_bag(bag_path: str, cloud_topic: str = "unilidar/cloud", imu_topic: str = "unilidar/imu",
             storage_id: str = "sqlite3") -> Iterator[Tuple[str, object]]:
    """Yield ('cloud', PointCloud) or ('imu', dict(stamp, gyro, accel)) in bag order."""
    import rosbag2_py  # type: ignore
    from rclpy.serialization import deserialize_message  # type: ignore
    from rosidl_runtime_py.utilities import get_message  # type: ignore

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag_path, storage_id=storage_id),
                rosbag2_py.ConverterOptions("", ""))
    types = {t.name.lstrip("/"): t.type for t in reader.get_all_topics_and_types()}
    for need in (cloud_topic.lstrip("/"),):
        if need not in types:
            raise KeyError(f"topic {need} not in bag; available: {sorted(types)}")
    msg_cls = {n: get_message(t) for n, t in types.items()}
    while reader.has_next():
        topic, raw, _ = reader.read_next()
        topic = topic.lstrip("/")
        if topic == cloud_topic.lstrip("/"):
            yield "cloud", _pc2_to_cloud(deserialize_message(raw, msg_cls[topic]))
        elif topic == imu_topic.lstrip("/"):
            m = deserialize_message(raw, msg_cls[topic])
            yield "imu", {
                "stamp": m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                "gyro": np.array([m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z]),
                "accel": np.array([m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z]),
            }


def bag_to_scans(bag_path: str, **kw) -> Tuple[List[PointCloud], dict]:
    """Collect all clouds and IMU samples from a bag."""
    clouds, imu = [], {"stamp": [], "gyro": [], "accel": []}
    for kind, item in iter_bag(bag_path, **kw):
        if kind == "cloud":
            clouds.append(item)
        else:
            for k in imu:
                imu[k].append(item[k])
    return clouds, {k: np.asarray(v) for k, v in imu.items()}
