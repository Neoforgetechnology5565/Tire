#!/usr/bin/env bash
# End-to-end demo on SIMULATED data (no sensor needed). Real data: replace the files and use --origin real.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
OUT=${1:-data/output/demo}
python3 -m treadlidar.cli analyze examples/sim_data/sim_scan_01.npy --out "$OUT/single" --tread-half-width-mm 95
python3 -m treadlidar.cli measure examples/sim_data/sim_scan_01.npy --tread-half-width-mm 95 --at 0,0
python3 -m treadlidar.cli validate examples/sim_data/sim_scan_0*.npy --reference examples/sim_data/sim_reference.csv \
    --origin simulated --out "$OUT/validation" --tread-half-width-mm 95
echo "Outputs in $OUT (PLY/STL/OBJ meshes, report JSON/CSV, depth map, cross-section, accuracy, repeatability)"
