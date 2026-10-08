`sim_data/` holds 5 **SIMULATED** scans (`sim_scan_XX.npy`, float32 metres) with sidecar `.sensor.json` (`"simulated": true`) and
`sim_reference.csv` (ground-truth depths). Regenerate: `bash scripts/make_sample_data.sh`. They exist so the pipeline, tests and CLI can run without
a sensor; they carry no information about the real L2.
