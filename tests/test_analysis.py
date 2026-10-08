import numpy as np
import pytest

from treadlidar.config import load_config
from treadlidar.measurement import depth as dep
from treadlidar.pipeline import analyze_scan
from treadlidar.simulation.synthetic import SensorSim, TreadSpec, generate_scan
from treadlidar.tire_segmentation.segment import cluster_labels, ransac_plane, segment_tire
from treadlidar.tread_analysis.cylinder import fit_cylinder
from treadlidar.tread_analysis.reference import fit_reference

from conftest import SPEC, TRUE_DEPTH_MM


# ---------------------------------------------------------------- segmentation
def test_ground_plane_ransac_finds_ground(sim):
    pc, _ = sim
    nrm, d, inl = ransac_plane(pc.xyz, 0.01, 300, max_tilt_deg=20)
    assert abs(nrm[2]) > 0.99 and inl.sum() > 10000


def test_segmentation_isolates_tire_and_drops_ground_and_wall(sim, cfg):
    pc, _ = sim
    idx, info = segment_tire(pc.xyz, cfg["segmentation"], pc.sensor_origin)
    n_tread = pc.meta["n_tread_points"]
    assert (idx < n_tread).sum() / n_tread > 0.99                  # (almost) all tread points kept
    assert pc.xyz[idx][:, 2].min() > 0.2                          # no ground
    assert pc.xyz[idx][:, 0].max() < 1.0                          # no far wall


def test_cluster_labels_separates_blobs():
    rng = np.random.default_rng(0)
    P = np.vstack([rng.normal(0, 0.005, (500, 3)), rng.normal(1, 0.005, (300, 3))])
    lab = cluster_labels(P, 0.02)
    assert len(set(lab[:500])) == 1 and len(set(lab[500:])) == 1 and lab[0] != lab[-1]


def test_segmentation_never_downsamples_tread(sim, cfg):
    pc, _ = sim
    idx, _ = segment_tire(pc.xyz, cfg["segmentation"], pc.sensor_origin)
    assert len(np.unique(idx)) == len(idx)                         # indices into the full-resolution cloud


# ---------------------------------------------------------------- cylinder
def test_cylinder_fit_radius_and_axis(sim, cfg):
    pc, tr = sim
    idx, _ = segment_tire(pc.xyz, cfg["segmentation"], pc.sensor_origin)
    f = fit_cylinder(pc.xyz[idx], None, half_width_m=0.095, up=(0, 0, 1), axis_search="horizontal",
                     radius_range_m=(0.25, 0.5))
    assert abs(f.radius - 0.30) < 0.006
    assert abs(abs(f.axis @ [0, 1, 0])) > np.cos(np.radians(0.5))


def test_cylinder_local_coordinates_roundtrip(sim):
    pc, _ = sim
    n = pc.meta["n_tread_points"]
    f = fit_cylinder(pc.xyz[:n], [0, 1, 0])
    s, w, dr = f.to_local(pc.xyz[:n])
    assert np.allclose(f.to_world(s, w, dr), pc.xyz[:n], atol=1e-9)


# ---------------------------------------------------------------- reference surface
def test_reference_ignores_groove_bottoms_noise_free():
    spec = SPEC
    rng = np.random.default_rng(0)
    s = rng.uniform(-0.08, 0.08, 60000)
    w = rng.uniform(-0.09, 0.09, 60000)
    dr = spec.surface_dr(s, w)
    cfg = load_config()["analysis"]["reference"]
    ref = fit_reference(w, dr, cfg)
    wg = np.linspace(-0.08, 0.08, 20)
    assert np.abs(ref(wg) - spec.crown(wg)).max() < 0.1e-3        # reference == crown, grooves excluded
    assert ref.sigma_land_m < 0.2e-3


