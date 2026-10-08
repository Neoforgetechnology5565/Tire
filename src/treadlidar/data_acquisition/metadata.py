"""Per-scan acquisition metadata (position, distance, angle, timing, point statistics)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from ..types import PointCloud


@dataclass
class ScanMetadata:
    scan_id: str
    timestamp: float
    n_points: int
    n_frames: int
    duration_s: float
    sensor_position: list           # in the frame of the points
    scan_distance_m: float          # sensor -> centroid of points of interest
    scan_azimuth_deg: float         # angle of the sensor->target ray in the horizontal plane
    scan_elevation_deg: float
    point_density_per_cm2: float    # filled in after tire surface extraction (NaN before)

    def to_dict(self) -> dict:
        return asdict(self)


def describe_scan(scan_id: str, pc: PointCloud, n_frames: int = 1, target: Optional[np.ndarray] = None,
                  density_per_cm2: float = float("nan")) -> ScanMetadata:
    target = pc.xyz.mean(axis=0) if target is None else np.asarray(target, float)
    v = target - pc.sensor_origin
    dist = float(np.linalg.norm(v))
    az = float(np.degrees(np.arctan2(v[1], v[0])))
    el = float(np.degrees(np.arcsin(v[2] / dist))) if dist > 0 else 0.0
    dur = float(pc.t.max() - pc.t.min()) if pc.t is not None and len(pc) else 0.0
    return ScanMetadata(scan_id, float(pc.stamp), len(pc), n_frames, dur,
                        pc.sensor_origin.tolist(), dist, az, el, density_per_cm2)
