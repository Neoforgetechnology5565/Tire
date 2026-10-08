"""Figures for the full-tire map and protocol."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .stitch import FullTireMap  # noqa: E402


def plot_unrolled(path, fm: FullTireMap, report: dict = None, vmax_mm=10.0):
    fig, ax = plt.subplots(2, 1, figsize=(13, 7), gridspec_kw={"height_ratios": [1.3, 1]})
    ext = [0, 360, (fm.w0 + fm.D.shape[1] * fm.cell) * 1e3, fm.w0 * 1e3]
    im = ax[0].imshow(fm.D.T * 1e3, extent=ext, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=vmax_mm, interpolation="nearest")
    ax[0].set_xlabel("angle around the tire [deg] (tire-fixed)"); ax[0].set_ylabel("w [mm]")
    ax[0].set_title(f"Unrolled full-tire depth map (C = {fm.circumference_m * 1e3:.0f} mm; white = not covered)")
    fig.colorbar(im, ax=ax[0], label="depth below reference [mm]")
    if report and report.get("measurements"):
        ang = np.array([m["angle_deg"] for m in report["measurements"]])
        gi = np.array([m["groove_index"] for m in report["measurements"]])
        dep = np.array([m["depth_mm"] for m in report["measurements"]])
        for g in sorted(set(gi)):
            s = gi == g
            ax[1].plot(ang[s], dep[s], "o-", label=f"groove {g}")
        lim = report["protocol"]["limit_mm"]
        ax[1].axhline(lim, color="r", ls="--", lw=0.8, label=f"limit {lim} mm")
        ax[1].set_xlabel("angle [deg]"); ax[1].set_ylabel("depth [mm]"); ax[1].legend(fontsize=7, ncol=3); ax[1].grid(alpha=.3)
        ax[1].set_title("Protocol measurements around the circumference")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)