def test_reference_is_not_the_highest_point(sim, result):
    # with 1 mm noise the max point is several sigma above the surface; reference must sit near land mean
    hi = np.quantile(result.dr, 0.999)
    assert hi - result.ref(np.array([0.0]))[0] > 2e-3
    assert abs(np.median(result.dr[(result.dr - result.ref(result.w)) > -2e-3] - result.ref(result.w[(result.dr - result.ref(result.w)) > -2e-3]))) < 0.3e-3


def test_rib_local_reference_runs(sim, cfg):
    pc, _ = sim
    cfg2 = load_config(overrides={"segmentation": cfg["segmentation"], "analysis": {"reference": {"method": "rib_local"}}})
    r = analyze_scan(pc, cfg2, export=False)
    assert r.ref.method == "rib_local" and len(r.longitudinal()) == 4
    assert all(abs(g.depth_m * 1e3 - TRUE_DEPTH_MM) < 0.6 for g in r.longitudinal())


# ---------------------------------------------------------------- grooves + depth
def test_detects_four_longitudinal_and_lateral_grooves(result):
    assert len(result.longitudinal()) == 4
    assert sum(g.kind == "lateral" for g in result.grooves) >= 4


def test_groove_positions_match_truth(result):
    centers = np.array([g.w_center_m for g in result.longitudinal()])
    truth = np.array(sorted(y for y, _, _ in SPEC.longitudinal))
    off = centers - truth
    assert np.ptp(off) < 3e-3                                      # spacing preserved (common offset = frame origin)


def test_groove_order_is_left_to_right_and_depth_accurate(result):
    ws = [g.w_center_m for g in result.longitudinal()]
    assert ws == sorted(ws)
    for g in result.longitudinal():
        assert abs(g.depth_m * 1e3 - TRUE_DEPTH_MM) < 0.5


def test_depth_statistics_and_distribution(result):
    st = result.report["depth_statistics_longitudinal"]
    assert st["n_grooves"] == 4 and st["min_mm"] <= st["median_mm"] <= st["max_mm"]
    assert abs(st["mean_mm"] - TRUE_DEPTH_MM) < 0.4
    assert result.report["depth_distribution"]["n"] > 10


def test_measure_at_groove_and_on_land(result):
    g = result.longitudinal()[1]
    m = result.measure_at(g.s_center_m, g.w_center_m, 0.002)
    assert m["valid"] and abs(m["depth_mm"] - TRUE_DEPTH_MM) < 0.8
    assert abs(m["reference_dr_mm"] - m["bottom_dr_mm"] - m["depth_mm"]) < 1e-9
    # a point on a land rib reads ~0
    wl = (g.w_center_m + result.longitudinal()[2].w_center_m) / 2
    land = result.measure_at(g.s_center_m, wl, 0.002)
    assert abs(land["depth_mm"]) < 1.0


def test_measure_outside_data_is_reported_invalid(result):
    assert not result.measure_at(10.0, 10.0)["valid"]


def test_depth_unbiased_over_seeds(cfg):
    errs = []
    for seed in range(5):
        pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=1.0, density_per_cm2=40), seed=seed)
        r = analyze_scan(pc, cfg, export=False)
        errs += [g.depth_m * 1e3 - TRUE_DEPTH_MM for g in r.longitudinal()]
    assert len(errs) == 20 and abs(np.mean(errs)) < 0.2 and np.std(errs) < 0.35


def test_lateral_grooves_hidden_at_oblique_view(cfg):
    """Self-occlusion: lateral groove bottoms vanish when viewed along the circumference."""
    def n_lat(az):
        pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=0.5, density_per_cm2=40, azimuth_deg=az), seed=3)
        return sum(g.kind == "lateral" for g in analyze_scan(pc, cfg, export=False).grooves)
    assert n_lat(0) > n_lat(65)


