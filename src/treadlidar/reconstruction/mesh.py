"""Surface reconstruction prioritising geometric fidelity.

Default ``heightfield``: triangulate the unwrapped (s, w) grid of per-cell median heights taken
from the raw points. No implicit-surface fitting, no hole filling beyond empty cells being left
as holes, smoothing OFF unless ``smoothing_sigma_cells`` > 0. Poisson/Ball-pivoting (Open3D) are
provided for comparison only; Poisson in particular regularises and will round groove edges.
"""
from __future__ import annotations

import numpy as np

from ..tread_analysis.cylinder import CylinderFit
from ..tread_analysis.heightmap import HeightMap


def depth_colors(depth_m: np.ndarray, vmax_mm: float = 10.0, cmap: str = "RdYlGn_r") -> np.ndarray:
    """Colour by depth below the reference: 0 mm (unworn tread) green -> deep groove red."""
    import matplotlib

    cm = matplotlib.colormaps[cmap]
    x = np.clip(np.nan_to_num(depth_m, nan=0.0) * 1e3 / vmax_mm, 0, 1)
    return cm(x)[..., :3]


def heightfield_mesh(hm: HeightMap, fit: CylinderFit, z: np.ndarray, D: np.ndarray, edge_jump_m: float = 0.03,
                     vmax_mm: float = 10.0, cmap: str = "RdYlGn_r"):
    """Return (vertices (V,3), faces (F,3), colors (V,3), depth_per_vertex (V,))."""
    valid = np.isfinite(z)
    vid = -np.ones(z.shape, np.int64)
    vid[valid] = np.arange(valid.sum())
    sc, wc = hm.cell_centers()
    S, W = np.meshgrid(sc, wc, indexing="ij")
    verts = fit.to_world(S[valid], W[valid], z[valid])
    a, b = vid[:-1, :-1], vid[1:, :-1]
    c, d = vid[1:, 1:], vid[:-1, 1:]
    ok = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    zz = np.where(valid, z, 0.0)
    zmax = np.maximum.reduce([zz[:-1, :-1], zz[1:, :-1], zz[1:, 1:], zz[:-1, 1:]])
    zmin = np.minimum.reduce([zz[:-1, :-1], zz[1:, :-1], zz[1:, 1:], zz[:-1, 1:]])
    ok &= (zmax - zmin) <= edge_jump_m
    a, b, c, d = a[ok], b[ok], c[ok], d[ok]
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])]).astype(np.int64)
    depth = D[valid]
    return verts, faces, depth_colors(depth, vmax_mm, cmap), depth


def open3d_mesh(xyz: np.ndarray, method: str = "poisson", normal_radius: float = 0.004, depth: int = 9,
                ball_radii=(0.002, 0.004, 0.008), outward_point=None):
    """Optional comparison reconstructions via Open3D (MIT). Raises ImportError if unavailable."""
    import open3d as o3d  # lazy

    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz))
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamRadius(normal_radius))
    if outward_point is not None:
        pcd.orient_normals_towards_camera_location(np.asarray(outward_point, float))
    if method == "poisson":
        mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    elif method == "bpa":
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector(list(ball_radii)))
    else:
        raise ValueError(method)
    return np.asarray(mesh.vertices), np.asarray(mesh.triangles)
