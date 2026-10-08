"""Command-line workflow (engineering interface).

treadlidar info      FILE                       inspect a scan
treadlidar simulate  --out DIR ...              synthetic scans with ground truth (TESTING ONLY)
treadlidar analyze   FILE [FILE...]  --out DIR  segment -> reconstruct -> groove/depth -> exports
treadlidar measure   FILE --at S_MM,W_MM ...    depth at user-selected locations
treadlidar validate  FILE... --reference CSV --origin real|simulated --out DIR
treadlidar sweep     --out DIR                  simulation sensitivity study (NOT a statement about the L2)
treadlidar view      FILE                       Open3D viewer (needs open3d + display)

Workflow mapping: load/preview = info + view; register = analyze (several FILEs + --register icp);
segment/reconstruct/analyze/calculate = analyze; measure area = measure/view; accuracy = validate;
export = analyze (PLY/STL/OBJ/JSON/CSV).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .config import load_config
from .data_acquisition.loaders import load_points, save_scan_npz
from .export import report as rep
from .pipeline import analyze_scan
from .registration.icp import register_scans
from .types import PointCloud


def _cfg(args):
    over = {}
    seg = {}
    if getattr(args, "axis_hint", None):
        seg["axis_hint"] = [float(x) for x in args.axis_hint.split(",")]
    if getattr(args, "tread_half_width_mm", None):
        seg["tread_half_width_m"] = args.tread_half_width_mm * 1e-3
    if seg:
        over["segmentation"] = seg
    if getattr(args, "smoothing", None) is not None:
        over["analysis"] = {"smoothing_sigma_cells": args.smoothing}
    return load_config(getattr(args, "config", None), over)


def _apply_sidecar(pc, files):
    o = _origin_from_sidecar(files[0])
    if o is not None:
        pc.sensor_origin = o
    return pc


def _load_many(files, scale, register):
    clouds = []
    for f in files:
        pc = load_points(f, scale=scale)
        if pc.sensor_origin is None or not np.any(pc.sensor_origin):
            pass
        clouds.append(pc)
    if len(clouds) == 1:
        return clouds[0], None
    if register == "icp":
        return register_scans(clouds)
    # stationary sensor: frames share a frame, accumulate by concatenation
    return PointCloud.concat(clouds), None


def _sensor_origin(args, pc):
    if getattr(args, "sensor_origin", None):
        pc.sensor_origin = np.array([float(x) for x in args.sensor_origin.split(",")])
    return pc


def cmd_info(args):
    pc = load_points(args.file, scale=args.scale)
    lo, hi = pc.xyz.min(0), pc.xyz.max(0)
    print(json.dumps({"n_points": len(pc), "bbox_min_m": lo.tolist(), "bbox_max_m": hi.tolist(),
                      "has_intensity": pc.intensity is not None, "has_point_time": pc.t is not None}, indent=2))


def cmd_simulate(args):
    from .simulation.synthetic import SensorSim, TreadSpec, generate_scan

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = TreadSpec(lateral_pitches_m=[0.034, 0.040, 0.046, 0.040, 0.036, 0.044]) if args.wheel_step_deg else TreadSpec()
    if args.depths_mm:
        d = [float(x) * 1e-3 for x in args.depths_mm.split(",")]
        spec.longitudinal = [(y, w, dd) for (y, w, _), dd in zip(spec.longitudinal, d)]
    arc = 0.18 if args.wheel_step_deg else 0.16
    for k in range(args.n_scans):
        angle = k * args.wheel_step_deg
        pc, truth = generate_scan(spec, SensorSim(args.distance, args.azimuth, 0.0, args.noise_mm, 0.0, args.density),
                                  arc_length_m=arc, seed=args.seed + k, wheel_angle_deg=angle)
        np.save(out / f"sim_scan_{k + 1:02d}.npy", pc.xyz.astype(np.float32))
        side = {"sensor_origin": pc.sensor_origin.tolist(), "simulated": True}
        if args.wheel_step_deg:
            side["wheel_angle_deg"] = angle
            side["circumference_m"] = 2 * np.pi * spec.radius_m
        (out / f"sim_scan_{k + 1:02d}.sensor.json").write_text(json.dumps(side))
    ref = out / "sim_reference.csv"
    ref.write_text("groove_index,ref_depth_mm\n" + "".join(f"{i + 1},{d * 1e3:.2f}\n" for i, (_, _, d) in
                                                           enumerate(truth["spec"].longitudinal)))
    print(f"wrote {args.n_scans} SIMULATED scans + {ref} (ground truth, NOT physical data) to {out}")


def _sidecar(path):
    side = Path(path).with_suffix("").with_suffix(".sensor.json")
    return json.loads(side.read_text()) if side.exists() else {}


def _origin_from_sidecar(path):
    d = _sidecar(path)
    return np.array(d["sensor_origin"]) if "sensor_origin" in d else None


def cmd_analyze(args):
    cfg = _cfg(args)
    pc, diag = _load_many(args.files, args.scale, args.register)
    o = _origin_from_sidecar(args.files[0])
    if o is not None:
        pc.sensor_origin = o
    pc = _sensor_origin(args, pc)
    res = analyze_scan(pc, cfg, args.tire_id, args.scan_id, args.out, n_frames=len(args.files))
    rp = res.report
    print(f"tire radius {rp['geometry']['fitted_radius_mm']:.1f} mm | grooves: {len(rp['grooves'])} | "
          f"mean tread depth {rp['mean_tread_depth_mm']:.2f} mm (min {rp['min_tread_depth_mm']:.2f}, "
          f"max {rp['max_tread_depth_mm']:.2f}) | land noise {rp['reference_surface']['sigma_land_mm']:.2f} mm")
    for g in rp["grooves"]:
        print(f"  groove {g['id']:2d} {g['kind']:12s} w={g['w_center_m'] * 1e3:7.1f} mm width={g['width_m'] * 1e3:5.1f} "
              f"depth={g['depth_m'] * 1e3:5.2f} mm")
    for r in rp["resolvability"]:
        if not r["resolved"]:
            print(f"  ! groove {r['groove_id']} NOT resolved: {r['points_across_width']:.1f} pts across width, "
                  f"depth/noise {r['depth_over_noise']:.1f}")
    for w in rp["warnings"]:
        print("  warning:", w)
    print(f"outputs in {args.out}")


def cmd_measure(args):
    cfg = _cfg(args)
    pc, _ = _load_many(args.files, args.scale, "none")
    pc = _sensor_origin(args, _apply_sidecar(pc, args.files))
    res = analyze_scan(pc, cfg, export=False)
    for loc in args.at:
        s, w = (float(x) * 1e-3 for x in loc.split(","))
        m = res.measure_at(s, w, args.radius_mm * 1e-3)
        if m.get("valid"):
            print(f"s={s * 1e3:.1f} w={w * 1e3:.1f} mm: Tread depth {m['depth_mm']:.2f} mm "
                  f"(reference surface {m['reference_dr_mm']:.2f} mm, groove bottom {m['bottom_dr_mm']:.2f} mm, "
                  f"{m['n_points']} points)")
        else:
            print(f"s={s * 1e3:.1f} w={w * 1e3:.1f} mm: no data ({m['reason']})")
    print("groove centres (s,w in mm) to aim at:",
          [(round(g.s_center_m * 1e3, 1), round(g.w_center_m * 1e3, 1)) for g in res.longitudinal()])


def cmd_validate(args):
    from .validation import workflow
    from .viewer import plots

    cfg = _cfg(args)
    if args.origin == "real" and any(_sidecar(f).get("simulated") for f in args.files):
        sys.exit("refusing --origin real: at least one input is marked simulated in its .sensor.json sidecar")
    ref = workflow.read_reference_csv(args.reference)
    results = []
    for k, f in enumerate(args.files):
        pc = load_points(f, scale=args.scale)
        o = _origin_from_sidecar(f)
        if o is not None:
            pc.sensor_origin = o
        pc = _sensor_origin(args, pc)
        results.append(analyze_scan(pc, cfg, args.tire_id, f"SCAN_{k + 1:03d}", args.out if args.export_each else None,
                                    export=args.export_each))
    val = workflow.validate(results, ref, cfg["validation"], args.origin)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rep.write_json(out / "validation_report.json", val)
    rep.write_csv(out / "validation_pairs.csv", val["pairs"])
    if val.get("accuracy_single_scan"):
        a = val["accuracy_single_scan"]
        plots.plot_accuracy(out / "accuracy.png", [p["ref_mm"] for p in val["pairs"]],
                            [p["lidar_mm"] for p in val["pairs"]], a, (cfg["validation"]["target_tight_mm"], cfg["validation"]["target_loose_mm"]))
        plots.plot_repeatability(out / "repeatability.png", np.array(val["depth_matrix_mm"]), reference_mm=val["reference_mm"])
        print(f"pairs={a['n']}  bias={a['bias_mm']:+.2f}  MAE={a['mae_mm']:.2f}  RMSE={a['rmse_mm']:.2f}  "
              f"SD={a['std_mm']:.2f}  max|err|={a['max_abs_error_mm']:.2f} mm")
        r = val["repeatability"]
        if "pooled_std_mm" in r:
            print(f"repeatability: pooled SD={r['pooled_std_mm']:.2f} mm, max range={r['max_range_mm']:.2f} mm over {r['n_scans']} scans")
    for e in val["excluded_scans"]:
        print("  excluded:", e)
    f = val["feasibility"]
    print(f"\nFEASIBILITY RESULT: {f['result']}\n{f['summary']}")
    rep.write_json(out / "feasibility.json", f)


def cmd_fulltire(args):
    from .fulltire.protocol import run_protocol
    from .fulltire.workflow import analyze_rotating_wheel, export_fulltire

    cfg = _cfg(args)
    clouds, sides = [], []
    for f in args.files:
        pc = load_points(f, scale=args.scale)
        side = _sidecar(f)
        if "sensor_origin" in side:
            pc.sensor_origin = np.array(side["sensor_origin"])
        clouds.append(_sensor_origin(args, pc))
        sides.append(side)
    if args.angles:
        angles = [float(x) for x in args.angles.split(",")]
    elif all("wheel_angle_deg" in sd for sd in sides):
        angles = [sd["wheel_angle_deg"] for sd in sides]
    else:
        angles = None
    circ = args.circumference_mm * 1e-3 if args.circumference_mm else next((sd["circumference_m"] for sd in sides if "circumference_m" in sd), None)
    fm, results, fit = analyze_rotating_wheel(clouds, cfg, angles, circ, args.tire_id,
                                              {"blind_step_deg": args.blind_step_deg} if angles is None else None)
    rpt = run_protocol(fm, {"n_positions": args.n_positions, "limit_mm": args.limit_mm, "uncertainty_mm": args.uncertainty_mm,
                              "expected_grooves": args.expected_grooves})
    paths = export_fulltire(fm, rpt, args.out, args.tire_id)
    sm = rpt["summary"]
    print(f"{len(clouds)} views | circumference {rpt['circumference_mm']:.0f} mm | coverage {rpt['coverage']['rows_covered_fraction']:.0%} "
          f"(uncovered arc {rpt['coverage']['uncovered_arc_mm']:.0f} mm)")
    if sm:
        print(f"measurements {sm['n_measurements']} (missing {sm['n_missing']}) | depth min {sm['min_mm']:.2f} "
              f"(groove {sm['min_at']['groove_index']} @ {sm['min_at']['angle_deg']:.0f} deg) mean {sm['mean_mm']:.2f} max {sm['max_mm']:.2f} mm")
        for g in sm["per_groove"]:
            print(f"  groove {g['groove_index']}: mean {g['mean_mm']:.2f} min {g['min_mm']:.2f} max {g['max_mm']:.2f} (range around tire {g['around_range_mm']:.2f}) mm")
        lc = sm["limit_check"]
        print(f"limit check ({lc['limit_mm']} mm): {lc['status']}  [{lc['note']}]")
    for w in rpt["warnings"][:6]:
        print("  warning:", w)
    print("outputs:", args.out)


def cmd_sweep(args):
    from .validation.sim_study import run_sweep

    rows = run_sweep(args.noise_mm, args.density, args.azimuth, args.seeds, verbose=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rep.write_csv(out / "sim_sweep.csv", rows)
    print("\nSIMULATION ONLY: parameters are assumptions, not L2 measurements.")
    print(f"wrote {out / 'sim_sweep.csv'}")


def cmd_view(args):
    from .viewer.o3d_viewer import show

    cfg = _cfg(args)
    pc, _ = _load_many(args.files, args.scale, "none")
    pc = _sensor_origin(args, _apply_sidecar(pc, args.files))
    show(analyze_scan(pc, cfg, export=False))


def main(argv=None):
    p = argparse.ArgumentParser(prog="treadlidar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, multi=True):
        sp.add_argument("files", nargs="+" if multi else 1, help="scan files (.npy/.npz/.xyz/.csv/.ply/.pcd)")
        sp.add_argument("--scale", type=float, default=1.0, help="multiply coordinates to get metres (mm files: 0.001)")
        sp.add_argument("--config", help="YAML config (merged over defaults)")
        sp.add_argument("--axis-hint", help="wheel axis direction 'x,y,z' (recommended when known)")
        sp.add_argument("--tread-half-width-mm", type=float, help="half of the tread width [mm] (default 120)")
        sp.add_argument("--sensor-origin", help="sensor position 'x,y,z' in the cloud frame")
        sp.add_argument("--smoothing", type=float, help="height-map smoothing sigma in cells (default 0 = off)")

    s = sub.add_parser("info"); s.add_argument("file"); s.add_argument("--scale", type=float, default=1.0); s.set_defaults(f=cmd_info)
    s = sub.add_parser("simulate"); s.add_argument("--out", required=True); s.add_argument("--n-scans", type=int, default=5)
    s.add_argument("--noise-mm", type=float, default=1.0); s.add_argument("--density", type=float, default=40.0)
    s.add_argument("--distance", type=float, default=0.6); s.add_argument("--azimuth", type=float, default=0.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--wheel-step-deg", type=float, default=0.0, help="simulate a rotating wheel: step between views (enables full-tire data)")
    s.add_argument("--depths-mm", help="per-groove true depths 'd1,d2,d3,d4' (e.g. an unevenly worn tire)")
    s.set_defaults(f=cmd_simulate)
    s = sub.add_parser("analyze"); common(s); s.add_argument("--out", required=True)
    s.add_argument("--tire-id", default="TIRE_001"); s.add_argument("--scan-id", default="SCAN_001")
    s.add_argument("--register", choices=["none", "icp"], default="none"); s.set_defaults(f=cmd_analyze)
    s = sub.add_parser("measure"); common(s); s.add_argument("--at", action="append", required=True, help="'s_mm,w_mm'")
    s.add_argument("--radius-mm", type=float, default=3.0); s.set_defaults(f=cmd_measure)
    s = sub.add_parser("validate"); common(s); s.add_argument("--reference", required=True)
    s.add_argument("--origin", choices=["real", "simulated", "unknown"], default="unknown")
    s.add_argument("--out", required=True); s.add_argument("--tire-id", default="TIRE_001")
    s.add_argument("--export-each", action="store_true"); s.set_defaults(f=cmd_validate)
    s = sub.add_parser("fulltire", help="stitch views of a rotating wheel into a 360 deg map + automated measurement protocol")
    common(s); s.add_argument("--out", required=True); s.add_argument("--tire-id", default="TIRE_001")
    s.add_argument("--angles", help="wheel angle of each view in degrees 'a0,a1,...' (or wheel_angle_deg in the .sensor.json sidecars)")
    s.add_argument("--blind-step-deg", type=float, help="if angles unknown: nominal step between views")
    s.add_argument("--circumference-mm", type=float, help="tape-measured circumference at the tread centre (strongly recommended)")
    s.add_argument("--n-positions", type=int, default=8); s.add_argument("--limit-mm", type=float, default=1.6)
    s.add_argument("--uncertainty-mm", type=float, help="VALIDATED measurement uncertainty (from `validate` on real data)")
    s.add_argument("--expected-grooves", type=int, help="number of longitudinal grooves on this tire; a PASS is withheld if the count differs/unknown")
    s.set_defaults(f=cmd_fulltire)
    s = sub.add_parser("sweep"); s.add_argument("--out", required=True)
    s.add_argument("--noise-mm", type=float, nargs="+", default=[0.5, 1, 2, 3])
    s.add_argument("--density", type=float, nargs="+", default=[20, 40, 80])
    s.add_argument("--azimuth", type=float, nargs="+", default=[0.0]); s.add_argument("--seeds", type=int, default=4)
    s.set_defaults(f=cmd_sweep)
    s = sub.add_parser("view"); common(s); s.set_defaults(f=cmd_view)
    args = p.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    sys.exit(main())
