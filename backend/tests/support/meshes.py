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
