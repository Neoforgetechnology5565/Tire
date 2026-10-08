import numpy as np
import pytest

from treadlidar.data_acquisition.loaders import load_points, read_pcd, read_ply, save_scan_npz
from treadlidar.data_acquisition.metadata import describe_scan
from treadlidar.export import writers
from treadlidar.types import PointCloud

RNG = np.random.default_rng(0)
P = RNG.normal(size=(500, 3))


def test_npy_xyz_csv_roundtrip(tmp_path):
    np.save(tmp_path / "a.npy", P)
    np.savetxt(tmp_path / "a.xyz", P)
    np.savetxt(tmp_path / "a.csv", P, delimiter=",")
    for n in ("a.npy", "a.xyz", "a.csv"):
        assert np.allclose(load_points(tmp_path / n).xyz, P)


def test_scale_and_nan_removal(tmp_path):
    Q = P.copy() * 1000
    Q[3] = np.nan
    np.save(tmp_path / "mm.npy", Q)
    pc = load_points(tmp_path / "mm.npy", scale=0.001)
    assert len(pc) == 499 and np.allclose(pc.xyz, np.delete(P, 3, 0), atol=1e-9)


def test_npz_keeps_time(tmp_path):
    pc = PointCloud(P, np.ones(500), np.linspace(0, 0.1, 500), stamp=12.5)
    save_scan_npz(tmp_path / "s.npz", pc)
    out = load_points(tmp_path / "s.npz")
    assert out.stamp == 12.5 and np.allclose(out.t, pc.t) and np.allclose(out.intensity, 1)


def test_ply_binary_roundtrip(tmp_path):
    writers.write_ply_points(tmp_path / "p.ply", P, normals=P, colors=np.full((500, 3), 0.5), meta={"k": "v"})
    out = read_ply(tmp_path / "p.ply")
    assert np.allclose(out.xyz, P, atol=1e-5)
    assert b"comment k: v" in (tmp_path / "p.ply").read_bytes()


def test_ply_ascii(tmp_path):
    with open(tmp_path / "a.ply", "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nend_header\n1 2 3\n4 5 6\n")
    assert np.allclose(load_points(tmp_path / "a.ply").xyz, [[1, 2, 3], [4, 5, 6]])


def test_pcd_ascii_and_binary(tmp_path):
    hdr = ("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n"
           "WIDTH 3\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 3\nDATA {}\n")
    pts = np.array([[1, 2, 3, 9], [4, 5, 6, 8], [7, 8, 9, 7]], np.float32)
    (tmp_path / "a.pcd").write_text(hdr.format("ascii") + "\n".join(" ".join(map(str, r)) for r in pts) + "\n")
    (tmp_path / "b.pcd").write_bytes(hdr.format("binary").encode() + pts.tobytes())
    for n in ("a.pcd", "b.pcd"):
        pc = read_pcd(tmp_path / n)
        assert np.allclose(pc.xyz, pts[:, :3]) and np.allclose(pc.intensity, pts[:, 3])


def test_unsupported_extension(tmp_path):
    (tmp_path / "x.foo").write_text("1 2 3")
    with pytest.raises(ValueError):
        load_points(tmp_path / "x.foo")


def test_metadata_fields():
    pc = PointCloud(P + [0, 2, 0], t=np.linspace(0, 0.05, 500), sensor_origin=[0, 0, 0])
    m = describe_scan("S", pc, n_frames=7)
    assert m.n_points == 500 and m.n_frames == 7 and abs(m.duration_s - 0.05) < 1e-9
    assert abs(m.scan_distance_m - 2.0) < 0.3 and abs(m.scan_azimuth_deg - 90) < 10
