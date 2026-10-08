# Third-party dependencies and licences

"Verified" = read from the project's own page / package metadata during development (2026-10). This table is
engineering due diligence, **not legal advice**: have counsel review before commercial distribution.

## Used by the shipped `treadlidar` package (permissive; commercial use OK)

| Dependency | Role | Licence | How verified |
|---|---|---|---|
| numpy 2.x | arrays | BSD-3-Clause (+ bundled permissive components) | package metadata |
| scipy 1.x | KD-tree, optimisation, morphology, stats | BSD (OSI) | package metadata |
| matplotlib 3.x | headless figures | PSF-based matplotlib licence (permissive) | package metadata |
| PyYAML 6.x | config | MIT | package metadata |
| open3d 0.20 (optional) | interactive viewer, optional Poisson/BPA | MIT | package metadata |
| pytest (test only) | tests | MIT | package metadata |

PLY/STL/OBJ/PCD readers and writers, ICP, RANSAC, cylinder fit, reference-surface estimation, groove detection
and all validation code are **original code in this repository** (no third-party code copied).

## External projects evaluated / used as separate processes

| Project | Licence | Used how | Commercial note |
|---|---|---|---|
| `unitreerobotics/unilidar_sdk2` | **BSD-3-Clause** (verified from repo page) | L2 driver (ROS1 Noetic / **ROS2 Foxy**) run as a separate node | permissive |
| `unitreerobotics/point_lio_unilidar` | **GPL-2.0** (verified) | optional LIO for moving sensor, **ROS1 only**, separate process/container | copyleft: keep out of the proprietary package; exchange files only; legal review |
| `hku-mars/Point-LIO` | not determinable from the repo page (LICENSE file linked, not read) | not used | **read LICENSE before any use** |
| `hku-mars/FAST_LIO` | **GPL-2.0** (verified) | not used (no L2 support; copyleft) | copyleft |
| `bohundan/treadscan` | **MIT** (verified from repo page) | **evaluated, not used.** It is camera/image based (vehicle detection -> tire unwrapping to a 2D tread image) and has no point-cloud/LiDAR input and no tread-depth measurement | permissive; only conceptually relevant (unwrapping) |
| `rosbags` (ROS1<->ROS2 bag conversion) | not verified | possible bridge for the Noetic side | verify before use |
| PCL | BSD-3-Clause (general knowledge, not re-verified) | used only inside the ROS driver/LIO stacks, not by `treadlidar` | verify |

Patents: the literature search found patents on LiDAR/laser tread-depth measurement (e.g. US 11707948, US 12296622,
US 7975540, CN 121977468 A). They were read only as background; **no freedom-to-operate analysis was done**.
That is a separate legal task before commercialising a measurement product.

## Custom code
All code under `src/`, `tests/`, `scripts/`, `ros2/` was written for this project and carries no third-party licence
obligations beyond the dependencies above. Add your own LICENSE/copyright header as the commercial owner.
