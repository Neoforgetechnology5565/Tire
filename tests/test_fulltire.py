import json
from dataclasses import replace

import numpy as np
import pytest

from treadlidar import cli
from treadlidar.config import load_config
from treadlidar.data_acquisition.loaders import read_ply
from treadlidar.export import writers
from treadlidar.fulltire.mesh import fulltire_mesh
from treadlidar.fulltire.protocol import find_longitudinal_grooves, run_protocol
from treadlidar.fulltire.stitch import FullTireMap, stitch_views
from treadlidar.fulltire.workflow import analyze_rotating_wheel, export_fulltire
from treadlidar.pipeline import analyze_scan
from treadlidar.simulation.synthetic import SensorSim, TreadSpec, generate_scan

PITCHES = [0.034, 0.040, 0.046, 0.040, 0.036, 0.044]
SPEC = TreadSpec(lateral_pitches_m=PITCHES)
C = 2 * np.pi * SPEC.radius_m
CFG = load_config(overrides={"segmentation": {"tread_half_width_m": 0.095}})
ANGLES = [k * 20.0 for k in range(18)]


def _views(spec, angles, noise=1.0, density=40):
    return [generate_scan(spec, SensorSim(range_noise_mm=noise, density_per_cm2=density), arc_length_m=0.18, seed=k,
                          wheel_angle_deg=a)[0] for k, a in enumerate(angles)]


@pytest.fixture(scope="module")
def uniform():
    clouds = _views(SPEC, ANGLES)
    fm, res, fit = analyze_rotating_wheel(clouds, CFG, ANGLES, C)
    return clouds, fm, res, fit


@pytest.fixture(scope="module")
def protocol(uniform):
    return run_protocol(uniform[1], {"n_positions": 8, "expected_grooves": 4})


# ------------------------------------------------------------------ stitching
def test_full_coverage_and_circumference(uniform):
    _, fm, *_ = uniform
    assert fm.circumference_m == pytest.approx(C)
    assert fm.coverage()["rows_covered_fraction"] > 0.99 and fm.coverage()["uncovered_arc_mm"] < 10
    assert fm.D.shape[0] == round(C / fm.cell) and fm.cell == pytest.approx(C / fm.D.shape[0])


def test_map_depth_matches_truth_everywhere_around_tire(uniform):
    _, fm, *_ = uniform
    P = np.nanmedian(fm.D, axis=0) * 1e3                       # lateral profile over the whole circumference
    grooves = find_longitudinal_grooves(fm)
    assert len(grooves) == 4
    for g in grooves:
        sel = P[g["col0"] + 1:g["col1"]]
        assert abs(np.nanmedian(sel) - 8.0) < 0.4


def test_stitched_lateral_grooves_form_the_true_pitch_sequence(uniform):
    """Alignment check against ground truth: lateral-groove positions in the map follow the real variable-pitch sequence."""
    _, fm, *_ = uniform
    D = fm.D
    zone = (fm.w_centers() > 0.065)                             # right shoulder, lateral grooves only (no longitudinal)
    prof = np.nanmean(D[:, zone], axis=1)
    truth = np.zeros(D.shape[0])
    u = fm.u_centers()
    for k, x in enumerate(u):
        # the analysis +s axis points down while the simulator's pattern coordinate points up: mirrored
        truth[k] = -SPEC.surface_dr(np.array([-x]), np.array([0.075]))[0]
    best = max(range(-8, 9), key=lambda k: np.corrcoef(np.roll(prof, k)[np.isfinite(np.roll(prof, k))],
                                                       truth[np.isfinite(np.roll(prof, k))])[0, 1])
    # a CONSTANT offset between the simulator's u=0 and the fitted frame's s=0 is arbitrary (tire-fixed zero is a
    # convention), so only the shape agreement around the whole circumference is asserted: if the 18 views were
    # misaligned relative to each other the pitch sequence would not correlate.
    ok = np.isfinite(np.roll(prof, best))
    assert np.corrcoef(np.roll(prof, best)[ok], truth[ok])[0, 1] > 0.6


