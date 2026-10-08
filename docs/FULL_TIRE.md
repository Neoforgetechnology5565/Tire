# Milestone 2 - full-tire reconstruction and automated measurement

**Status: implemented and tested on SIMULATED data only (23 tests in `tests/test_fulltire.py`). The feasibility gate of
Milestone 1 (real L2 + physical tire + reference gauge) has NOT been passed. Treat every M2 output as unvalidated until
`treadlidar validate --origin real` has produced an A/B verdict for your setup.** The limit check below is an engineering aid,
not an inspection result.

## What it does
```
fixed sensor, wheel turned in steps (marked with tape)         e.g. 18 views x 20 deg
  -> per-view segmentation (M1)
  -> ONE cylinder frame fitted on the pooled tire points of all views (same axis/centre/radius in every view)
  -> every view analysed in that frame (reference surface, depth map D)
  -> stitch_views: merge depth maps in tire-fixed arc coordinates u = s - R*angle (mod circumference)
  -> FullTireMap (360 deg x tread width depth map, uncovered cells stay empty)
  -> run_protocol: depth of every longitudinal groove at N positions around the tire + wear/uneven-wear metrics + limit check
  -> closed-ring mesh (PLY/STL/OBJ), unrolled depth-map figure, protocol JSON/CSV
```
Why a common frame: a ~30 deg arc determines the cylinder centre/radius only to a few mm, so per-view fits shift each view's
arc origin; pooling all views (same physical cylinder) removes that scatter. `s = 0` is defined as the direction from the axis towards
the sensor, a fixed physical direction. Merging depth maps (not points) keeps each view's own reference surface.

## Procedure
1. Sensor on a rigid tripod, 0.4-0.8 m from the tread, wheel on a stand or jacked up (it must be free to rotate). The sensor must not move.
2. Mark the wheel with tape. Turn it by a fixed step (default 20 deg; the arc seen by one view is ~35 deg for a 0.18 m window, so keep **>= 25 %
   overlap**, i.e. step <= ~25 deg) and record each view (`record_l2.launch.py ... wheel_angle_deg:=20`). Positive angle = **the tread at the sensor moves downward**.
3. Measure the circumference with a tape at the tread centre (strongly recommended): a short arc cannot give it to better than cm.
4. Run: `treadlidar fulltire data/raw/TIRE_001_SCAN_*.npy --out data/output/t1 --circumference-mm 1885 --axis-hint 0,1,0 --tread-half-width-mm 85 --expected-grooves 4`
   Angles are read from `wheel_angle_deg` in the `.sensor.json` sidecars (or `--angles a0,a1,...`; `--blind-step-deg` if only the step is known).

## Alignment between views
Nominal wheel angles are refined by correlating the circumferential (lateral-groove) depth profile of each new view with the map so far,
**only** if the overlap is >= 60 mm, the correlation >= 0.8 and the peak is clearly unique; otherwise the nominal angle is kept and the view is
flagged. In simulation (variable pitch, +-1 deg = +-5 mm angle jitter) the remaining misalignment is <= 2 cells (6 mm). Uniform-pitch tread
is ambiguous (the correlation repeats every pitch): the search window is limited to +-10 mm and a runner-up check applies.
Longitudinal-groove depth does not depend on circumferential alignment; alignment mainly affects where around the tire a value is attributed (6 mm ~ 1 deg).

## Protocol output (`*_fulltire_protocol.json`)
Per groove x position: depth (median over a +-4 mm window and the central half of the groove width), number of cells, `measured` flag
(missing = < 50 % cells covered; **never interpolated**). Summary: min/mean/median/max/std, per-groove min/mean/max/range-around-the-tire,
max across-tread range (uneven wear), shoulder-minus-centre and left-minus-right wear, coverage (uncovered arc in mm).

### Limit check (default limit 1.6 mm - configurable, not legal advice)
* No `--uncertainty-mm`: reports PASS/FAIL **marked unvalidated**. With a validated uncertainty `u` (from `validate` on real data):
  PASS if `min - u >= limit`, FAIL if `min + u < limit`, else INDETERMINATE.
* **Guards that downgrade PASS to INDETERMINATE** (FAIL is never softened): groove count not verified (`--expected-grooves`), detected count differs
  from the expected count, or the groove-detection floor is more than half the limit. Reason: the most dangerous failure is a *missed* worn groove.

## What simulation says (assumed sensor, NOT the L2)
* Uniform 8 mm tire, sigma 1 mm, 40 pts/cm2, 18 views: 48 measurements, mean 8.03 mm (true 8.0), per-position scatter (SD) 0.22 mm.
* Unevenly worn 3/5/6/4 mm grooves recovered within 0.5 mm; near-limit grooves (1.6/2.0/2.5/3.0 mm) at sigma 0.5 mm read 1.49/1.86/2.51/3.02,
  at sigma 1.0 mm about 0.1-0.3 mm low. Accumulating 18 views is what makes these shallow grooves detectable; a single view at sigma 1 mm is not enough for 2-3 mm grooves.
* Real tires differ in ways the simulator does not model (sipes, tread-block wear, rubber reflectance, mixed pixels at groove edges).

## Limitations
* A tire on a vehicle cannot be rotated in the contact patch: the contact area and inner side stay uncovered and are reported as such.
* Requires a stationary, rigid sensor and a wheel angle known to ~1-2 deg (refinement helps on patterned tread only).
* Mesh is a height field of the tread band (open at the shoulders); sidewalls are not reconstructed.
* Outer diameter in the report is C/pi from the supplied circumference, not an independent measurement.
* Moving-vehicle scanning (continuous rolling) is **not** implemented; `lio/README.md` lists the prepared interfaces.
