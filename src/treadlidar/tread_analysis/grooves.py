"""Groove detection on the depth map D = r_ref(w) - z (positive = below the reference surface)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np
from scipy import ndimage

from .heightmap import HeightMap, fill_empty
from .reference import ReferenceSurface


@dataclass
class Groove:
    id: int
    kind: str                    # longitudinal | lateral | other
    w_center_m: float
    s_center_m: float
    width_m: float
    length_m: float
    depth_m: float               # median depth over the groove core
    depth_min_m: float
    depth_max_m: float
    n_cells: int
    n_core_cells: int
    n_points_core: int
    centerline: np.ndarray       # (K, 2) in (s, w)
    mask: np.ndarray = field(repr=False, default=None)

    def summary(self) -> dict:
        d = {k: getattr(self, k) for k in ("id", "kind", "w_center_m", "s_center_m", "width_m",
                                            "length_m", "depth_m", "depth_min_m", "depth_max_m",
                                            "n_cells", "n_core_cells", "n_points_core")}
        return {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in d.items()}


def depth_map(hm: HeightMap, ref: ReferenceSurface, z=None) -> np.ndarray:
    """Depth below the reference per cell [m]; NaN for empty cells."""
    sc, wc = hm.cell_centers()
    zz = hm.z if z is None else z
    return ref.on_grid(sc, wc) - zz


def detect_grooves(hm: HeightMap, ref: ReferenceSurface, cfg: dict, z=None):
    """Return (grooves, groove_mask, D)."""
    D = depth_map(hm, ref, z)                       # measured cells only (NaN where empty)
    thr = cfg["threshold_mm"] * 1e-3
    # detection-only helper: fill empty cells from neighbours, optionally blur slightly. The mask is
    # used to LOCATE grooves; reported depths always come from the unblurred measured cells in D.
    D_det, _ = fill_empty(D, cfg.get("fill_sigma_cells", 1.5))
    if cfg.get("detect_sigma_cells", 0.0) > 0:
        D_det = ndimage.gaussian_filter(np.nan_to_num(D_det, nan=0.0), cfg["detect_sigma_cells"])
    m = np.nan_to_num(D_det, nan=-1.0) > thr
    if cfg["open_iterations"] > 0:
        m = ndimage.binary_opening(m, iterations=cfg["open_iterations"])
    if cfg["close_iterations"] > 0:
        m = ndimage.binary_closing(m, iterations=cfg["close_iterations"])
    # Directional separation: longitudinal grooves run along s, lateral grooves along w. Where they
    # join, a plain connected-component labelling would merge them and corrupt width/centre.
    cell_mm = hm.cell * 1e3
    ls = max(3, int(round(cfg.get("long_min_length_mm", 20.0) / cell_mm)))
    lw = max(3, int(round(cfg.get("lat_min_length_mm", 12.0) / cell_mm)))
    long_core = ndimage.binary_opening(m, structure=np.ones((ls, 1), bool))
    # remove a margin around longitudinal grooves so their junctions do not seed lateral grooves
    rest = m & ~ndimage.binary_dilation(long_core, structure=np.ones((1, 3), bool), iterations=1)
    lat_core = ndimage.binary_opening(rest, structure=np.ones((1, lw), bool))
    other = m & ~long_core & ~lat_core
    sc, wc = hm.cell_centers()
    grooves: List[Groove] = []
    for kind, base in (("longitudinal", long_core), ("lateral", lat_core), ("other", other)):
        lab, n = ndimage.label(base, structure=np.ones((3, 3)))
        for k in range(1, n + 1):
            gm = lab == k
            ncell = int(gm.sum())
            if ncell < cfg["min_cells"]:
                continue
            g = _make_groove(len(grooves), kind, gm, D, hm, sc, wc, cfg)
            if g is not None:
                grooves.append(g)
    final = np.zeros_like(m)
    for g in grooves:
        final |= g.mask
    return grooves, final, D


def _make_groove(gid, kind, gm, D, hm, sc, wc, cfg):
    ncell = int(gm.sum())
    ii, jj = np.nonzero(gm)
    ext_s = (ii.max() - ii.min() + 1) * hm.cell
    ext_w = (jj.max() - jj.min() + 1) * hm.cell
    edt = ndimage.distance_transform_edt(np.pad(gm, 1))[1:-1, 1:-1]
    core = gm & (edt >= cfg["core_fraction"] * edt.max())
    dvals = D[core]
    dvals = dvals[np.isfinite(dvals)]          # measured cells only: filled cells never contribute
    if len(dvals) == 0:
        return None
    if kind == "longitudinal":
        rows = np.unique(ii)
        cl = np.array([[sc[r], wc[jj[ii == r]].mean()] for r in rows])
        length, width = ext_s, ncell * hm.cell / max(len(rows), 1)     # mean width = area / length
    elif kind == "lateral":
        cols = np.unique(jj)
        cl = np.array([[sc[ii[jj == c]].mean(), wc[c]] for c in cols])
        length, width = ext_w, ncell * hm.cell / max(len(cols), 1)
    else:
        cl = np.array([[sc[ii].mean(), wc[jj].mean()]])
        length, width = max(ext_s, ext_w), min(ext_s, ext_w)
    return Groove(gid, kind, float(wc[jj].mean()), float(sc[ii].mean()), float(width), float(length),
                  float(np.median(dvals)), float(dvals.min()), float(dvals.max()), ncell, int(core.sum()),
                  int(hm.count[core].sum()), cl, gm)