def test_jittered_nominal_angles_are_corrected_to_about_one_cell(uniform):
    """+-1 deg angle jitter (= +-5 mm of arc) must be reduced by the correlation refinement, checked against truth."""
    clouds, *_ = uniform
    rng = np.random.default_rng(5)
    jitter = rng.uniform(-1, 1, len(ANGLES))
    jitter[0] = 0.0
    nominal = [a + j for a, j in zip(ANGLES, jitter)]
    fm, res, _ = analyze_rotating_wheel(clouds, CFG, nominal, C)
    err_mm = jitter * np.pi / 180 * SPEC.radius_m * 1e3                     # nominal - true, as arc [mm]
    ref_mm = np.array([v["refinement_mm"] for v in fm.view_info])
    residual = np.abs(err_mm - ref_mm)                                        # remaining misalignment per view
    assert residual.max() <= 6.0                                              # <= 2 cells
    assert residual.mean() < np.abs(err_mm).mean()                            # refinement improved things on average
    rep = run_protocol(fm, {"n_positions": 8})
    assert abs(rep["summary"]["mean_mm"] - 8.0) < 0.4


def test_refinement_never_applies_large_unreliable_shifts(uniform):
    _, fm, *_ = uniform
    assert all(abs(v["refinement_mm"]) <= 10.0 for v in fm.view_info)
    assert np.allclose([v["refinement_mm"] for v in fm.view_info], 0.0, atol=3.1)    # exact angles -> ~no correction


def test_blind_mode_requires_step_or_angles(uniform):
    _, fm, res, _ = uniform
    with pytest.raises(ValueError):
        stitch_views(res[:3], None, C)
    fm2 = stitch_views(res[:3], None, C, blind_step_deg=20.0, common_frame=True)
    assert any("blind alignment" in w for w in fm2.warnings)


def test_missing_circumference_is_warned(uniform):
    _, _, res, _ = uniform
    fm = stitch_views(res[:2], [0, 20], None, common_frame=True)
    assert any("circumference_m not given" in w for w in fm.warnings)


# ------------------------------------------------------------------ protocol
def test_protocol_measures_every_groove_at_every_position(protocol):
    s = protocol["summary"]
    assert s["n_measurements"] == 32 and s["n_missing"] == 0
    assert abs(s["mean_mm"] - 8.0) < 0.3 and s["std_mm"] < 0.5
    assert [g["groove_index"] for g in s["per_groove"]] == [1, 2, 3, 4]
    assert all(g["around_range_mm"] < 1.5 for g in s["per_groove"])


def test_protocol_limit_check_is_marked_unvalidated_without_uncertainty(protocol):
    lc = protocol["summary"]["limit_check"]
    assert lc["status"] == "PASS" and lc["validated_uncertainty"] is False
    assert any("NO validated uncertainty" in w for w in protocol["warnings"])


def _synthetic_map(depth_mm):
    N, W, cell = 200, 40, 0.003
    D = np.zeros((N, W))
    D[:, 10:16] = depth_mm * 1e-3
    D[:, 25:31] = depth_mm * 1e-3
    return FullTireMap(N * cell, cell, 0.0, D, np.ones_like(D), np.zeros(W))


@pytest.mark.parametrize("depth,unc,expected", [
    (1.7, None, "PASS"), (1.7, 0.5, "INDETERMINATE"), (1.7, 0.05, "PASS"), (1.2, 0.05, "FAIL"),
    (1.2, 0.5, "INDETERMINATE"), (1.0, 0.2, "FAIL"), (3.0, 0.5, "PASS")])
