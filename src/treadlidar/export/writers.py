"""PLY / STL / OBJ writers implemented directly in numpy (no third-party licence exposure)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


def _comments(meta: Optional[dict]) -> str:
    if not meta:
        return ""
    return "".join(f"comment {k}: {str(v).replace(chr(10), ' ')}\n" for k, v in meta.items())


def face_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(ln > 0, ln, 1.0)


def vertex_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])  # area-weighted
    acc = np.zeros_like(v)
    for k in range(3):
        np.add.at(acc, f[:, k], n)
    ln = np.linalg.norm(acc, axis=1, keepdims=True)
    return acc / np.where(ln > 0, ln, 1.0)


def _write_ply(path, v, f=None, normals=None, colors=None, scalars=None, meta=None):
    v = np.asarray(v, np.float32)
    cols = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
    data = [v[:, 0], v[:, 1], v[:, 2]]
    if normals is not None:
        n = np.asarray(normals, np.float32)
        cols += [("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4")]
        data += [n[:, 0], n[:, 1], n[:, 2]]
    if colors is not None:
        c = np.asarray(colors)
        c = (np.clip(c, 0, 1) * 255).astype(np.uint8) if c.dtype.kind == "f" else c.astype(np.uint8)
        cols += [("red", "u1"), ("green", "u1"), ("blue", "u1")]
        data += [c[:, 0], c[:, 1], c[:, 2]]
    for name, arr in (scalars or {}).items():
        cols.append((name, "<f4"))
        data.append(np.asarray(arr, np.float32))
    rec = np.empty(len(v), dtype=cols)
    for (name, _), d in zip(cols, data):
        rec[name] = d
    hdr = "ply\nformat binary_little_endian 1.0\n" + _comments(meta) + f"element vertex {len(v)}\n"
    tmap = {"<f4": "float", "u1": "uchar"}
    hdr += "".join(f"property {tmap[t]} {n}\n" for n, t in cols)
    if f is not None:
        hdr += f"element face {len(f)}\nproperty list uchar int vertex_indices\n"
    hdr += "end_header\n"
    with open(path, "wb") as fh:
        fh.write(hdr.encode("ascii"))
        fh.write(rec.tobytes())
        if f is not None:
            fr = np.empty(len(f), dtype=[("n", "u1"), ("i", "<i4", (3,))])
            fr["n"] = 3
            fr["i"] = np.asarray(f, np.int32)
            fh.write(fr.tobytes())


def write_ply_points(path, xyz, normals=None, colors=None, scalars=None, meta=None) -> Path:
    _write_ply(path, xyz, None, normals, colors, scalars, meta)
    return Path(path)


def write_ply_mesh(path, vertices, faces, normals=None, colors=None, scalars=None, meta=None) -> Path:
    if normals is None:
        normals = vertex_normals(np.asarray(vertices, float), np.asarray(faces))
    _write_ply(path, vertices, faces, normals, colors, scalars, meta)
    return Path(path)


def write_stl(path, vertices, faces, name: str = "tread") -> Path:
    v = np.asarray(vertices, np.float32)
    f = np.asarray(faces, np.int64)
    tri = v[f]
    dt = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec = np.zeros(len(f), dtype=dt)
    rec["n"] = face_normals(v.astype(np.float64), f)
    rec["v"] = tri
    with open(path, "wb") as fh:
        fh.write(name.encode("ascii", "replace")[:80].ljust(80, b" "))
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(rec.tobytes())
    return Path(path)


def write_obj(path, vertices, faces, normals=None, meta=None) -> Path:
    v = np.asarray(vertices, float)
    with open(path, "w") as fh:
        for k, val in (meta or {}).items():
            fh.write(f"# {k}: {val}\n")
        np.savetxt(fh, v, fmt="v %.6f %.6f %.6f")
        if normals is not None:
            np.savetxt(fh, np.asarray(normals, float), fmt="vn %.5f %.5f %.5f")
            idx = np.asarray(faces) + 1
            np.savetxt(fh, np.column_stack([idx[:, 0], idx[:, 0], idx[:, 1], idx[:, 1], idx[:, 2], idx[:, 2]]),
                       fmt="f %d//%d %d//%d %d//%d")
        else:
            np.savetxt(fh, np.asarray(faces) + 1, fmt="f %d %d %d")
    return Path(path)


def read_stl(path):
    """Minimal binary-STL reader (used in tests / round-trip checks)."""
    raw = Path(path).read_bytes()
    n = int(np.frombuffer(raw[80:84], "<u4")[0])
    dt = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec = np.frombuffer(raw[84:], dtype=dt, count=n)
    return rec["v"].reshape(-1, 3).astype(np.float64), np.arange(3 * n).reshape(-1, 3)
