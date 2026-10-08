"""Interactive 3D viewer (Open3D, MIT). Lazy import: the rest of the package works without it.

UNTESTED in CI (needs a display + GL); exercised only through the pure-numpy geometry builders in
``build_geometry_arrays`` which ARE unit-tested. Keys in the window:
  1 raw tire points   2 filtered points   3 mesh   4 groove centrelines   5 measurements
  +/-  point size     P  pick-and-measure (shift+click picks a point; depth printed + drawn)
"""
from __future__ import annotations

import numpy as np

from ..mesh_utils import groove_lines
from ..reconstruction.mesh import depth_colors


def build_geometry_arrays(res, vmax_mm: float = 10.0) -> dict:
    """Numpy arrays for everything the viewer shows (testable without Open3D)."""
    d_pts = res.ref(res.w, res.s) - res.dr
    out = {
        "raw_points": res.raw_tire_xyz,
        "filtered_points": res.tire_xyz,
        "filtered_colors": depth_colors(d_pts, vmax_mm),
        "mesh_vertices": res.mesh[0], "mesh_faces": res.mesh[1], "mesh_colors": res.mesh[2],
        "sensor_position": res.sensor_origin,
        "axes_origin": res.fit.center,
        "grooves": groove_lines(res),
    }
    return out


def show(res, vmax_mm: float = 10.0, measure_radius_m: float = 0.003):
    import open3d as o3d  # type: ignore

    g = build_geometry_arrays(res, vmax_mm)
    geoms = {}
    raw = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(g["raw_points"]))
    raw.paint_uniform_color([0.6, 0.6, 0.6])
    filt = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(g["filtered_points"]))
    filt.colors = o3d.utility.Vector3dVector(g["filtered_colors"])
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(g["mesh_vertices"]),
                                     o3d.utility.Vector3iVector(g["mesh_faces"]))
    mesh.vertex_colors = o3d.utility.Vector3dVector(g["mesh_colors"])
    mesh.compute_vertex_normals()
    lines = o3d.geometry.LineSet()
    if len(g["grooves"]["points"]):
        lines.points = o3d.utility.Vector3dVector(g["grooves"]["points"])
        lines.lines = o3d.utility.Vector2iVector(g["grooves"]["segments"])
        lines.paint_uniform_color([0, 0, 0])
    sensor = o3d.geometry.TriangleMesh.create_sphere(0.02)
    sensor.translate(g["sensor_position"])
    sensor.paint_uniform_color([0, 0, 1])
    axes = o3d.geometry.TriangleMesh.create_coordinate_frame(0.1, origin=g["axes_origin"])
    geoms = {"1": raw, "2": filt, "3": mesh, "4": lines}
    state = {k: True for k in geoms}
    meas = {"geoms": []}

    vis = o3d.visualization.VisualizerWithKeyCallback()
    vis.create_window(f"{res.tire_id} {res.scan_id}", 1280, 800)
    for geo in list(geoms.values()) + [sensor, axes]:
        vis.add_geometry(geo)

    def toggler(k):
        def cb(v):
            if state[k]:
                v.remove_geometry(geoms[k], reset_bounding_box=False)
            else:
                v.add_geometry(geoms[k], reset_bounding_box=False)
            state[k] = not state[k]
            return False
        return cb

    for k in geoms:
        vis.register_key_callback(ord(k), toggler(k))

    def psize(delta):
        def cb(v):
            o = v.get_render_option()
            o.point_size = max(1.0, o.point_size + delta)
            return False
        return cb

    vis.register_key_callback(ord("="), psize(1.0))
    vis.register_key_callback(ord("-"), psize(-1.0))
    print("Pick a point with shift+left-click in a *separate* Open3D editing window: press P.")

    def pick(v):
        pv = o3d.visualization.VisualizerWithEditing()
        pv.create_window("Pick points (shift+click), then close", 1000, 700)
        pv.add_geometry(filt)
        pv.run()
        pv.destroy_window()
        pts = np.asarray(filt.points)[pv.get_picked_points()]
        for p in pts:
            s, w, _ = res.fit.to_local(p[None, :])
            m = res.measure_at(float(s[0]), float(w[0]), measure_radius_m)
            if m.get("valid"):
                print(f"Tread depth: {m['depth_mm']:.2f} mm | reference surface at {m['reference_dr_mm']:.2f} mm | "
                      f"groove bottom {m['depth_mm']:.2f} mm below reference")
        return False

    vis.register_key_callback(ord("P"), pick)
    vis.run()
    vis.destroy_window()
