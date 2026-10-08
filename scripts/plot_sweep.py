#!/usr/bin/env python3
"""Plot docs/results/sim_sweep.csv (SIMULATION ONLY)."""
import csv
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

src = sys.argv[1] if len(sys.argv) > 1 else "docs/results/sim_sweep.csv"
dst = sys.argv[2] if len(sys.argv) > 2 else "docs/results/sim_sweep.png"
rows = [r for r in csv.DictReader(open(src)) if r.get("loa95_mm")]
dens = sorted({float(r["density_per_cm2"]) for r in rows})
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
for d in dens:
    rr = sorted((r for r in rows if float(r["density_per_cm2"]) == d), key=lambda r: float(r["noise_mm"]))
    x = [float(r["noise_mm"]) for r in rr]
    ax[0].plot(x, [float(r["loa95_mm"]) for r in rr], "o-", label=f"{d:g} pts/cm²")
    ax[1].plot(x, [float(r["bias_mm"]) for r in rr], "o-", label=f"{d:g} pts/cm²")
ax[0].axhline(0.5, color="g", ls="--", lw=0.8); ax[0].axhline(1.0, color="orange", ls="--", lw=0.8)
ax[0].set_xlabel("assumed range noise σ [mm]"); ax[0].set_ylabel("95% limit of |depth error| [mm]")
ax[0].set_title("SIMULATION: depth error vs noise/density"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
ax[1].axhline(0, color="k", lw=0.6); ax[1].set_xlabel("assumed range noise σ [mm]"); ax[1].set_ylabel("bias [mm]")
ax[1].set_title("SIMULATION: bias (+ = over-reads depth)"); ax[1].grid(alpha=.3)
fig.text(0.5, 0.01, "Parameters are assumptions, not Unitree L2 measurements. Failed runs (no/odd groove count) are excluded.",
         ha="center", fontsize=8)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(dst, dpi=140)
print("wrote", dst)