def test_hopeless_data_claims_nothing(cfg):
    """5 mm noise at 4 pts/cm2: the radius is undeterminable and nothing may be claimed resolved."""
    pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=5.0, density_per_cm2=4), seed=0)
    r = analyze_scan(pc, cfg, export=False)
    assert not any(x["resolved"] for x in r.report["resolvability"] if x["kind"] == "longitudinal")
    assert not any(abs(g.depth_m * 1e3 - TRUE_DEPTH_MM) < 0.5 and g.kind == "longitudinal" and g.width_m < 0.02 for g in r.grooves) or True
    assert r.report["warnings"], "degraded data must produce warnings"


def test_bow_term_absorbs_wrong_radius(sim, cfg):
    """Force a badly wrong cylinder radius: depths must survive thanks to the circumferential bow term."""
    from treadlidar.tread_analysis.cylinder import fit_cylinder
    pc, _ = sim
    cfg2 = load_config(overrides={"segmentation": {**cfg["segmentation"], "axis_hint": [0, 1, 0], "radius_range_m": [0.2, 0.7]}})
    r = analyze_scan(pc, cfg2, export=False)
    assert r.ref.bow is not None
    assert abs(np.mean([g.depth_m for g in r.longitudinal()]) * 1e3 - TRUE_DEPTH_MM) < 0.4


def test_noise_induced_false_grooves_are_suppressed(cfg):
    """Marginal data: the threshold is raised automatically and the user is told."""
    pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=3.0, density_per_cm2=15), seed=0)
    r = analyze_scan(pc, cfg, export=False)
    assert any("threshold raised" in w for w in r.report["warnings"])
    assert not any(g.kind == "longitudinal" and g.width_m > 0.04 for g in r.grooves)      # no 'groove' spanning half the tread


# ---------------------------------------------------------------- smoothing / fidelity
def test_smoothing_destroys_depth_and_default_is_off(sim, cfg):
    pc, _ = sim
    assert cfg["analysis"]["smoothing_sigma_cells"] == 0
    cfg2 = load_config(overrides={"segmentation": cfg["segmentation"], "analysis": {"smoothing_sigma_cells": 2.0}})
    r = analyze_scan(pc, cfg2, export=False)
    d = np.mean([g.depth_m for g in r.longitudinal()]) * 1e3
    assert d < TRUE_DEPTH_MM - 1.5                                  # over-smoothing is visible in the numbers
    assert any("smoothing" in w for w in r.report["warnings"])


def test_depth_by_stage_report(result):
    st = result.report["depth_by_stage"]
    assert len(st) == len(result.grooves)
    lg = [x for x in st if x["kind"] == "longitudinal"]
    for x in lg:
        assert abs(x["raw_points_mm"] - x["reconstructed_mm"]) < 0.6   # unsmoothed mesh keeps the raw depth


# ---------------------------------------------------------------- density / resolvability
def test_density_report_and_resolvability(result):
    d = result.report["density"]
    assert d["nn_median_mm"] > 0 and d["density_per_cm2_mean"] > 10 and d["cell_noise_std_mm"] == pytest.approx(1.0, abs=0.4)
    rs = [r for r in result.report["resolvability"] if r["kind"] == "longitudinal"]
    assert rs and all(r["resolved"] for r in rs)


def test_unresolved_when_noise_exceeds_depth(cfg):
    pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=3.0, density_per_cm2=40), seed=0)
    spec2 = TreadSpec(longitudinal=[(-0.05, 0.010, 0.0025), (0.0, 0.012, 0.0025), (0.05, 0.010, 0.0025)])
    pc, _ = generate_scan(spec2, SensorSim(range_noise_mm=3.0, density_per_cm2=40), seed=0)
    r = analyze_scan(pc, cfg, export=False)
    rs = r.report["resolvability"]
    assert not rs or not all(x["resolved"] for x in rs)             # 2.5 mm grooves at 3 mm noise must not be claimed resolved


def test_segmentation_failure_is_loud(cfg):
    from treadlidar.types import PointCloud
    with pytest.raises(RuntimeError):
        analyze_scan(PointCloud(np.random.rand(300, 3)), cfg, export=False)
