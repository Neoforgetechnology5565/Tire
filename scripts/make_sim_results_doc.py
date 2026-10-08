#!/usr/bin/env python3
"""Regenerate docs/SIMULATION_RESULTS.md table from a sweep CSV (SIMULATION ONLY)."""
import csv, sys
src = sys.argv[1] if len(sys.argv) > 1 else "docs/results/sim_sweep.csv"
rows = list(csv.DictReader(open(src)))
def f(r, k): return f"{float(r[k]):+.2f}" if r.get(k) else "-"
L = ["| σ (mm) | pts/cm² | runs ok/failed | bias (mm) | SD (mm) | 95% limit of \\|error\\| (mm) | within ±0.5 | within ±1.0 |", "|---|---|---|---|---|---|---|---|"]
for r in rows:
    ok = f"{r['n_ok']}/{r['n_failed']}"
    if r.get("loa95_mm"):
        L.append(f"| {r['noise_mm']} | {float(r['density_per_cm2']):g} | {ok} | {f(r,'bias_mm')} | {float(r['std_mm']):.2f} | {float(r['loa95_mm']):.2f} | {float(r['within_0p5']):.0%} | {float(r['within_1p0']):.0%} |")
    else:
        L.append(f"| {r['noise_mm']} | {float(r['density_per_cm2']):g} | {ok} | - | - | - | - | - |")
print("\n".join(L))
