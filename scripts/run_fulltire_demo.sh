#!/usr/bin/env bash
# End-to-end M2 demo on SIMULATED data: 18 views of a rotating, unevenly worn wheel -> 360 deg map + protocol.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
OUT=${1:-data/output/fulltire_demo}
SIM=$(mktemp -d)
python3 -m treadlidar.cli simulate --out "$SIM" --n-scans 18 --wheel-step-deg 20 --noise-mm 1.0 --density 40 --depths-mm 3.0,5.0,6.0,4.0
python3 -m treadlidar.cli fulltire "$SIM"/sim_scan_*.npy --out "$OUT" --tread-half-width-mm 95 --expected-grooves 4
echo "Outputs in $OUT"
