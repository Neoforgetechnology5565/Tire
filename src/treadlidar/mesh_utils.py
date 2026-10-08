"""Small geometry helpers shared by viewer/export (pure numpy)."""
from __future__ import annotations

import numpy as np


def groove_lines(res) -> dict:
    """Groove centrelines as 3D polylines on the reference surface (points + segment index pairs)."""
    pts, segs = [], []
    for g in res.grooves:
        cl = g.centerline
        if len(cl) < 2:
            continue
        w = cl[:, 1]
        P = res.fit.to_world(cl[:, 0], w, res.ref(w, cl[:, 0]) + 0.0005)
        base = sum(len(p) for p in pts)
        pts.append(P)
        segs += [[base + i, base + i + 1] for i in range(len(P) - 1)]
    return {"points": np.vstack(pts) if pts else np.zeros((0, 3)), "segments": np.array(segs, int).reshape(-1, 2)}
