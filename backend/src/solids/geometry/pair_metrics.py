"""Geometric metrics of one pair of solids (previous vs current period).

PROVISIONAL volumes (user decision for the prototype): meshes whose global orientation is
inverted are re-oriented on an in-memory copy; the originals are never touched. Both solids
of a pair share one translation applied in float64 before any boolean or distance, so UTM
magnitudes do not lose precision. A metric that cannot be computed is ``None`` with a reason,
never zero. Runs in the isolated worker process: native booleans may hang or crash.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from solids.geometry.characterization import _pca, characterize_mesh
from solids.geometry.qc import _edge_counts
from solids.geometry.scene import common_origin, load_obj

PAIR_VERSION = "pair-1"
N_POINTS = 30_000
SEED = 42
N_SEGMENTS = 8
MIN_POINTS_SEGMENT = 150
MIN_SEGMENTS_COMPARED = 4
TOLERANCE = 1e-6  # relative: numerical noise of the boolean, never a way to hide a real error


def _signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    shifted = vertices - vertices.mean(axis=0)
    v0, v1, v2 = shifted[faces[:, 0]], shifted[faces[:, 1]], shifted[faces[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _surface_centroid(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2.0
    return (tri.mean(axis=1) * area[:, None]).sum(axis=0) / area.sum()


def _angle_between_lines(a: np.ndarray, b: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip(abs(np.dot(a, b)), 0.0, 1.0))))


def _local_change(points_a: np.ndarray, points_b: np.ndarray) -> dict[str, Any]:
    """Compare local plane normals on the SAME spatial slices (limits from both solids together)."""
    union = np.vstack((points_a, points_b))
    centre = union.mean(axis=0)
    _, _, vectors = _pca(points_a)
    axis = vectors[:, 0]
    limits = np.quantile((union - centre) @ axis, np.linspace(0, 1, N_SEGMENTS + 1))
    angles = []
    for i in range(N_SEGMENTS):
        normals = []
        for pts in (points_a, points_b):
            pos = (pts - centre) @ axis
            upper = pos <= limits[i + 1] if i == N_SEGMENTS - 1 else pos < limits[i + 1]
            chunk = pts[(pos >= limits[i]) & upper]
            if len(chunk) < MIN_POINTS_SEGMENT:
                break
            normals.append(_pca(chunk)[2][:, 2])
        if len(normals) == 2:
            angles.append(_angle_between_lines(*normals))
    if len(angles) < MIN_SEGMENTS_COMPARED:
        return {"p95": None, "max": None, "compared": len(angles)}
    return {"p95": float(np.percentile(angles, 95)), "max": float(np.max(angles)), "compared": len(angles)}


def _failed(error: str) -> dict[str, Any]:
    return {"pair_version": PAIR_VERSION, "status": "failed", "error": error, "provisional": True, "warnings": [],
            "volumes": None, "metrics": None, "components": None, "characterization": None, "reasons": {}, "origin": None}


failed_result = _failed  # public name used by the worker for crashes and timeouts


def compute_pair_metrics(previous: Path, current: Path) -> dict[str, Any]:
    import trimesh

    try:
        sides = {}
        for role, path in (("previous", Path(previous)), ("current", Path(current))):
            vertices, faces = load_obj(path)
            sides[role] = {"vertices": vertices, "faces": faces, "path": path}
    except Exception as exc:
        return _failed(str(exc)[:200] or exc.__class__.__name__)

    origin = common_origin([(s["vertices"].min(axis=0), s["vertices"].max(axis=0)) for s in sides.values()])
    warnings: list[str] = []
    reasons: dict[str, str] = {}
    volumes: dict[str, float | None] = {"previous_m3": None, "current_m3": None, "intersection_m3": None,
                                        "union_m3": None, "added_m3": None, "removed_m3": None}
    meshes: dict[str, Any] = {}
    volume_block: str | None = None

    for role, side in sides.items():
        shifted = side["vertices"] - np.asarray(origin)  # one shared translation, float64
        faces = side["faces"]
        side["shifted"], side["surface_faces"] = shifted, faces
        counts = _edge_counts(faces)
        watertight = bool(np.all(counts == 2))
        if not watertight:
            volume_block = volume_block or f"not_watertight:{role}"
            continue
        mesh = trimesh.Trimesh(vertices=shifted, faces=faces, process=False)
        if not mesh.is_winding_consistent:
            volume_block = volume_block or f"inconsistent_winding:{role}"
            continue
        signed = _signed_volume(shifted, faces)
        if signed == 0:
            volume_block = volume_block or f"zero_volume:{role}"
            continue
        if signed < 0:  # provisional normalisation on a copy: the original file is not modified
            mesh.faces = mesh.faces[:, ::-1]
            warnings.append(f"inverted_orientation_normalized:{role}")
        meshes[role] = mesh
        volumes[f"{role}_m3"] = abs(signed)

    metrics: dict[str, float | None] = {k: None for k in (
        "iou_pct", "no_coincidence_pct", "delta_volume_pct", "delta_volume_sym_pct", "added_pct", "removed_pct",
        "p95_m", "centroid_m", "local_change_deg", "local_change_max_deg")}
    metrics["local_segments_compared"] = None

    v1, v2 = volumes["previous_m3"], volumes["current_m3"]
    if volume_block:
        for name in ("iou_pct", "no_coincidence_pct", "delta_volume_pct", "delta_volume_sym_pct", "added_pct", "removed_pct"):
            reasons[name] = volume_block
    else:
        try:
            result = trimesh.boolean.intersection([meshes["previous"], meshes["current"]], engine="manifold", check_volume=False)
            inter = 0.0 if result is None or result.is_empty else float(abs(result.volume))
            smaller = min(v1, v2)
            if inter > smaller * (1 + TOLERANCE):
                raise ValueError("intersection_exceeds_volume")
            inter = min(inter, smaller)  # only numerical noise above the smaller volume is absorbed
            union = v1 + v2 - inter
            volumes.update(intersection_m3=inter, union_m3=union, added_m3=v2 - inter, removed_m3=v1 - inter)
            metrics.update(
                iou_pct=100 * inter / union, no_coincidence_pct=100 * (v1 + v2 - 2 * inter) / (v1 + v2),
                delta_volume_pct=100 * (v2 - v1) / v1, delta_volume_sym_pct=100 * abs(v2 - v1) / max(v1, v2),
                added_pct=100 * (v2 - inter) / v2, removed_pct=100 * (v1 - inter) / v1)
        except Exception as exc:
            for name in ("iou_pct", "no_coincidence_pct", "delta_volume_pct", "delta_volume_sym_pct", "added_pct", "removed_pct"):
                reasons[name] = f"boolean_failed: {exc}"[:200]
            volumes.update(intersection_m3=None, union_m3=None, added_m3=None, removed_m3=None)

    # surface distance (exact point-to-triangle) and centroid: they do not need a valid volume
    components: dict[str, int | None] = {}
    samples: dict[str, np.ndarray] = {}
    surfaces = {}
    for role, side in sides.items():
        surface = trimesh.Trimesh(vertices=side["shifted"], faces=side["faces"], process=False)
        surfaces[role] = surface
        samples[role], _ = trimesh.sample.sample_surface(surface, N_POINTS, seed=SEED)
        try:
            components[role] = int(surface.body_count)
        except Exception:
            components[role] = None
    try:
        distances = np.concatenate([
            trimesh.proximity.closest_point(surfaces["current"], samples["previous"])[1],
            trimesh.proximity.closest_point(surfaces["previous"], samples["current"])[1]])
        metrics["p95_m"] = float(np.percentile(distances, 95))
    except Exception as exc:
        reasons["p95_m"] = f"distance_failed: {exc}"[:200]
    metrics["centroid_m"] = float(np.linalg.norm(
        _surface_centroid(sides["current"]["shifted"], sides["current"]["faces"])
        - _surface_centroid(sides["previous"]["shifted"], sides["previous"]["faces"])))
    try:
        local = _local_change(samples["previous"], samples["current"])
        metrics.update(local_change_deg=local["p95"], local_change_max_deg=local["max"], local_segments_compared=local["compared"])
        if local["p95"] is None:
            reasons["local_change_deg"] = "insufficient_matching_segments"
    except Exception as exc:
        reasons["local_change_deg"] = f"local_change_failed: {exc}"[:200]

    return {
        "pair_version": PAIR_VERSION, "status": "ok", "error": None, "provisional": True, "warnings": warnings,
        "volumes": volumes, "metrics": metrics, "components": components, "reasons": reasons,
        "characterization": {role: characterize_mesh(side["path"]) for role, side in sides.items()},
        "origin": {"east": origin[0], "north": origin[1], "elevation": origin[2]},
    }


# --- one solid that exists in a single period (NUEVO / ELIMINADO) -------------------------------

def _single_failed(error: str) -> dict[str, Any]:
    return {"pair_version": PAIR_VERSION, "kind": "single", "status": "failed", "error": error, "provisional": True,
            "volume_m3": None, "volume_reason": "single_failed", "warnings": [], "characterization": None}


failed_single_result = _single_failed


def compute_single(path: Path) -> dict[str, Any]:
    """Provisional volume (orientation normalised on a copy) and Part 1 of one solid, for the totals."""
    import trimesh

    try:
        vertices, faces = load_obj(Path(path))
    except Exception as exc:
        return _single_failed(str(exc)[:200] or exc.__class__.__name__)
    shifted = vertices - vertices.mean(axis=0)
    volume, reason, warnings = None, None, []
    if not np.all(_edge_counts(faces) == 2):
        reason = "not_watertight:solid"
    elif not trimesh.Trimesh(vertices=shifted, faces=faces, process=False).is_winding_consistent:
        reason = "inconsistent_winding:solid"
    else:
        signed = _signed_volume(shifted, faces)
        if signed == 0:
            reason = "zero_volume:solid"
        else:
            volume = abs(signed)
            if signed < 0:
                warnings.append("inverted_orientation_normalized:solid")
    return {"pair_version": PAIR_VERSION, "kind": "single", "status": "ok", "error": None, "provisional": True,
            "volume_m3": volume, "volume_reason": reason, "warnings": warnings,
            "characterization": characterize_mesh(Path(path))}
