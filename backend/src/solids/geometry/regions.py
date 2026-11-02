"""Common, added and removed zones between two periods of one solid, as visual derivatives (GLB).

PROVISIONAL, like the pair volumes: inverted meshes are re-oriented on an in-memory copy; originals are
never touched. Zones are computed with boolean operations in the shared float64 frame of the comparison
and exported in the same scene coordinates as the two period layers (x=East, y=Elevation, z=-North).
Runs in the isolated worker: native booleans may hang or crash. A zone that cannot be computed says why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from solids.geometry.qc import _edge_counts
from solids.geometry.scene import export_glb, load_obj

ROLES = ("common", "added", "removed")
EMPTY_FRACTION = 1e-6  # relative to the larger volume: below this a zone is considered empty


def failed_result(error: str) -> dict[str, Any]:
    return {"status": "failed", "error": error, "provisional": True, "warnings": [], "regions": None, "origin": None}


def _prepare(vertices: np.ndarray, faces: np.ndarray, origin: np.ndarray, role: str):
    import trimesh

    shifted = vertices - origin
    if not np.all(_edge_counts(faces) == 2):
        return None, f"not_watertight:{role}", False
    mesh = trimesh.Trimesh(vertices=shifted, faces=faces, process=False)
    if not mesh.is_winding_consistent:
        return None, f"inconsistent_winding:{role}", False
    centred = shifted - shifted.mean(axis=0)
    signed = float(np.einsum("ij,ij->i", centred[faces[:, 0]], np.cross(centred[faces[:, 1]], centred[faces[:, 2]])).sum() / 6.0)
    if signed == 0:
        return None, f"zero_volume:{role}", False
    flipped = signed < 0
    if flipped:
        mesh.faces = mesh.faces[:, ::-1]
    return mesh, None, flipped


def compute_regions(previous: Path, current: Path, out_dir: Path, base: Path) -> dict[str, Any]:
    """``base`` is ``<sha_prev>-<sha_curr>_<east_mm>_<north_mm>_<elevation_mm>``: it names the files and carries the origin."""
    import trimesh

    name = Path(base).name
    try:
        east, north, elevation = (int(x) / 1000 for x in name.rsplit("_", 3)[1:])
        origin = np.array([east, north, elevation])
        sides = {}
        for role, path in (("previous", Path(previous)), ("current", Path(current))):
            vertices, faces = load_obj(path)
            sides[role] = (vertices, faces)
    except Exception as exc:
        return failed_result(str(exc)[:200] or exc.__class__.__name__)

    warnings, meshes, block = [], {}, None
    for role, (vertices, faces) in sides.items():
        mesh, reason, flipped = _prepare(vertices, faces, origin, role)
        if mesh is None:
            block = block or reason
            continue
        meshes[role] = mesh
        if flipped:
            warnings.append(f"inverted_orientation_normalized:{role}")
    result: dict[str, Any] = {"status": "ok", "error": None, "provisional": True, "warnings": warnings,
                              "origin": {"east": east, "north": north, "elevation": elevation}, "regions": {}}
    if block:
        result["regions"] = {role: {"status": "unavailable", "reason": block} for role in ROLES}
        return result

    a, b = meshes["previous"], meshes["current"]
    smallest = EMPTY_FRACTION * max(abs(a.volume), abs(b.volume))
    operations = {
        "common": lambda: trimesh.boolean.intersection([a, b], engine="manifold", check_volume=False),
        "added": lambda: trimesh.boolean.difference([b, a], engine="manifold", check_volume=False),
        "removed": lambda: trimesh.boolean.difference([a, b], engine="manifold", check_volume=False),
    }
    out_dir = Path(out_dir)
    for role, operation in operations.items():
        try:
            mesh = operation()
            volume = 0.0 if mesh is None or mesh.is_empty else float(abs(mesh.volume))
            if volume <= smallest:
                result["regions"][role] = {"status": "empty", "volume_m3": 0.0}
                continue
            v = np.asarray(mesh.vertices, dtype=np.float64)
            scene = np.column_stack((v[:, 0], v[:, 2], -v[:, 1])).astype(np.float32)  # same axis contract as the layers
            export_glb(scene, np.asarray(mesh.faces, dtype=np.int64), out_dir / f"{name}_{role}.glb")
            result["regions"][role] = {"status": "ok", "volume_m3": volume, "triangles": int(len(mesh.faces))}
        except Exception as exc:
            result["regions"][role] = {"status": "unavailable", "reason": f"boolean_failed: {exc}"[:200]}
    return result
