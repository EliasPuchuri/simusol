"""Geometric quality control of one mesh (Part 0). Detects and reports; never repairs.

The OBJ is read as stored (no vertex merging, no face reordering). Each check
is either a value, "unavailable" or "failed" with a reason; a failed check is
never reported as zero. Reasons and problems are stable English codes that the
UI translates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from solids.domain.metrics import Metric

QC_VERSION = "qc-1"
DEGENERATE_AREA = 1e-12
DECIMALS = 6


def _edge_counts(faces: np.ndarray) -> np.ndarray:
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    key = edges[:, 0].astype(np.int64) * (int(faces.max()) + 1) + edges[:, 1]
    _, counts = np.unique(key, return_counts=True)
    return counts


def _signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    shifted = vertices - vertices.mean(axis=0)  # local origin: avoids cancellation at UTM magnitudes
    v0, v1, v2 = shifted[faces[:, 0]], shifted[faces[:, 1]], shifted[faces[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _self_intersections(path: Path) -> Metric:
    try:
        import pymeshlab
    except Exception:  # pragma: no cover - depends on the environment
        return Metric.unavailable("pymeshlab_missing")
    try:
        meshset = pymeshlab.MeshSet()
        meshset.load_new_mesh(str(path))
        meshset.compute_selection_by_self_intersections_per_face()
        return Metric.valid(float(meshset.current_mesh().selected_face_number()))
    except Exception as exc:
        return Metric.failed(f"self_intersection_test_failed: {exc}"[:200])


def failed_result(error: str) -> dict[str, Any]:
    none = Metric.unavailable("not_evaluated")
    return {
        "qc_version": QC_VERSION, "status": "failed", "error": error, "problems": [],
        "vertices": None, "faces": None, "watertight": None, "open_edges": None, "non_manifold_edges": None,
        "winding_consistent": None, "orientation": "unknown", "signed_volume_m3": None, "volume_m3": none,
        "duplicate_vertices": None, "duplicate_faces": None, "degenerate_faces": None,
        "components": none, "self_intersections": none,
        "fitness": {"pca": False, "volume": False, "boolean": False, "visualization": False},
    }


def analyze_mesh(path: Path) -> dict[str, Any]:
    import trimesh

    path = Path(path)
    try:
        mesh = trimesh.load(path, file_type="obj", force="mesh", process=False)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        if len(vertices) == 0 or len(faces) == 0:
            raise ValueError("the OBJ has no triangles")
        if not np.isfinite(vertices).all():
            raise ValueError("the OBJ has non-finite coordinates")
    except Exception as exc:
        return failed_result(str(exc)[:200] or exc.__class__.__name__)

    counts = _edge_counts(faces)
    open_edges, non_manifold = int(np.sum(counts == 1)), int(np.sum(counts > 2))
    watertight = open_edges == 0 and non_manifold == 0
    try:
        winding = bool(mesh.is_winding_consistent)
    except Exception:
        winding = False

    signed = _signed_volume(vertices, faces) if watertight else None
    if not watertight or not winding or signed is None:
        orientation = "unknown"
    else:
        orientation = "outward" if signed > 0 else "inverted"

    dup_vertices = int(len(vertices) - len(np.unique(np.round(vertices, DECIMALS), axis=0)))
    dup_faces = int(len(faces) - len(np.unique(np.sort(faces, axis=1), axis=0)))
    cross = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]])
    degenerate = int(np.sum(np.linalg.norm(cross, axis=1) / 2.0 <= DEGENERATE_AREA))
    try:
        components = Metric.valid(float(mesh.body_count))
    except Exception as exc:
        components = Metric.unavailable(f"components_unavailable: {exc}"[:200])
    self_int = _self_intersections(path)

    problems: list[str] = []
    if not watertight:
        problems.append("not_watertight")
    if not winding:
        problems.append("inconsistent_winding")
    if orientation == "inverted":
        problems.append("inverted_orientation")
    if open_edges:
        problems.append("open_edges")
    if non_manifold:
        problems.append("non_manifold_edges")
    if dup_vertices:
        problems.append("duplicate_vertices")
    if dup_faces:
        problems.append("duplicate_faces")
    if degenerate:
        problems.append("degenerate_faces")
    if components.value is not None and components.value > 1:
        problems.append("multiple_components")
    if self_int.value:
        problems.append("self_intersections")

    # A volume number is only offered when nothing in the surface contradicts it.
    if not watertight:
        volume = Metric.unavailable("not_watertight")
    elif not winding:
        volume = Metric.unavailable("inconsistent_winding")
    elif orientation == "inverted":
        volume = Metric.unavailable("inverted_orientation")
    elif self_int.value:
        volume = Metric.unavailable("self_intersections")
    else:
        volume = Metric.valid(signed)

    return {
        "qc_version": QC_VERSION, "status": "ok" if not problems else "with_issues", "error": None,
        "problems": problems, "vertices": int(len(vertices)), "faces": int(len(faces)),
        "watertight": watertight, "open_edges": open_edges, "non_manifold_edges": non_manifold,
        "winding_consistent": winding, "orientation": orientation, "signed_volume_m3": signed,
        "volume_m3": volume, "duplicate_vertices": dup_vertices, "duplicate_faces": dup_faces,
        "degenerate_faces": degenerate, "components": components, "self_intersections": self_int,
        "fitness": {
            "pca": len(vertices) >= 4,
            "volume": volume.value is not None,
            "boolean": volume.value is not None and self_int.value == 0,
            "visualization": True,
        },
    }


def to_jsonable(result: dict[str, Any]) -> dict[str, Any]:
    """Plain, strict-JSON form (Metric -> dict, numpy -> python)."""
    out: dict[str, Any] = {}
    for key, value in result.items():
        out[key] = value.to_dict() if isinstance(value, Metric) else value
    return out