def test_limit_check_logic(depth, unc, expected):
    # groove threshold must sit below the tested depths
    rep = run_protocol(_synthetic_map(depth), {"limit_mm": 1.6, "uncertainty_mm": unc, "groove_threshold_mm": 0.5,
                                               "expected_grooves": 2})
    assert rep["summary"]["limit_check"]["status"] == expected
    assert rep["summary"]["min_mm"] == pytest.approx(depth)


def test_pass_is_withheld_when_a_groove_may_have_been_missed():
    base = {"limit_mm": 1.6, "groove_threshold_mm": 0.5}
    ok = run_protocol(_synthetic_map(3.0), {**base, "expected_grooves": 2})["summary"]["limit_check"]
    assert ok["status"] == "PASS" and ok["guards"] == []
    # unknown groove count: cannot certify
    unk = run_protocol(_synthetic_map(3.0), base)["summary"]["limit_check"]
    assert unk["status"] == "INDETERMINATE" and any("not verified" in g for g in unk["guards"])
    # a 3rd (invisible) groove was expected
    mis = run_protocol(_synthetic_map(3.0), {**base, "expected_grooves": 3})
    assert mis["summary"]["limit_check"]["status"] == "INDETERMINATE"
    assert any("expected" in w for w in mis["warnings"])
    # detection floor too close to the limit
    flo = run_protocol(_synthetic_map(3.0), {"limit_mm": 1.6, "groove_threshold_mm": 1.2, "expected_grooves": 2})
    assert flo["summary"]["limit_check"]["status"] == "INDETERMINATE"
    # FAIL is never softened by the guards (conservative direction)
    f = run_protocol(_synthetic_map(1.0), {**base, "expected_grooves": 3})
    assert f["summary"]["limit_check"]["status"] == "FAIL"


def test_near_limit_depths_are_found_and_not_hidden(tmp_path):
    spec = replace(SPEC, longitudinal=[(y, w, d * 1e-3) for (y, w, _), d in zip(SPEC.longitudinal, [1.6, 2.0, 2.5, 3.0])])
    angles = [k * 20.0 for k in range(18)]
    fm, _, _ = analyze_rotating_wheel(_views(spec, angles, noise=0.5, density=40), CFG, angles, C)
    rep = run_protocol(fm, {"n_positions": 8, "expected_grooves": 4})
    per = [g["mean_mm"] for g in rep["summary"]["per_groove"]]
    assert len(per) == 4
    assert np.max(np.abs(np.array(per) - np.array([1.6, 2.0, 2.5, 3.0]))) < 0.35


def test_unevenness_metrics_detect_shoulder_wear():
    fm = _synthetic_map(6.0)
    fm.D[:, 25:31] = 3.0e-3                                    # right groove more worn
    rep = run_protocol(fm, {"groove_threshold_mm": 0.5})
    s = rep["summary"]
    assert s["max_across_tread_range_mm"] == pytest.approx(3.0)
    assert s["left_minus_right_mm"] == pytest.approx(3.0)


# ------------------------------------------------------------------ mesh + export
def test_full_mesh_is_a_closed_ring_and_manifold(uniform):
    _, fm, *_ = uniform
    V, F, col, depth = fulltire_mesh(fm)
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    assert cnt.max() <= 2                                       # manifold
    ang = np.arctan2(V[:, 2], V[:, 0]) % (2 * np.pi)
    # faces exist across the seam (angle ~0 / ~2pi): ring closure
    tri_ang = ang[F]
    assert ((tri_ang.max(1) - tri_ang.min(1)) > np.pi).any()
    r = np.hypot(V[:, 0], V[:, 2])
    assert abs(np.median(r) - SPEC.radius_m) < 0.006 and (r.max() - r.min()) < 0.02


