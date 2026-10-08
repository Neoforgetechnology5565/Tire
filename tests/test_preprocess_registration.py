import numpy as np
from scipy.spatial.transform import Rotation

from treadlidar.preprocessing import filters, motion
from treadlidar.registration.icp import icp, register_scans
from treadlidar.types import PointCloud


def test_statistical_outlier_removes_isolated_points():
    rng = np.random.default_rng(0)
    P = np.vstack([rng.normal(0, 0.01, (2000, 3)), [[1, 1, 1], [-1, 1, 0.5]]])
    m = filters.statistical_outlier_mask(P, 16, 3.0)
    assert not m[-1] and not m[-2] and m[:2000].mean() > 0.98


def test_range_filter_and_voxel():
    P = np.array([[0.01, 0, 0], [1, 0, 0], [20, 0, 0]])
    assert filters.range_filter(P, [0, 0, 0], 0.05, 5).tolist() == [False, True, False]
    assert len(filters.voxel_downsample(np.random.rand(1000, 3), 0.0)) == 1000   # off by default


def test_deskew_with_gyro_recovers_static_scene():
    rng = np.random.default_rng(1)
    world = rng.uniform(-1, 1, (3000, 3)) + [3, 0, 0]
    stamp, n = 100.0, 3000
    t = np.linspace(0, 0.1, n)
    imu_t = np.linspace(stamp - 0.01, stamp + 0.11, 200)
    wz = 0.8   # rad/s yaw while scanning
    gyro = np.tile([0, 0, wz], (len(imu_t), 1))
    # sensor yaws by wz*(t_i - stamp): point measured in the sensor frame at t_i
    R = Rotation.from_rotvec(np.outer(wz * t, [0, 0, 1]))
    measured = R.inv().apply(world)
    out = motion.deskew_with_gyro(measured, t, stamp, imu_t, gyro, t_ref=stamp)
    assert np.abs(out - world).max() < 1e-6
    assert np.abs(measured - world).max() > 1e-2          # compensation actually did something


def test_deskew_rejects_uncovered_time():
    import pytest
    with pytest.raises(ValueError):
        motion.deskew_with_gyro(np.zeros((2, 3)), np.array([0.0, 0.1]), 10.0, np.array([10.05, 10.2]), np.zeros((2, 3)))


def test_deskew_constant_velocity():
    P = np.array([[1.0, 0, 0]])
    out = motion.deskew_constant_velocity(P, np.array([0.1]), [1.0, 0, 0], [0, 0, 0])
    assert np.allclose(out, [[1.1, 0, 0]])


def _bumpy(n=6000, seed=2):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(-0.1, 0.1, (2, n))
    z = 0.01 * np.sin(60 * x) * np.cos(45 * y) + 0.5 * x ** 2 + 0.3 * x * y
    return np.column_stack([x, y, z])


def test_icp_recovers_known_transform_on_nondegenerate_surface():
    A = _bumpy()
    T = np.eye(4)
    T[:3, :3] = Rotation.from_euler("xyz", [0.5, -0.8, 1.2], degrees=True).as_matrix()
    T[:3, 3] = [0.004, -0.003, 0.002]
    B = A @ T[:3, :3].T + T[:3, 3]
    Tr, rmse, fit, ok = icp(B, A, max_corr=0.02, max_iter=200)
    back = B @ Tr[:3, :3].T + Tr[:3, 3]
    assert np.linalg.norm(back - A, axis=1).mean() < 2e-4


def test_icp_on_tread_patch_is_poorly_constrained_documented_limitation(sim):
    """A cylinder is invariant to rotation about its axis, so ICP on a tread patch cannot be trusted
    to sub-mm: this test pins the *known* behaviour (see docs/LIO_INTEGRATION.md)."""
    pc, _ = sim
    A = pc.xyz[: pc.meta["n_tread_points"]]
    T = np.eye(4)
    T[:3, 3] = [0.004, -0.003, 0.002]
    B = A @ T[:3, :3].T + T[:3, 3]
    Tr, *_ = icp(B, A, max_corr=0.03)
    err = np.linalg.norm((B @ Tr[:3, :3].T + Tr[:3, 3]) - A, axis=1).mean()
    assert err < 0.01          # converges to the right neighbourhood (< 1 cm) but NOT guaranteed sub-mm


def test_register_scans_merges_all_points(sim):
    pc, _ = sim
    a = PointCloud(pc.xyz[:3000])
    b = PointCloud(pc.xyz[:3000] + [0.001, 0, 0])
    merged, diag = register_scans([a, b])
    assert len(merged) == 6000 and len(diag) == 2
