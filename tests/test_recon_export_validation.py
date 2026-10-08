import json

import numpy as np
import pytest

from treadlidar.config import DEFAULTS, load_config
from treadlidar.export import report as rep
from treadlidar.export import writers
from treadlidar.data_acquisition.loaders import read_ply
from treadlidar.mesh_utils import groove_lines
from treadlidar.pipeline import analyze_scan, export_result
from treadlidar.reconstruction.mesh import depth_colors, heightfield_mesh
from treadlidar.validation import accuracy, feasibility, workflow
from treadlidar.viewer.o3d_viewer import build_geometry_arrays

from conftest import TRUE_DEPTH_MM


# ---------------------------------------------------------------- reconstruction
def test_mesh_is_valid_and_dense(result):
    v, f, col, depth = result.mesh
    assert len(v) > 1000 and len(f) > 1000
    assert f.min() >= 0 and f.max() < len(v)
    assert np.isfinite(v).all() and col.shape == (len(v), 3) and ((col >= 0) & (col <= 1)).all()


def test_mesh_preserves_groove_relief(result):
    """Mesh vertex radial heights must retain the groove depth (no smoothing)."""
    v, f, col, depth = result.mesh
    assert depth.max() * 1e3 > TRUE_DEPTH_MM - 1.5 and np.nanpercentile(depth, 5) < 0.5e-3 + 1e-3


def test_mesh_edge_jump_drops_huge_discontinuities(result):
    hm, fit = result.hm, result.fit
    z = result.z.copy()
    z[10, 10] = 1.0   # absurd spike
    v, f, *_ = heightfield_mesh(hm, fit, z, result.D, edge_jump_m=0.03)
    assert len(f) < len(result.mesh[1])


def test_depth_colors_ordering():
    c = depth_colors(np.array([0.0, 0.005, 0.010]))
    assert c[0, 1] > c[0, 0] and c[2, 0] > c[2, 1]       # green at 0 mm, red at >=10 mm


# ---------------------------------------------------------------- export
def test_writers_roundtrip(tmp_path, result):
    v, f, col, depth = result.mesh
    writers.write_ply_mesh(tmp_path / "m.ply", v, f, None, col, {"depth_mm": depth * 1e3}, {"tire_id": "X"})
    pc = read_ply(tmp_path / "m.ply")
    assert len(pc) == len(v) and np.allclose(pc.xyz, v, atol=1e-5)
    writers.write_stl(tmp_path / "m.stl", v, f)
    sv, sf = writers.read_stl(tmp_path / "m.stl")
    assert len(sf) == len(f) and np.allclose(sv[:3], v[f[0]], atol=1e-5)
    writers.write_obj(tmp_path / "m.obj", v, f, writers.vertex_normals(v, f), {"scan": "S"})
    txt = (tmp_path / "m.obj").read_text().splitlines()
    assert sum(l.startswith("v ") for l in txt) == len(v) and sum(l.startswith("f ") for l in txt) == len(f)
    assert txt[0].startswith("# scan")


def test_vertex_normals_are_unit():
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0.0]])
    n = writers.vertex_normals(v, np.array([[0, 1, 2]]))
    assert np.allclose(np.linalg.norm(n, axis=1), 1) and np.allclose(n[:, 2], 1)


def test_full_export_set_and_report_schema(tmp_path, result):
    paths = export_result(result, tmp_path)
    for k in ("points_ply", "mesh_ply", "mesh_stl", "mesh_obj", "report_json", "grooves_csv", "depth_map_png", "cross_section_png"):
        assert (tmp_path / paths[k].split("/")[-1]).exists() and (tmp_path / paths[k].split("/")[-1]).stat().st_size > 100
    rpt = json.loads((tmp_path / paths["report_json"].split("/")[-1]).read_text())
    for key in ("tire_id", "scan_id", "mean_tread_depth_mm", "min_tread_depth_mm", "max_tread_depth_mm", "grooves",
                "density", "resolvability", "depth_by_stage", "geometry", "warnings", "scan_metadata"):
        assert key in rpt
    assert abs(rpt["mean_tread_depth_mm"] - TRUE_DEPTH_MM) < 0.4
    sm = rpt["scan_metadata"]
    for key in ("sensor_position", "scan_distance_m", "scan_azimuth_deg", "timestamp", "n_points",
                "point_density_per_cm2", "duration_s", "n_frames"):
        assert key in sm


def test_report_json_handles_numpy_and_nan(tmp_path):
    p = rep.write_json(tmp_path / "a.json", {"a": np.float32(1.5), "b": np.nan, "c": np.arange(3), "d": np.bool_(True)})
    assert json.loads(p.read_text()) == {"a": 1.5, "b": None, "c": [0, 1, 2], "d": True}


def test_viewer_geometry_arrays_and_groove_lines(result):
    g = build_geometry_arrays(result)
    assert g["raw_points"].shape[1] == 3 and len(g["filtered_colors"]) == len(g["filtered_points"])
    gl = groove_lines(result)
    assert gl["points"].shape[1] == 3 and gl["segments"].max() < len(gl["points"])


# ---------------------------------------------------------------- accuracy / repeatability
def test_accuracy_metrics_known_values():
    ref = np.array([8.0, 8.0, 6.0, 6.0])
    meas = np.array([7.5, 8.5, 5.5, 6.5])
    m = accuracy.accuracy_metrics(ref, meas)
    assert m["bias_mm"] == pytest.approx(0.0) and m["mae_mm"] == pytest.approx(0.5)
    assert m["rmse_mm"] == pytest.approx(0.5) and m["max_abs_error_mm"] == pytest.approx(0.5)
    assert m["frac_within_0p5mm"] == 1.0 and m["std_mm"] == pytest.approx(np.std([-.5, .5, -.5, .5], ddof=1))
    assert m["bias_ci_mm"][0] < 0 < m["bias_ci_mm"][1]


