"""Core data containers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np


@dataclass
class PointCloud:
    """A point cloud in metres, in the sensor or world frame named by ``frame_id``.

    ``t`` holds per-point time offsets in seconds relative to ``stamp`` (needed for
    deskewing). ``sensor_origin`` is the sensor position in the same frame as ``xyz``.
    """

    xyz: np.ndarray
    intensity: Optional[np.ndarray] = None
    t: Optional[np.ndarray] = None
    stamp: float = 0.0
    frame_id: str = ""
    sensor_origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.xyz = np.ascontiguousarray(self.xyz, dtype=np.float64).reshape(-1, 3)
        self.sensor_origin = np.asarray(self.sensor_origin, dtype=np.float64).reshape(3)

    def __len__(self) -> int:
        return self.xyz.shape[0]

    def select(self, idx) -> "PointCloud":
        return PointCloud(
            self.xyz[idx],
            None if self.intensity is None else self.intensity[idx],
            None if self.t is None else self.t[idx],
            self.stamp, self.frame_id, self.sensor_origin.copy(), dict(self.meta),
        )

    def transformed(self, T: np.ndarray) -> "PointCloud":
        out = self.select(slice(None))
        out.xyz = self.xyz @ T[:3, :3].T + T[:3, 3]
        out.sensor_origin = T[:3, :3] @ self.sensor_origin + T[:3, 3]
        return out

    @staticmethod
    def concat(clouds: Sequence["PointCloud"]) -> "PointCloud":
        clouds = list(clouds)
        xyz = np.vstack([c.xyz for c in clouds])
        inten = None
        if all(c.intensity is not None for c in clouds):
            inten = np.concatenate([c.intensity for c in clouds])
        return PointCloud(xyz, inten, None, clouds[0].stamp, clouds[0].frame_id,
                          clouds[0].sensor_origin.copy(), {"n_clouds": len(clouds)})
