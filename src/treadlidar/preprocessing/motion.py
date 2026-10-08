"""LiDAR/IMU time alignment and motion compensation (deskewing).

Two entry points:
* ``deskew_with_gyro``: rotation-only compensation from raw IMU gyro (hand-held / pan motion).
* ``deskew_constant_velocity``: rotation+translation from a velocity estimate (e.g. from Point-LIO).

For a stationary sensor no deskew is needed. Per-point times ``t`` are seconds relative to the
cloud stamp (the L2 driver publishes a per-point ``time`` field; verify its units on your device).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def integrate_gyro(imu_t: np.ndarray, gyro: np.ndarray) -> Rotation:
    """Orientation at each IMU sample (relative to first sample) from body-rate integration."""
    imu_t = np.asarray(imu_t, float)
    dt = np.diff(imu_t)
    w_mid = 0.5 * (gyro[1:] + gyro[:-1])
    incr = Rotation.from_rotvec(w_mid * dt[:, None])
    q = [Rotation.identity()]
    for r in incr:
        q.append(q[-1] * r)
    return Rotation.concatenate(q)


def deskew_with_gyro(xyz, point_t, stamp, imu_t, gyro, t_ref=None):
    """Rotate each point into the sensor orientation at ``t_ref`` (default: stamp)."""
    abs_t = stamp + np.asarray(point_t, float)
    t_ref = stamp if t_ref is None else t_ref
    imu_t = np.asarray(imu_t, float)
    if abs_t.min() < imu_t[0] or abs_t.max() > imu_t[-1] or not (imu_t[0] <= t_ref <= imu_t[-1]):
        raise ValueError("IMU samples do not cover the point time span; cannot synchronise")
    slerp = Slerp(imu_t, integrate_gyro(imu_t, np.asarray(gyro, float)))
    r_i = slerp(abs_t)
    r_ref = slerp([t_ref])[0]
    # p_ref = R_ref^-1 R_i p_i
    return (r_ref.inv() * r_i).apply(xyz)


def deskew_constant_velocity(xyz, point_t, lin_vel, ang_vel, t_ref=0.0):
    """Compensate constant body-frame twist (v [m/s], w [rad/s]) over the scan."""
    dt = (np.asarray(point_t, float) - t_ref)[:, None]
    rot = Rotation.from_rotvec(np.asarray(ang_vel, float)[None, :] * dt)
    return rot.apply(xyz) + np.asarray(lin_vel, float)[None, :] * dt
