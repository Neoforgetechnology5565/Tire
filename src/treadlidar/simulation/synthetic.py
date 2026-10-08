"""Synthetic tire-tread scans with exact ground truth.

PURPOSE: unit/integration testing and *sensitivity studies* ("what range noise / density would be
needed for +-1 mm?"). Results from here are NOT evidence about the Unitree L2: every sensor
parameter is a user-set assumption. Not modelled (=> simulation is optimistic): finite laser spot
size / mixed pixels at groove edges, multipath, intensity-dependent range bias, registration error.

World frame: tire axis = +Y, centre at (0, 0, R); tread patch centred at polar angle ``phi0``
measured in the XZ plane from +X. Sensor looks at the patch from outside.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from ..types import PointCloud


@dataclass
class TreadSpec:
    radius_m: float = 0.30
    half_width_m: float = 0.09               # tread region |y| <= half_width
    crown_m: float = 0.004                   # radial drop at the shoulders (parabolic crown)
    # (y_center, width, depth) in metres
    longitudinal: List[Tuple[float, float, float]] = field(default_factory=lambda: [
        (-0.050, 0.010, 0.008), (-0.015, 0.012, 0.008), (0.020, 0.012, 0.008), (0.055, 0.010, 0.008)])
    lateral_width_m: float = 0.006
    lateral_depth_m: float = 0.007
    lateral_pitch_m: float = 0.040
    lateral_zones: List[Tuple[float, float]] = field(default_factory=lambda: [(-0.088, -0.057), (0.062, 0.088)])
    wall_m: float = 0.0015                   # trapezoid wall run (groove side slope)

    def crown(self, y):
        return -self.crown_m * (np.asarray(y) / self.half_width_m) ** 2

    def pattern(self, s, y):
        """Groove offset (<= 0) relative to the local land surface."""
        s, y = np.asarray(s), np.asarray(y)
        h = np.zeros(np.broadcast(s, y).shape)
        for yc, wd, dp in self.longitudinal:
            half = wd / 2
            h = np.minimum(h, -dp * np.clip((half + self.wall_m - np.abs(y - yc)) / self.wall_m, 0, 1))
        sp = (s % self.lateral_pitch_m) - self.lateral_pitch_m / 2
        half = self.lateral_width_m / 2
        lat = -self.lateral_depth_m * np.clip((half + self.wall_m - np.abs(sp)) / self.wall_m, 0, 1)
        zone = np.zeros(h.shape, bool)
        for a, b in self.lateral_zones:
            zone |= (y >= a) & (y <= b)
        return np.where(zone, np.minimum(h, lat), h)

    def surface_dr(self, s, y):
        return self.crown(y) + self.pattern(s, y)


@dataclass
class SensorSim:
    distance_m: float = 0.60                 # sensor to tread surface
    azimuth_deg: float = 0.0                 # angle around the tire from the patch centre normal
    y_offset_m: float = 0.0
    range_noise_mm: float = 2.0              # 1-sigma along the ray -- ASSUMPTION, set from datasheet/measurement
    range_bias_mm: float = 0.0
    density_per_cm2: float = 30.0            # surface sampling density of the accumulated scan
    occlusion: bool = True


def _ray_blocked(spec: TreadSpec, R, C, P, S, phi0, max_travel=0.014, step=0.0005):
    """True where the segment P->S passes through tread material (self-occlusion)."""
    blocked = np.zeros(len(P), bool)
    d = S[None, :] - P
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    for t in np.arange(0.0004, max_travel, step):
        Q = P + d * t
        v = Q - C
        phi = np.arctan2(v[:, 2], v[:, 0])
        rho = np.hypot(v[:, 0], v[:, 2])
        s = R * (phi - phi0)
        blocked |= (rho - R) < spec.surface_dr(s, v[:, 1]) - 1e-6
    return blocked


def generate_scan(spec: TreadSpec = None, sensor: SensorSim = None, arc_length_m: float = 0.16,
                  seed: int = 0, phi0_deg: float = 35.0, clutter: bool = True):
    spec = spec or TreadSpec()
    sensor = sensor or SensorSim()
    rng = np.random.default_rng(seed)
    R = spec.radius_m
    C = np.array([0.0, 0.0, R])
    phi0 = np.radians(phi0_deg)
    n = int(sensor.density_per_cm2 * (arc_length_m * 100) * (2 * spec.half_width_m * 100))
    s = rng.uniform(-arc_length_m / 2, arc_length_m / 2, n)
    y = rng.uniform(-spec.half_width_m, spec.half_width_m, n)
    phi = phi0 + s / R
    rho = R + spec.surface_dr(s, y)
    P = np.column_stack([C[0] + rho * np.cos(phi), y, C[2] + rho * np.sin(phi)])
    u0 = np.array([np.cos(phi0 + np.radians(sensor.azimuth_deg)), 0, np.sin(phi0 + np.radians(sensor.azimuth_deg))])
    S = C + (R + sensor.distance_m) * u0 + np.array([0, sensor.y_offset_m, 0])
    if sensor.occlusion:
        keep = ~_ray_blocked(spec, R, C, P, S, phi0)
        P, s, y = P[keep], s[keep], y[keep]
    rdir = P - S
    rng_true = np.linalg.norm(rdir, axis=1, keepdims=True)
    rdir /= rng_true
    meas = rng_true + (rng.normal(0, sensor.range_noise_mm, (len(P), 1)) + sensor.range_bias_mm) * 1e-3
    X = S + rdir * meas
    parts = [X]
    n_tread = len(X)
    if clutter:
        g = rng.uniform([-0.5, -0.8, 0], [1.2, 0.8, 0], (15000, 3))
        parts.append(g)
        side = []
        for sgn in (-1, 1):
            m = 4000
            sp = rng.uniform(-arc_length_m, arc_length_m, m)
            rr = rng.uniform(R - 0.12, R - 0.01, m)
            ph = phi0 + sp / R
            side.append(np.column_stack([C[0] + rr * np.cos(ph), np.full(m, sgn * (spec.half_width_m + 0.015)),
                                         C[2] + rr * np.sin(ph)]))
        parts += side
        wall = rng.uniform([2.5, -1.0, 0.0], [2.51, 1.0, 1.2], (8000, 3))
        parts.append(wall)
    xyz = np.vstack(parts)
    pc = PointCloud(xyz, sensor_origin=S, frame_id="world",
                    meta={"simulated": True, "n_tread_points": n_tread})
    truth = {"spec": spec, "sensor": sensor, "radius_m": R, "center": C, "axis": np.array([0.0, 1.0, 0.0]),
             "phi0": phi0, "sensor_position": S,
             "grooves_longitudinal": [{"y": a, "width_m": b, "depth_m": c} for a, b, c in spec.longitudinal]}
    return pc, truth
