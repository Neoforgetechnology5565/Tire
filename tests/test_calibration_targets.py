import numpy as np
import pytest

from treadlidar.calibration.targets import fit_plane, plane_noise, step_height


def _plane(n=20000, sigma=0.002, seed=0, tilt=0.05):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(-0.1, 0.1, (2, n))
    z = tilt * x + rng.normal(0, sigma, n)
    return np.column_stack([x, y, z])


def test_plane_noise_recovers_sigma_and_density():
    m = plane_noise(_plane(sigma=0.002), tol=0.01)
    assert m["noise_std_mm"] == pytest.approx(2.0, rel=0.1)
    assert m["density_per_cm2"] == pytest.approx(20000 / (20 * 20), rel=0.15)


def test_step_height_recovers_known_step_through_noise():
    P = _plane(40000, sigma=0.002, tilt=0.03)
    P[P[:, 0] > 0.0, 2] += 0.006                           # 6 mm step
    s = step_height(P, split_axis=[1, 0, 0])
    assert abs(s["step_mm"] - 6.0) < 0.3 and s["std_error_mm"] < 0.1


def test_step_height_noise_limit_visible():
    """With noise comparable to the step and few points the standard error must expose the uncertainty."""
    P = _plane(300, sigma=0.004)
    P[P[:, 0] > 0.0, 2] += 0.002
    s = step_height(P, split_axis=[1, 0, 0])
    assert s["std_error_mm"] > 0.2


def test_fit_plane_normal():
    n, c, inl = fit_plane(_plane(sigma=0.0005, tilt=0.0))
    assert abs(abs(n[2]) - 1) < 1e-3 and inl.mean() > 0.95
