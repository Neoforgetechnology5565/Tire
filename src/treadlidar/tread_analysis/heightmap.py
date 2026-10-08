"""Raw-point height map on the unwrapped (s, w) tread plane. Cells hold per-cell statistics of the
UNMODIFIED points; no resampling is done unless smoothing is explicitly requested."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass
class HeightMap:
    cell: float
    s0: float
    w0: float
    count: np.ndarray        # (Ns, Nw)
    z: np.ndarray            # median dr per cell [m], NaN where empty
    z_std: np.ndarray        # per-cell std of dr (NaN if < 2 points)

    @property
    def shape(self):
        return self.z.shape

    def cell_centers(self):
        s = self.s0 + (np.arange(self.shape[0]) + 0.5) * self.cell
        w = self.w0 + (np.arange(self.shape[1]) + 0.5) * self.cell
        return s, w

    def index(self, s, w):
        return (np.floor((np.asarray(s) - self.s0) / self.cell).astype(int),
                np.floor((np.asarray(w) - self.w0) / self.cell).astype(int))


def build_heightmap(s, w, dr, cell: float, min_points: int = 1) -> HeightMap:
    s0, w0 = float(s.min()), float(w.min())
    i = np.floor((s - s0) / cell).astype(np.int64)
    j = np.floor((w - w0) / cell).astype(np.int64)
    shape = (int(i.max()) + 1, int(j.max()) + 1)
    flat = i * shape[1] + j
    order = np.argsort(flat, kind="stable")
    fs, ds = flat[order], dr[order]
    uniq, start, cnt = np.unique(fs, return_index=True, return_counts=True)
    z = np.full(shape[0] * shape[1], np.nan)
    sd = np.full_like(z, np.nan)
    c = np.zeros_like(z)
    for u, a, n in zip(uniq, start, cnt):
        c[u] = n
        if n >= min_points:
            seg = ds[a:a + n]
            z[u] = np.median(seg)
            if n > 1:
                sd[u] = seg.std(ddof=1)
    return HeightMap(cell, s0, w0, c.reshape(shape), z.reshape(shape), sd.reshape(shape))


def smooth_nan(z: np.ndarray, sigma: float) -> np.ndarray:
    """NaN-aware Gaussian smoothing (normalised convolution). sigma in cells; 0 -> unchanged."""
    if sigma <= 0:
        return z.copy()
    m = np.isfinite(z)
    num = ndimage.gaussian_filter(np.where(m, z, 0.0), sigma)
    den = ndimage.gaussian_filter(m.astype(float), sigma)
    out = np.where(den > 1e-6, num / np.maximum(den, 1e-6), np.nan)
    out[~m] = np.nan
    return out


def fill_empty(z: np.ndarray, sigma: float = 1.5):
    """Fill ONLY empty cells from neighbours (normalised convolution). Measured cells are untouched.
    Used for detection robustness; depth values are always taken from measured cells."""
    m = np.isfinite(z)
    if m.all() or not m.any():
        return z.copy(), np.zeros_like(m)
    num = ndimage.gaussian_filter(np.where(m, z, 0.0), sigma)
    den = ndimage.gaussian_filter(m.astype(float), sigma)
    est = np.where(den > 0.05, num / np.maximum(den, 1e-9), np.nan)
    out = np.where(m, z, est)
    return out, (~m) & np.isfinite(out)


def choose_cell_m(s: np.ndarray, w: np.ndarray, target_points_per_cell: float = 4.0,
                  lo_m: float = 0.0005, hi_m: float = 0.005, probe_m: float = 0.002) -> float:
    """Pick a cell size so cells hold ~target points on average over the occupied area."""
    i = np.floor((s - s.min()) / probe_m).astype(np.int64)
    j = np.floor((w - w.min()) / probe_m).astype(np.int64)
    occupied = len(np.unique(i * (j.max() + 1) + j))
    area = occupied * probe_m ** 2
    dens = len(s) / area                                   # points per m^2
    return float(np.clip(np.sqrt(target_points_per_cell / dens), lo_m, hi_m))
