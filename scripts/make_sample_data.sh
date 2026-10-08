#!/usr/bin/env bash
# Regenerate the SIMULATED sample scans used by the tests/examples (ground-truth depths in sim_reference.csv).
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src python3 -m treadlidar.cli simulate --out examples/sim_data --n-scans 5 --noise-mm 1.0 --density 40
