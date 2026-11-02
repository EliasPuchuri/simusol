"""Visual derivatives of the analytic meshes.

Analytic meshes stay in UTM (float64). For the viewer, one translation shared
by every layer of a comparison is applied *before* casting to float32, and the
axes are remapped to a Y-up scene:

    x = East - E0,  y = Elevation - Z0,  z = -(North - N0)
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

Origin = tuple[float, float, float]  # (East, North, Elevation)


def common_origin(bounds: Iterable[tuple[Sequence[float], Sequence[float]]]) -> Origin:
    """Center of the joint bounds (min, max) of every mesh of the comparison."""
    boxes = [(np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)) for lo, hi in bounds]
    if not boxes:
        raise ValueError("at least one bounding box is required")
    low = np.min([b[0] for b in boxes], axis=0)
    high = np.max([b[1] for b in boxes], axis=0)
    east, north, elevation = (low + high) / 2
    return float(east), float(north), float(elevation)


def to_scene_coordinates(vertices: np.ndarray, origin: Origin) -> np.ndarray:
    """UTM (E, N, Z) float64 -> scene (x, y, z) float32 using the shared origin."""
    rel = np.asarray(vertices, dtype=np.float64) - np.asarray(origin, dtype=np.float64)
    scene = np.column_stack((rel[:, 0], rel[:, 2], -rel[:, 1]))
    return scene.astype(np.float32)


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read vertices/faces exactly as stored: no vertex merging, no repair."""
    import trimesh

    mesh = trimesh.load(path, file_type="obj", force="mesh", process=False)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("the OBJ has no triangles")
    if not np.isfinite(vertices).all():
        raise ValueError("the OBJ has non-finite coordinates")
    return vertices, faces


def export_glb(scene_vertices: np.ndarray, faces: np.ndarray, target: Path) -> None:
    import trimesh

    mesh = trimesh.Trimesh(vertices=scene_vertices, faces=faces, process=False)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(mesh.export(file_type="glb"))
    tmp.replace(target)  # atomic publication