def test_full_tire_exports(tmp_path, uniform, protocol):
    _, fm, *_ = uniform
    paths = export_fulltire(fm, protocol, tmp_path)
    for k in ("mesh_ply", "mesh_stl", "mesh_obj", "protocol_json", "measurements_csv", "unrolled_png"):
        assert (tmp_path / paths[k].split("/")[-1]).stat().st_size > 100
    V, F, *_ = fulltire_mesh(fm)
    assert len(read_ply(paths["mesh_ply"])) == len(V)
    sv, sf = writers.read_stl(paths["mesh_stl"])
    assert len(sf) == len(F)
    rpt = json.loads((tmp_path / "TIRE_001_fulltire_protocol.json").read_text())
    assert rpt["summary"]["n_measurements"] == 32 and rpt["circumference_mm"] == pytest.approx(C * 1e3)


# ------------------------------------------------------------------ partial coverage + uneven wear
@pytest.fixture(scope="module")
def worn_partial():
    spec = replace(SPEC, longitudinal=[(y, w, d * 1e-3) for (y, w, _), d in zip(SPEC.longitudinal, [3.0, 5.0, 6.0, 4.0])])
    angles = [k * 20.0 for k in range(6)]                       # covers only ~140 of 360 degrees
    fm, res, _ = analyze_rotating_wheel(_views(spec, angles, noise=0.5, density=50), CFG, angles, C)
    return fm, run_protocol(fm, {"n_positions": 12})


def test_partial_coverage_is_reported_and_never_interpolated(worn_partial):
    fm, rep = worn_partial
    assert fm.coverage()["rows_covered_fraction"] < 0.55
    assert rep["summary"]["n_missing"] > 0
    missing = [m for m in rep["measurements"] if not m["measured"]]
    assert missing and all(np.isnan(m["depth_mm"]) for m in missing)
    assert any("not covered" in w for w in rep["warnings"])


def test_uneven_wear_recovered(worn_partial):
    _, rep = worn_partial
    per = {g["groove_index"]: g["mean_mm"] for g in rep["summary"]["per_groove"]}
    for idx, truth in zip((1, 2, 3, 4), (3.0, 5.0, 6.0, 4.0)):
        assert abs(per[idx] - truth) < 0.5, (idx, per[idx], truth)
    assert rep["summary"]["max_across_tread_range_mm"] > 1.5


# ------------------------------------------------------------------ M1 regression: shallow grooves
def test_shallow_grooves_are_measured_without_large_bias():
    spec = replace(TreadSpec(), longitudinal=[(y, w, d * 1e-3) for (y, w, _), d in zip(TreadSpec().longitudinal, [4.0, 5.0, 6.0, 7.0])])
    errs = []
    for seed in range(3):
        pc, _ = generate_scan(spec, SensorSim(range_noise_mm=1.0, density_per_cm2=40), seed=seed)
        long = analyze_scan(pc, CFG, export=False).longitudinal()
        assert len(long) == 4
        errs += [g.depth_m * 1e3 - t for g, t in zip(long, (4, 5, 6, 7))]
    assert abs(np.mean(errs)) < 0.3 and np.max(np.abs(errs)) < 0.8


# ------------------------------------------------------------------ CLI
def test_cli_fulltire_end_to_end(tmp_path, capsys):
    scans = tmp_path / "s"
    cli.main(["simulate", "--out", str(scans), "--n-scans", "3", "--wheel-step-deg", "20", "--noise-mm", "1"])
    side = json.loads((scans / "sim_scan_02.sensor.json").read_text())
    assert side["wheel_angle_deg"] == 20.0 and side["simulated"] is True
    cli.main(["fulltire", *map(str, sorted(scans.glob("sim_scan_*.npy"))), "--out", str(tmp_path / "o"),
              "--tread-half-width-mm", "95", "--n-positions", "6"])
    out = capsys.readouterr().out
    assert "3 views" in out and "limit check" in out and "NO validated" not in out.split("limit check")[0]
    rpt = json.loads((tmp_path / "o" / "TIRE_001_fulltire_protocol.json").read_text())
    assert rpt["summary"]["n_missing"] > 0                       # 3 views cannot cover 360 degrees
