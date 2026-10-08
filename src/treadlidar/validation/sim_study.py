"""SIMULATION sensitivity study: how do depth bias / spread vary with range noise, density, view angle?

This answers "what sensor performance would be NEEDED", not "what the L2 does". Sensor parameters
are assumptions supplied by the caller. Ground-truth depth is known exactly.
"""
from __future__ import annotations

import itertools
from typing import Iterable

import numpy as np

from ..config import load_config
from ..pipeline import analyze_scan
from ..simulation.synthetic import SensorSim, TreadSpec, generate_scan
from . import accuracy


def run_sweep(noise_mm: Iterable[float], density_per_cm2: Iterable[float], azimuth_deg: Iterable[float] = (0.0,),
              seeds: int = 4, cfg: dict = None, spec: TreadSpec = None, verbose: bool = False) -> list:
    spec = spec or TreadSpec()
    cfg = cfg or load_config(overrides={"segmentation": {"tread_half_width_m": spec.half_width_m + 0.005}})
    truth = np.array([d for _, _, d in spec.longitudinal]) * 1e3
    rows = []
    for sig, dens, az in itertools.product(noise_mm, density_per_cm2, azimuth_deg):
        errs, failures = [], 0
        per_scan_mean = []
        for sd in range(seeds):
            pc, _ = generate_scan(spec, SensorSim(range_noise_mm=sig, density_per_cm2=dens, azimuth_deg=az), seed=sd)
            try:
                r = analyze_scan(pc, cfg, export=False)
                long = r.longitudinal()
            except Exception:
                failures += 1
                continue
            if len(long) != len(truth):
                failures += 1
                continue
            d = np.array([g.depth_m * 1e3 for g in long])
            errs.extend((d - truth).tolist())
            per_scan_mean.append(float(np.mean(d - truth)))
        if errs:
            m = accuracy.accuracy_metrics(np.zeros(len(errs)), errs)
            rows.append({"noise_mm": sig, "density_per_cm2": dens, "azimuth_deg": az, "n_ok": seeds - failures,
                         "n_failed": failures, "bias_mm": m["bias_mm"], "std_mm": m["std_mm"],
                         "rmse_mm": m["rmse_mm"], "loa95_mm": m["loa95_halfwidth_mm"],
                         "within_0p5": m["frac_within_0p5mm"], "within_1p0": m["frac_within_1p0mm"]})
        else:
            rows.append({"noise_mm": sig, "density_per_cm2": dens, "azimuth_deg": az, "n_ok": 0, "n_failed": failures})
        if verbose:
            print(rows[-1])
    return rows
