# Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `tire segmentation found only N points` | ROI/ground parameters, sensor too far, tire out of range | check `info` bbox; enable/adjust `segmentation.roi`; confirm `min/max_range_m`; scan closer |
| `cylinder fit failed: no circle within radius_range_m` | wrong `radius_range_m` for this tire, or wheel axis far from horizontal | set `radius_range_m` from the tire code (±10 %); pass `--axis-hint x,y,z`; `axis_search: auto` |
| warning `tire radius NOT determinable` | arc too short/noisy; fitted radius at/outside the range | depth is still measured (bow term), but no diameter; scan a longer arc or give `--axis-hint` |
| `no longitudinal grooves detected` / `threshold raised` | tread not resolved at this noise/density (or segmentation wrong) | read `report.density`, `resolvability`; accumulate more frames; closer range; do the step-target test |
| groove numbering differs from reference | detected groove count != reference count -> scan excluded | check `validation_report.json -> excluded_scans`; adjust `tread_half_width_m`; fix reference numbering (left→right from the sensor) |
| lateral grooves missing | self-occlusion at oblique view / too coarse cell | view more frontally; denser accumulation |
| depths too small after enabling smoothing | by design | set `smoothing_sigma_cells: 0` |
| `--origin real` refused | input marked simulated | use real recordings; never relabel |
| viewer: `libEGL.so.1` / GL errors | no GL libraries / headless | `apt install libegl1 libgl1`, run with a display; headless runs use the matplotlib figures instead |
| ROS: no `unilidar/cloud` | driver not running / network | set PC interface for the L2's 192.168.1.2 target IP (see unilidar_sdk2 README), `ros2 topic list` |
| Point-LIO has no ROS2 build | upstream is ROS1 Noetic | use the Noetic container (`lio/README.md`) |
| MemoryError in numpy SVD | (fixed) `full_matrices=True` on tall matrices | update; use `full_matrices=False` in new code |
