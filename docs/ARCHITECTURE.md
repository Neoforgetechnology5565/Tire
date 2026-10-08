# Architecture and design decisions

```
L2 ──▶ tire_scan_recorder (ROS2) ──▶ data/raw/*.npy + .sensor.json (+ IMU)         [stationary: frames concatenated]
      └▶ rosbag2 ──▶ data_acquisition.ros2_bag                                       [offline]
      └▶ (moving) Point-LIO in ROS1 container ──▶ registered PCD                     [lio/README.md]
        data_acquisition.loaders  (npy/npz/xyz/csv/ply/pcd)  ─ same code path for recorded and live data
          ▼
preprocessing (range filter, optional SOR, deskew)      registration (ICP fallback)
          ▼
tire_segmentation: ROI → ground RANSAC (noise-adaptive) → voxel-occupancy clustering (labels mapped back to full-res points)
          ▼
tread_analysis.cylinder: axis search (horizontal sweep / hint) → RANSAC circle + M-estimator scoring → robust LS → land-only refit
          ▼   unwrap to (s, w, dr); lateral crop to the tread
tread_analysis.reference: crown polynomial in w (or per-rib lines) + circumferential bow b1·s+b2·s², asymmetric trimming, noise from the UPPER residual side
          ▼
tread_analysis.heightmap: per-cell median of RAW points (auto cell size ≈ 4 pts/cell, no downsampling)
          ▼
tread_analysis.grooves: depth map D = ref − z → threshold (≥ 3σ_cell) → longitudinal/lateral separation by directional morphology → core depth
          ▼                     └─ density.py: spacing, density, noise, per-groove resolvability
measurement.depth: stats, measure_at(s,w), groove ordering        reconstruction.mesh: height-field mesh (no smoothing by default)
          ▼
export (PLY/STL/OBJ/JSON/CSV)   validation (accuracy, repeatability, A/B/C)   viewer (Open3D, matplotlib)
```

## Why these choices
* **Height-field, not Poisson.** The tread is a thin relief on a cylinder: unwrapping gives an exact height field, and the mesh vertices are
  measured heights. Poisson regularises and rounds groove edges; Open3D Poisson/BPA are provided only for comparison (`reconstruction.mesh.open3d_mesh`).
* **Smoothing is off by default and its damage is measurable:** in simulation, a Gaussian of sigma = 1 cell turned 8.0 mm grooves into 7.4 mm and sigma = 2 into 5.5 mm
  (`tests/test_analysis.py::test_smoothing_destroys_depth_and_default_is_off`). `report.depth_by_stage` compares groove depth from raw points / filtered points / mesh.
* **Reference surface ≠ highest point.** Land points are those within a noise-scaled tolerance below the fitted surface; groove bottoms never enter the fit; the noise
  estimate uses only residuals *above* the reference (groove points cannot contaminate it).
* **Bow term.** A cylinder fitted to a ~30° arc has a poorly constrained radius; the residual circumferential sag is estimated and removed in the reference.
* **Detection ≠ measurement.** Empty cells are filled and lightly blurred only to *locate* grooves; reported depths come from measured, un-blurred cells.
* **Fail loudly.** Implausible radius → warning and no diameter; threshold auto-raised to ≥ 3σ_cell with a warning; segmentation failures raise; validation refuses unpaired scans.

## Defects found and fixed during development (kept for transparency)
1. Normal-based axis estimation was dominated by groove walls → replaced by horizontal-axis sweep scored by RANSAC circle + truncated-quadratic cost.
2. Sidewall/ground clutter attached to the tire cluster biased the cylinder → lateral crop inside the fit, noise-adaptive ground removal, radius prior.
3. Noise estimated from the land set ran away into the groove population → estimate from the upper half only, tolerance clamped.
4. Longitudinal/lateral grooves merged at junctions → directional morphological opening.
5. `np.linalg.svd` full_matrices default built an N×N matrix (3 GB for 20 k points) → fixed.
6. A simulator artifact (noise-free sidewall clutter) made the fit lock on to a perfect plane → clutter now carries range noise, scaled with density.

## Known limitations
* **No real L2 data has been processed.** All accuracy numbers in this repo come from simulation with *assumed* sensor parameters.
* Simulator omits beam-footprint mixed pixels, multipath, intensity-dependent bias, registration error → optimistic for narrow grooves.
* Axis search assumes an (approximately) level vehicle unless `--axis-hint` is given; very short arcs (< ~20°) make the radius undeterminable (reported).
* ICP on a tread patch is poorly constrained along the circumference (a cylinder slides around its axis) — do not rely on it for sub-mm registration; use fixed pose or LIO.
* Groove *width* is approximate (cell-size limited); *depth* is the validated quantity. Sipes are not resolved.
* Only one patch (a partial arc) is analysed; full-circumference unwrapping is the moving-vehicle milestone.
