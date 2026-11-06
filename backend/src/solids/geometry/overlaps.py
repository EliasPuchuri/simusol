"""Volumetric overlap between two distinct solids of the same period (RF-58).

Runs in the isolated worker process. Same provisional policy as the pair metrics: a mesh with inverted
orientation is re-oriented on an in-memory copy and flagged; originals are never touched or repaired. A value
that cannot be computed is ``None`` with a reason, never zero; ``0.0`` is only a computed empty intersection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from solids.geometry.pair_metrics import _signed_volume, surface_distances
from solids.geometry.qc import _edge_counts
from solids.geometry.scene import common_origin, load_obj

OVERLAP_VERSION = "overlap-1"
TOLERANCE = 1e-6          # relative to the smaller volume: numerical noise of the boolean, never a way to hide an error
CONTACT_FRACTION = 1e-9   # common volume below this fraction of the smaller solid is not an overlap
CONTACT_M = 0.01          # solids without common volume but a vertex this close to the other surface are in contact
CONTACT_SAMPLE = 2000     # vertices tested per solid: bounded cost, evenly spaced


def _bounds_failed(error: str) -> dict[str, Any]:
    return {"version": OVERLAP_VERSION, "status": "failed", "error": error, "min": None, "max": None}


def compute_bounds(path: Path) -> dict[str, Any]:
    """Axis-aligned box of one solid in its own (UTM) coordinates, for the conservative pre-filter."""
    try:
        vertices, _ = load_obj(Path(path))
        return {"version": OVERLAP_VERSION, "status": "ok", "error": None,
                "min": [float(x) for x in vertices.min(axis=0)], "max": [float(x) for x in vertices.max(axis=0)]}
    except Exception as exc:
        return _bounds_failed(str(exc)[:200] or exc.__class__.__name__)


def _in_contact(meshes: dict[str, Any]) -> bool:
    for src, dst in (("a", "b"), ("b", "a")):
        vertices = meshes[src].vertices
        step = max(1, len(vertices) // CONTACT_SAMPLE)
        if surface_distances(meshes[dst], vertices[::step]).min() <= CONTACT_M:
            return True
    return False


def _failed(error: str) -> dict[str, Any]:
    return {"version": OVERLAP_VERSION, "status": "failed", "error": error, "relation": None, "common_m3": None,
            "common_pct_of_smaller": None, "volumes": {"a_m3": None, "b_m3": None}, "reason": "overlap_failed", "warnings": []}


failed_overlap_result = _failed


def compute_overlap(path_a: Path, path_b: Path) -> dict[str, Any]:
    import trimesh

    try:
        sides = {}
        for role, path in (("a", Path(path_a)), ("b", Path(path_b))):
            vertices, faces = load_obj(path)
            sides[role] = (vertices, faces)
    except Exception as exc:
        return _failed(str(exc)[:200] or exc.__class__.__name__)

    origin = np.asarray(common_origin([(v.min(axis=0), v.max(axis=0)) for v, _ in sides.values()]))
    warnings: list[str] = []
    meshes: dict[str, Any] = {}
    volumes: dict[str, float | None] = {"a_m3": None, "b_m3": None}
    reason: str | None = None
    for role, (vertices, faces) in sides.items():
        shifted = vertices - origin  # one shared translation in float64, before any boolean
        if not np.all(_edge_counts(faces) == 2):
            reason = reason or f"not_watertight:{role}"
            continue
        mesh = trimesh.Trimesh(vertices=shifted, faces=faces, process=False)
        if not mesh.is_winding_consistent:
            reason = reason or f"inconsistent_winding:{role}"
            continue
        signed = _signed_volume(shifted, faces)
        if signed == 0:
            reason = reason or f"zero_volume:{role}"
            continue
        if signed < 0:
            mesh.faces = mesh.faces[:, ::-1]
            warnings.append(f"inverted_orientation_normalized:{role}")
        meshes[role] = mesh
        volumes[f"{role}_m3"] = abs(signed)

    out: dict[str, Any] = {"version": OVERLAP_VERSION, "status": "ok", "error": None, "relation": "not_evaluable",
                           "common_m3": None, "common_pct_of_smaller": None, "volumes": volumes, "reason": reason,
                           "warnings": warnings}
    if reason:
        return out
    try:
        result = trimesh.boolean.intersection([meshes["a"], meshes["b"]], engine="manifold", check_volume=False)
        common = 0.0 if result is None or result.is_empty else float(abs(result.volume))
        smaller = min(volumes["a_m3"], volumes["b_m3"])
        if common > smaller * (1 + TOLERANCE):
            raise ValueError("intersection_exceeds_volume")
        common = min(common, smaller)  # only numerical noise above the smaller volume is absorbed
    except Exception as exc:
        out["reason"] = f"boolean_failed: {exc}"[:200]
        return out
    if common > smaller * CONTACT_FRACTION:
        relation = "overlap"
    else:
        try:
            relation = "contact" if _in_contact(meshes) else "disjoint"
        except Exception as exc:
            out["reason"] = f"contact_check_failed: {exc}"[:200]
            return out
    out.update(common_m3=common, common_pct_of_smaller=100 * common / smaller, relation=relation)
    return out
