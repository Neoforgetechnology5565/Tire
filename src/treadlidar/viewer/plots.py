"""Headless matplotlib figures (depth map, cross-sections, accuracy, repeatability, raw/filtered/mesh)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_depth_map(path, hm, D, grooves, vmax_mm=10.0, cmap="RdYlGn_r", title="Tread depth map"):
    fig, ax = plt.subplots(figsize=(9, 5))
    ext = [hm.w0 * 1e3, (hm.w0 + hm.shape[1] * hm.cell) * 1e3, (hm.s0 + hm.shape[0] * hm.cell) * 1e3, hm.s0 * 1e3]
    im = ax.imshow(D * 1e3, extent=ext, aspect="equal", cmap=cmap, vmin=0, vmax=vmax_mm, interpolation="nearest")
    for g in grooves:
        if len(g.centerline) > 1:
            ax.plot(g.centerline[:, 1] * 1e3, g.centerline[:, 0] * 1e3, "k--", lw=0.6)
        ax.annotate(f"{g.id}: {g.depth_m * 1e3:.1f} mm", (g.w_center_m * 1e3, g.s_center_m * 1e3), fontsize=7,
                    ha="center", color="k", bbox=dict(boxstyle="round,pad=0.1", fc="w", alpha=0.7))
    ax.set_xlabel("w along wheel axis [mm]")
    ax.set_ylabel("s along circumference [mm]")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="depth below reference [mm]")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_cross_section(path, s, w, dr, ref, s_center, half_window_m=0.002, z_filtered=None, hm=None, title=""):
    """Raw points (thin s-slice) vs reference vs mesh/height-map profile: lets you SEE any over-smoothing."""
    m = np.abs(s - s_center) <= half_window_m
    dr = dr - 0.0   # (kept in raw radial units; reference is evaluated at s_center)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(w[m] * 1e3, dr[m] * 1e3, ".", ms=2, color="0.5", label=f"raw points (slice {2 * half_window_m * 1e3:.0f} mm)")
    wg = np.linspace(w.min(), w.max(), 400)
    ax.plot(wg * 1e3, ref(wg, np.full_like(wg, s_center)) * 1e3, "g-", lw=1.2, label="reference surface")
    if z_filtered is not None and hm is not None:
        i = int(np.clip((s_center - hm.s0) // hm.cell, 0, hm.shape[0] - 1))
        wc = hm.w0 + (np.arange(hm.shape[1]) + 0.5) * hm.cell
        ax.plot(wc * 1e3, z_filtered[i] * 1e3, "r-", lw=1.0, label="height-map / mesh row")
    ax.set_xlabel("w [mm]")
    ax.set_ylabel("radial height [mm]")
    ax.set_title(title or "Cross-section")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_accuracy(path, ref_mm, meas_mm, metrics, targets=(0.5, 1.0)):
    ref, meas = np.asarray(ref_mm), np.asarray(meas_mm)
    err = meas - ref
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    lo, hi = min(ref.min(), meas.min()) - 0.5, max(ref.max(), meas.max()) + 0.5
    ax[0].plot([lo, hi], [lo, hi], "k-", lw=0.8)
    ax[0].plot(ref, meas, "o", ms=4)
    ax[0].set_xlabel("reference depth [mm]")
    ax[0].set_ylabel("LiDAR depth [mm]")
    ax[0].set_title("LiDAR vs reference")
    ax[0].grid(alpha=0.3)
    ax[1].plot(ref, err, "o", ms=4)
    for t, c in zip(targets, ("g", "orange")):
        ax[1].axhspan(-t, t, color=c, alpha=0.12, label=f"+-{t} mm")
    ax[1].axhline(metrics.get("bias_mm", 0), color="r", lw=1, label=f"bias {metrics.get('bias_mm', 0):+.2f}")
    ax[1].set_xlabel("reference depth [mm]")
    ax[1].set_ylabel("error (LiDAR - ref) [mm]")
    ax[1].set_title(f"RMSE {metrics.get('rmse_mm', float('nan')):.2f} mm, n={metrics.get('n')}")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_repeatability(path, values_mm, labels=None, reference_mm=None):
    v = np.atleast_2d(values_mm)
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(v.shape[1])
    for i in range(v.shape[0]):
        ax.plot(x, v[i], "o", ms=4, alpha=0.7)
    ax.errorbar(x, v.mean(0), yerr=v.std(0, ddof=1) if v.shape[0] > 1 else None, fmt="k_", capsize=4, lw=1.5, label="mean +- SD")
    if reference_mm is not None:
        ax.plot(x, reference_mm, "r_", ms=18, mew=2, label="reference")
    ax.set_xticks(x)
    ax.set_xticklabels(labels or [str(i + 1) for i in x])
    ax.set_xlabel("groove / location")
    ax.set_ylabel("depth [mm]")
    ax.set_title(f"Repeatability over {v.shape[0]} scans")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
