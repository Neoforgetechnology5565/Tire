#!/usr/bin/env python3
"""Characterise the L2 on physical targets.

  scripts/characterize_sensor.py plane  flat_board.npy  --tol 0.01
  scripts/characterize_sensor.py step   step_target.npy --known-mm 4.0

Record each target with tire_scan_recorder at the SAME distance/angle/duration you will use on tires.
Repeat at several distances (e.g. 0.4, 0.6, 0.8, 1.0 m) to get noise-vs-distance.
"""
import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/src")
from treadlidar.calibration.targets import plane_noise, step_height  # noqa: E402
from treadlidar.data_acquisition.loaders import load_points  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["plane", "step"])
    p.add_argument("file")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--tol", type=float, default=0.01)
    p.add_argument("--known-mm", type=float)
    a = p.parse_args()
    P = load_points(a.file, scale=a.scale).xyz
    out = plane_noise(P, a.tol) if a.mode == "plane" else step_height(P, tol=a.tol)
    if a.mode == "step" and a.known_mm is not None:
        out["known_mm"] = a.known_mm
        out["error_mm"] = abs(out["step_mm"]) - a.known_mm
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