def test_accuracy_sign_convention_matches_example():
    m = accuracy.accuracy_metrics([8.00], [7.62])
    assert m["errors_mm"][0] == pytest.approx(-0.38)


def test_repeatability_metrics_known_values():
    vals = np.array([[8.0, 6.0], [8.2, 6.0], [7.8, 6.4], [8.0, 5.6], [8.0, 6.0]])
    r = accuracy.repeatability_metrics(vals)
    assert r["n_scans"] == 5 and r["n_locations"] == 2
    p0 = r["per_location"][0]
    assert p0["mean_mm"] == pytest.approx(8.0) and p0["range_mm"] == pytest.approx(0.4)
    assert r["pooled_std_mm"] == pytest.approx(np.sqrt(np.mean([np.var(vals[:, 0], ddof=1), np.var(vals[:, 1], ddof=1)])))
    assert r["repeatability_limit_mm"] == pytest.approx(2.77 * r["pooled_std_mm"])
    assert "error" in accuracy.repeatability_metrics(vals[:1])


VCFG = DEFAULTS["validation"]


def _val(loa, bias=0.0, n=20):
    return {"n": n, "loa95_halfwidth_mm": loa, "bias_mm": bias}


def _rep(sd, n=5):
    return {"n_scans": n, "pooled_std_mm": sd}


def test_feasibility_never_claims_from_non_real_data():
    for origin in ("simulated", "unknown"):
        assert feasibility.assess(_val(0.1), _rep(0.05), None, VCFG, origin)["result"] == "NOT_ASSESSED"


def test_feasibility_needs_enough_data():
    assert feasibility.assess(_val(0.1, n=3), _rep(0.05), None, VCFG, "real")["result"] == "INCONCLUSIVE"
    assert feasibility.assess(_val(0.1), _rep(0.05, n=2), None, VCFG, "real")["result"] == "INCONCLUSIVE"
    assert feasibility.assess(None, None, None, VCFG, "real")["result"] == "INCONCLUSIVE"


def test_feasibility_verdicts_a_b_c():
    a = feasibility.assess(_val(0.8), _rep(0.3), [{"resolved": True}], VCFG, "real")
    assert a["result"] == "A" and a["achievable_loose"] and not a["achievable_tight"]
    t = feasibility.assess(_val(0.4), _rep(0.1), [{"resolved": True}], VCFG, "real")
    assert t["result"] == "A" and t["achievable_tight"]
    b = feasibility.assess(_val(1.6), _rep(0.6), [{"resolved": True}], VCFG, "real")
    assert b["result"] == "B"
    c = feasibility.assess(_val(3.5), _rep(1.5), [{"resolved": True}], VCFG, "real")
    assert c["result"] == "C"
    # repeatable-but-biased measurements are not 'A'
    assert feasibility.assess(_val(1.2, bias=-1.0), _rep(0.2), None, VCFG, "real")["result"] == "B"
    # unresolved grooves downgrade an otherwise good verdict
    r = feasibility.assess(_val(0.8), _rep(0.3), [{"resolved": False}] * 3 + [{"resolved": True}], VCFG, "real")
    assert r["result"] == "B"


def test_validation_workflow_on_simulated_scans(cfg):
    from treadlidar.simulation.synthetic import SensorSim, generate_scan, TreadSpec
    spec = TreadSpec()
    results = []
    for sd in range(3):
        pc, _ = generate_scan(spec, SensorSim(range_noise_mm=1.0, density_per_cm2=40), seed=10 + sd)
        results.append(analyze_scan(pc, cfg, "T", f"S{sd}", export=False))
    ref = {i + 1: d * 1e3 for i, (_, _, d) in enumerate(spec.longitudinal)}
    v = workflow.validate(results, ref, cfg["validation"], "simulated")
    assert v["n_scans_used"] == 3 and len(v["pairs"]) == 12
    assert v["accuracy_single_scan"]["rmse_mm"] < 0.5 and v["repeatability"]["pooled_std_mm"] < 0.4
    assert v["feasibility"]["result"] == "NOT_ASSESSED"


def test_validation_excludes_scans_with_wrong_groove_count(result, cfg):
    v = workflow.validate([result], {1: 8.0, 2: 8.0, 3: 8.0}, cfg["validation"], "real")
    assert v["n_scans_used"] == 0 and v["excluded_scans"] and v["feasibility"]["result"] == "INCONCLUSIVE"


def test_reference_csv_reader(tmp_path):
    (tmp_path / "r.csv").write_text("groove_index,ref_depth_mm\n1,7.5\n2,8.1\n")
    assert workflow.read_reference_csv(tmp_path / "r.csv") == {1: 7.5, 2: 8.1}
    (tmp_path / "e.csv").write_text("groove_index,ref_depth_mm\n")
    with pytest.raises(ValueError):
        workflow.read_reference_csv(tmp_path / "e.csv")


# ---------------------------------------------------------------- config
def test_yaml_config_keys_exist_in_defaults():
    import yaml
    from pathlib import Path
    y = yaml.safe_load((Path(__file__).parents[1] / "config" / "pipeline.yaml").read_text())

    def check(a, b, path=""):
        for k, v in a.items():
            assert k in b, f"unknown config key {path}{k}"
            if isinstance(v, dict) and isinstance(b[k], dict):
                check(v, b[k], path + k + ".")
    check(y, DEFAULTS)


def test_load_config_override_merging():
    c = load_config(overrides={"analysis": {"reference": {"poly_degree": 3}}})
    assert c["analysis"]["reference"]["poly_degree"] == 3 and c["analysis"]["reference"]["w_bin_mm"] == 2.0
