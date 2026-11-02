"""Synthetic meshes with known geometry, serialised as OBJ bytes."""

import math

import numpy as np
import trimesh


def obj_bytes(mesh, extra: str = "") -> bytes:
    lines = [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in mesh.vertices] + [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in mesh.faces]
    return (extra + "\n".join(lines) + "\n").encode()


def dip_normal(azimuth, dip):
    a, d = math.radians(azimuth), math.radians(dip)
    return np.array([-math.sin(d) * math.sin(a), -math.sin(d) * math.cos(a), math.cos(d)])


def slab(azimuth=120.0, dip=30.0, extents=(120.0, 60.0, 3.0), invert=False):
    mesh = trimesh.creation.box(extents=extents)
    n = dip_normal(azimuth, dip)
    strike = np.cross([0, 0, 1], n)
    strike /= np.linalg.norm(strike)
    basis = np.column_stack((strike, np.cross(n, strike), n))
    mesh.vertices = mesh.vertices @ basis.T + np.array([367_800.0, 8_827_600.0, 3_300.0])
    if invert:
        mesh.faces = mesh.faces[:, ::-1]
    return mesh


def sphere(radius=40.0):
    return trimesh.creation.icosphere(subdivisions=3, radius=radius)


def cube(center=(0.0, 0.0, 0.0), size=10.0, invert=False):
    mesh = trimesh.creation.box(extents=(size, size, size))
    mesh.apply_translation(center)
    if invert:
        mesh.faces = mesh.faces[:, ::-1]
    return mesh


def bent_slab(bend_deg=40.0):
    """Two thin plates joined end to end, the second one bent by `bend_deg` around the Y axis."""
    left, right = slab(90, 20, extents=(60, 60, 3)), slab(90, 20, extents=(60, 60, 3))
    centre = np.array([367_800.0, 8_827_600.0, 3_300.0])
    right.apply_translation(-centre)
    right.apply_transform(trimesh.transformations.rotation_matrix(math.radians(bend_deg), [0, 1, 0]))
    right.apply_translation(centre + [55, 0, 0])
    return trimesh.util.concatenate([left, right])
