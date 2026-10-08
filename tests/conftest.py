import numpy as np
import pytest

from treadlidar.config import load_config
from treadlidar.pipeline import analyze_scan
from treadlidar.simulation.synthetic import SensorSim, TreadSpec, generate_scan

SPEC = TreadSpec()
TRUE_DEPTH_MM = 8.0


@pytest.fixture(scope="session")
def cfg():
    return load_config(overrides={"segmentation": {"tread_half_width_m": SPEC.half_width_m + 0.005}})


@pytest.fixture(scope="session")
def sim(cfg):
    return generate_scan(SPEC, SensorSim(range_noise_mm=1.0, density_per_cm2=40), seed=1)


@pytest.fixture(scope="session")
def result(sim, cfg):
    return analyze_scan(sim[0], cfg, "T1", "S1", export=False)
