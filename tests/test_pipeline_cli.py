import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from treadlidar import cli
from treadlidar.pipeline import analyze_scan
from treadlidar.simulation.synthetic import SensorSim, generate_scan

from conftest import SPEC


def test_pipeline_is_deterministic(sim, cfg):
    a = analyze_scan(sim[0], cfg, export=False)
    b = analyze_scan(sim[0], cfg, export=False)
    assert [g.depth_m for g in a.longitudinal()] == [g.depth_m for g in b.longitudinal()]


def test_accumulating_frames_by_concatenation_improves_noise(cfg):
    """Stationary accumulation: more points per cell lowers depth scatter (random error averaging)."""
    def sd(density, n=4):
        out = []
        for s in range(n):
            pc, _ = generate_scan(SPEC, SensorSim(range_noise_mm=2.0, density_per_cm2=density), seed=100 + s)
            out.append(np.mean([g.depth_m for g in analyze_scan(pc, cfg, export=False).longitudinal()]) * 1e3)
        return np.std(out)
    assert sd(80) <= sd(15) + 0.05


def test_cli_end_to_end(tmp_path, capsys):
    scans = tmp_path / "scans"
    cli.main(["simulate", "--out", str(scans), "--n-scans", "3", "--noise-mm", "1.0"])
    assert (scans / "sim_reference.csv").exists()
    out = tmp_path / "out"
    cli.main(["analyze", str(scans / "sim_scan_01.npy"), "--out", str(out), "--tread-half-width-mm", "95"])
    rpt = json.loads(next(out.glob("*_report.json")).read_text())
    assert abs(rpt["mean_tread_depth_mm"] - 8.0) < 0.5
    cli.main(["measure", str(scans / "sim_scan_01.npy"), "--tread-half-width-mm", "95", "--at", "0,0"])
    # validation: simulated data is accepted as simulated...
    val = tmp_path / "val"
    cli.main(["validate", *map(str, sorted(scans.glob("sim_scan_0*.npy"))), "--reference", str(scans / "sim_reference.csv"),
              "--origin", "simulated", "--out", str(val), "--tread-half-width-mm", "95"])
    f = json.loads((val / "feasibility.json").read_text())
    assert f["result"] == "NOT_ASSESSED"
    assert (val / "accuracy.png").exists() and (val / "repeatability.png").exists() and (val / "validation_pairs.csv").exists()
    # ...and can NOT be relabelled as real
    with pytest.raises(SystemExit):
        cli.main(["validate", *map(str, sorted(scans.glob("sim_scan_0*.npy"))), "--reference", str(scans / "sim_reference.csv"),
                  "--origin", "real", "--out", str(tmp_path / "bad")])


def test_cli_info(tmp_path, capsys):
    np.save(tmp_path / "a.npy", np.random.rand(10, 3))
    cli.main(["info", str(tmp_path / "a.npy")])
    assert json.loads(capsys.readouterr().out)["n_points"] == 10


def test_sample_data_in_repo_analyses_without_sensor(cfg):
    root = Path(__file__).parents[1] / "examples" / "sim_data"
    files = sorted(root.glob("sim_scan_*.npy"))
    assert files, "examples/sim_data missing (run scripts/make_sample_data.sh)"
    from treadlidar.data_acquisition.loaders import load_points
    pc = load_points(files[0])
    pc.sensor_origin = np.array(json.loads(files[0].with_suffix("").with_suffix(".sensor.json").read_text())["sensor_origin"])
    assert len(analyze_scan(pc, cfg, export=False).longitudinal()) == 4
