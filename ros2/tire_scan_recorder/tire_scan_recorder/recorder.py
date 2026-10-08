"""Live L2 acquisition node: accumulates PointCloud2 frames into one scan file + metadata.

UNTESTED on hardware (no ROS 2 / L2 in the development container). Verify topic names and the
PointCloud2 field layout with `ros2 topic list` / `ros2 topic echo --once unilidar/cloud`.

Parameters
  cloud_topic   (default unilidar/cloud)     imu_topic (default unilidar/imu)
  output_dir    (default data/raw)           scan_id, tire_id
  n_frames      stop after this many accumulated frames (0 = until duration_s)
  duration_s    stop after this many seconds (0 = until n_frames)
  target_xyz    approx. tire tread centre in the sensor frame [x,y,z] for distance/angle logging
The node is *stationary-mode*: frames are concatenated in the sensor frame (the sensor must not move).
For a moving sensor use Point-LIO poses (docs/LIO_INTEGRATION.md) and save the registered cloud instead.
"""
import json
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, PointCloud2
from sensor_msgs_py import point_cloud2 as pc2


class Recorder(Node):
    def __init__(self):
        super().__init__("tire_scan_recorder")
        self.declare_parameter("cloud_topic", "unilidar/cloud")
        self.declare_parameter("imu_topic", "unilidar/imu")
        self.declare_parameter("output_dir", "data/raw")
        self.declare_parameter("scan_id", "SCAN_001")
        self.declare_parameter("tire_id", "TIRE_001")
        self.declare_parameter("n_frames", 0)
        self.declare_parameter("duration_s", 30.0)
        self.declare_parameter("target_xyz", [0.0, 0.0, 0.0])
        g = self.get_parameter
        self.frames, self.t_first, self.imu = [], None, []
        self.create_subscription(PointCloud2, g("cloud_topic").value, self.on_cloud, 10)
        self.create_subscription(Imu, g("imu_topic").value, self.on_imu, 200)
        self.start = time.time()
        self.timer = self.create_timer(0.5, self.check_done)

    def on_imu(self, m):
        self.imu.append([m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m.angular_velocity.x, m.angular_velocity.y,
                         m.angular_velocity.z, m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z])

    def on_cloud(self, m):
        names = [f.name for f in m.fields]
        want = [n for n in ("x", "y", "z", "intensity", "time") if n in names]
        a = pc2.read_points(m, field_names=want, skip_nans=True)
        arr = np.column_stack([np.asarray(a[n], np.float64) for n in want])
        stamp = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        self.t_first = self.t_first or stamp
        self.frames.append((stamp, want, arr))

    def check_done(self):
        g = self.get_parameter
        n_done = g("n_frames").value and len(self.frames) >= g("n_frames").value
        t_done = g("duration_s").value and (time.time() - self.start) >= g("duration_s").value
        if n_done or t_done:
            self.save()
            rclpy.shutdown()

    def save(self):
        g = self.get_parameter
        out = Path(g("output_dir").value)
        out.mkdir(parents=True, exist_ok=True)
        if not self.frames:
            self.get_logger().error("no frames received: check topic names / L2 network (192.168.1.2 target IP)")
            return
        xyz = np.vstack([f[2][:, :3] for f in self.frames])
        stamps = np.array([f[0] for f in self.frames])
        target = np.array(g("target_xyz").value, float)
        dist = float(np.linalg.norm(target))
        meta = {
            "scan_id": g("scan_id").value, "tire_id": g("tire_id").value, "simulated": False,
            "sensor_origin": [0.0, 0.0, 0.0],      # points are in the sensor frame
            "n_frames": len(self.frames), "n_points": int(len(xyz)),
            "timestamp": float(stamps[0]), "duration_s": float(stamps[-1] - stamps[0]),
            "scan_distance_m": dist,
            "scan_azimuth_deg": float(np.degrees(np.arctan2(target[1], target[0]))),
            "scan_elevation_deg": float(np.degrees(np.arcsin(target[2] / dist))) if dist > 0 else 0.0,
            "frame_fields": self.frames[0][1], "units": "metre",
        }
        base = out / f"{g('tire_id').value}_{g('scan_id').value}"
        np.save(str(base) + ".npy", xyz.astype(np.float32))
        Path(str(base) + ".sensor.json").write_text(json.dumps(meta, indent=2))
        if self.imu:
            np.save(str(base) + "_imu.npy", np.array(self.imu))
        self.get_logger().info(f"saved {len(xyz)} points from {len(self.frames)} frames to {base}.npy")


def main():
    rclpy.init()
    node = Recorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.save()
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
