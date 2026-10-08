"""Point-cloud loading: .npy/.npz/.xyz/.txt/.csv/.ply/.pcd, all without the physical sensor.

All loaders return :class:`treadlidar.types.PointCloud` in metres. Units are NOT guessed;
pass ``scale`` (e.g. 0.001 for millimetre files).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from ..types import PointCloud

_PLY_TYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "<i2", "int16": "<i2",
    "ushort": "<u2", "uint16": "<u2", "int": "<i4", "int32": "<i4", "uint": "<u4",
    "uint32": "<u4", "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


def _from_columns(arr: np.ndarray, **kw) -> PointCloud:
    arr = np.atleast_2d(arr)
    if arr.shape[1] < 3:
        raise ValueError("need at least 3 columns (x y z)")
    inten = arr[:, 3] if arr.shape[1] >= 4 else None
    t = arr[:, 4] if arr.shape[1] >= 5 else None
    return PointCloud(arr[:, :3], inten, t, **kw)


def read_ply(path) -> PointCloud:
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("not a PLY file")
        fmt, props, n_vert, in_vertex, header_lines = None, [], 0, False, []
        while True:
            line = f.readline().decode("ascii", "replace").strip()
            if line == "end_header":
                break
            if not line:
                raise ValueError("truncated PLY header")
            header_lines.append(line)
            tok = line.split()
            if tok[0] == "format":
                fmt = tok[1]
            elif tok[0] == "element":
                in_vertex = tok[1] == "vertex"
                if in_vertex:
                    n_vert = int(tok[2])
            elif tok[0] == "property" and in_vertex:
                if tok[1] == "list":
                    raise ValueError("list property inside vertex element unsupported")
                props.append((tok[2], _PLY_TYPES[tok[1]]))
        if fmt == "ascii":
            data = np.loadtxt(f, max_rows=n_vert, ndmin=2)
            cols = {n: data[:, i] for i, (n, _) in enumerate(props)}
        elif fmt in ("binary_little_endian", "binary_big_endian"):
            dt = np.dtype([(n, ("<" if fmt.endswith("little_endian") else ">") + t.lstrip("<>=")
                            if t[0] not in "<>" else t) for n, t in props])
            rec = np.frombuffer(f.read(dt.itemsize * n_vert), dtype=dt, count=n_vert)
            cols = {n: rec[n].astype(np.float64) for n, _ in props}
        else:
            raise ValueError(f"unsupported PLY format {fmt}")
    xyz = np.column_stack([cols["x"], cols["y"], cols["z"]])
    return PointCloud(xyz, cols.get("intensity"), cols.get("time", cols.get("t")))


def read_pcd(path) -> PointCloud:
    with open(path, "rb") as f:
        hdr = {}
        while True:
            line = f.readline().decode("ascii", "replace").strip()
            if not line:
                raise ValueError("truncated PCD header")
            if line.startswith("#"):
                continue
            key, *vals = line.split()
            hdr[key.upper()] = vals
            if key.upper() == "DATA":
                break
        fields, size, typ = hdr["FIELDS"], list(map(int, hdr["SIZE"])), hdr["TYPE"]
        count = list(map(int, hdr.get("COUNT", ["1"] * len(fields))))
        n = int(hdr["POINTS"][0])
        tmap = {"F": "f", "U": "u", "I": "i"}
        dtl = []
        for nme, s, t, c in zip(fields, size, typ, count):
            base = f"<{tmap[t]}{s}"
            dtl.append((nme, base) if c == 1 else (nme, base, (c,)))
        dt = np.dtype(dtl)
        mode = hdr["DATA"][0]
        if mode == "binary":
            rec = np.frombuffer(f.read(dt.itemsize * n), dtype=dt, count=n)
            cols = {k: rec[k].astype(np.float64) for k in fields if k in rec.dtype.names and rec[k].ndim == 1}
        elif mode == "ascii":
            data = np.loadtxt(f, ndmin=2)
            cols, i = {}, 0
            for nme, c in zip(fields, count):
                if c == 1:
                    cols[nme] = data[:, i]
                i += c
        else:
            raise ValueError(f"unsupported PCD DATA mode {mode}")
    xyz = np.column_stack([cols["x"], cols["y"], cols["z"]])
    return PointCloud(xyz, cols.get("intensity"), cols.get("time", cols.get("t")))


def load_points(path, scale: float = 1.0, **kw) -> PointCloud:
    """Load a point cloud by extension. ``scale`` converts file units to metres."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".npy":
        pc = _from_columns(np.load(p), **kw)
    elif ext == ".npz":
        z = np.load(p)
        pc = PointCloud(z["xyz"], z["intensity"] if "intensity" in z else None,
                        z["t"] if "t" in z else None,
                        float(z["stamp"]) if "stamp" in z else 0.0)
    elif ext in (".xyz", ".txt", ".csv"):
        pc = _from_columns(np.loadtxt(p, delimiter="," if ext == ".csv" else None, ndmin=2), **kw)
    elif ext == ".ply":
        pc = read_ply(p)
    elif ext == ".pcd":
        pc = read_pcd(p)
    else:
        raise ValueError(f"unsupported point cloud format: {ext}")
    if scale != 1.0:
        pc.xyz = pc.xyz * scale
    finite = np.isfinite(pc.xyz).all(axis=1)
    if not finite.all():
        pc = pc.select(finite)
    return pc


def save_scan_npz(path, pc: PointCloud) -> None:
    kw = {"xyz": pc.xyz, "stamp": pc.stamp}
    if pc.intensity is not None:
        kw["intensity"] = pc.intensity
    if pc.t is not None:
        kw["t"] = pc.t
    np.savez_compressed(path, **kw)


def load_scan_dir(directory, pattern: str = "*", scale: float = 1.0) -> list:
    """Load every supported file in a directory, sorted by name."""
    exts = {".npy", ".npz", ".xyz", ".txt", ".csv", ".ply", ".pcd"}
    files = sorted(p for p in Path(directory).glob(pattern) if p.suffix.lower() in exts)
    return [(p, load_points(p, scale=scale)) for p in files]
