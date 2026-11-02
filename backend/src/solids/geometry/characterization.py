"""Global characterization of one solid (Part 1): PCA, body type and orientation.

Reproducible: surface points are sampled with a fixed seed, weighted by face area.
Nothing is repaired or merged. Local per-segment orientations are used only to
decide the body type; they are never returned, only aggregated evidence.

Thresholds are the experimental values of the demo notebook (profile
``pilot-v1-provisional``); they still need calibration with the area.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

CHAR_VERSION = "char-1"
PROFILE = "pilot-v1-provisional"
_EPS = 1e-9


@dataclass(frozen=True)
class Params:
    n_points: int = 30_000
    seed: int = 42
    ratio_cb_vein_max: float = 0.40       # thickness / intermediate dispersion
    ratio_ca_vein_max: float = 0.22       # thickness / major dispersion (notebook "extra support")
    ratio_ca_local_max: float = 0.50      # added guard: slicing a compact body must not look like a vein
    local_tabular_fraction_min: float = 0.65
    local_curvature_min_deg: float = 12.0
    n_segments: int = 8
    min_points_segment: int = 150
    axis_dominance_min: float = 1.1       # lambda1 / lambda2 needed for an interpretable axis


# --- angle conversions -----------------------------------------------------------------------

def plane_normal_to_azimuth_dip(normal) -> dict[str, Any]:
    """Azimuth (dip direction, 0-360 clockwise from North) and dip (0-90) of a plane from its normal."""
    n = np.asarray(normal, dtype=float)
    length = np.linalg.norm(n)
    if length == 0:
        return {"azimuth": None, "dip": None, "note": "zero_normal"}
    n = n / length
    if abs(n[2]) < 1e-6:  # vertical plane: both signs of the normal describe the same plane
        if n[1] < 0 or (abs(n[1]) < _EPS and n[0] < 0):
            n = -n
    elif n[2] < 0:
        n = -n
    east, north, up = n
    horizontal = math.hypot(east, north)
    dip = float(np.clip(math.degrees(math.atan2(horizontal, abs(up))), 0.0, 90.0))
    if horizontal < _EPS:
        return {"azimuth": None, "dip": dip, "note": "horizontal_plane"}
    azimuth = float(math.degrees(math.atan2(-east, -north)) % 360.0)
    note = "vertical_plane_direction_ambiguous" if abs(up) < 1e-6 else None
    return {"azimuth": azimuth, "dip": dip, "note": note}


def axis_to_trend_plunge(vector) -> dict[str, float | None]:
    """Trend and plunge of an axis. An axis has no sign: the result is valid modulo 180 degrees."""
    v = np.asarray(vector, dtype=float)
    length = np.linalg.norm(v)
    if length == 0:
        return {"trend": None, "plunge": None}
    v = v / length
    if v[1] < 0 or (abs(v[1]) < 1e-12 and v[0] < 0):
        v = -v
    east, north, vertical = v
    trend = math.degrees(math.atan2(east, north)) % 360.0
    plunge = float(np.clip(math.degrees(math.atan2(abs(vertical), math.hypot(east, north))), 0.0, 90.0))
    return {"trend": float(trend), "plunge": plunge}


# --- PCA ---------------------------------------------------------------------------------------

def _pca(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    centre = points.mean(axis=0)
    values, vectors = np.linalg.eigh(np.cov(points - centre, rowvar=False))
    order = np.argsort(values)[::-1]
    return centre, np.maximum(values[order], 0.0), vectors[:, order]


def _ratio(num: float, den: float) -> float | None:
    return float(num / den) if den > _EPS else None


def _angle_between_lines(a: np.ndarray, b: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip(abs(np.dot(a, b)), 0.0, 1.0))))


def _local_evidence(points, centre, major_axis, p: Params) -> dict[str, Any]:
    """Slice along the major axis; only aggregated evidence leaves this function."""
    position = (points - centre) @ major_axis
    limits = np.quantile(position, np.linspace(0, 1, p.n_segments + 1))
    tabular, normals = [], []
    for i in range(p.n_segments):
        upper = position <= limits[i + 1] if i == p.n_segments - 1 else position < limits[i + 1]
        chunk = points[(position >= limits[i]) & upper]
        if len(chunk) < p.min_points_segment:
            continue
        _, values, vectors = _pca(chunk)
        dispersion = np.sqrt(values)
        ratio = _ratio(dispersion[2], dispersion[1])
        tabular.append(ratio is not None and ratio <= p.ratio_cb_vein_max)
        normals.append(vectors[:, 2])
    if not tabular:
        return {"local_tabular_fraction": None, "local_change_p50_deg": None, "local_change_p95_deg": None,
                "local_change_max_deg": None, "segments_used": 0}
    changes = [_angle_between_lines(a, b) for a, b in zip(normals, normals[1:])] or [0.0]
    return {
        "local_tabular_fraction": float(np.mean(tabular)),
        "local_change_p50_deg": float(np.percentile(changes, 50)),
        "local_change_p95_deg": float(np.percentile(changes, 95)),
        "local_change_max_deg": float(np.max(changes)),
        "segments_used": len(tabular),
    }


def failed_result(error: str, params: Params = Params()) -> dict[str, Any]:
    return {
        "char_version": CHAR_VERSION, "profile": PROFILE, "status": "failed", "error": error,
        "params": asdict(params), "n_points": None, "eigenvalues": None, "dispersion": None, "axes": None,
        "body_type": None, "evidence": None,
        "orientation": {"type": "no_interpretable", "azimuth": None, "dip": None, "note": None, "reason": "analysis_failed"},
    }


def characterize_mesh(path: Path, params: Params = Params()) -> dict[str, Any]:
    import trimesh

    from solids.geometry.scene import load_obj

    try:
        vertices, faces = load_obj(Path(path))
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        points, _ = trimesh.sample.sample_surface(mesh, params.n_points, seed=params.seed)
    except Exception as exc:
        return failed_result(str(exc)[:200] or exc.__class__.__name__, params)

    centre, values, vectors = _pca(points)
    a, b, c = (float(x) for x in np.sqrt(values))
    if a <= _EPS:
        return failed_result("degenerate_geometry: the surface has no spatial extent", params)

    ratio_cb, ratio_ca, ratio_ba = _ratio(c, b), _ratio(c, a), _ratio(b, a)
    evidence = {"ratio_c_b": ratio_cb, "ratio_c_a": ratio_ca, "ratio_b_a": ratio_ba,
                **_local_evidence(points, centre, vectors[:, 0], params)}

    vein_global = (ratio_cb is not None and ratio_cb <= params.ratio_cb_vein_max) or (
        ratio_ca is not None and ratio_ca <= params.ratio_ca_vein_max)
    fraction = evidence["local_tabular_fraction"]
    vein_local = (fraction is not None and fraction >= params.local_tabular_fraction_min
                  and ratio_ca is not None and ratio_ca <= params.ratio_ca_local_max)
    p95 = evidence["local_change_p95_deg"]

    if not (vein_global or vein_local):
        body_type = "GLOBULAR"
    elif p95 is not None and p95 >= params.local_curvature_min_deg:
        body_type = "TABULAR CURVO"
    else:
        body_type = "TABULAR"

    if body_type == "GLOBULAR":
        if values[1] > 0 and values[0] / values[1] >= params.axis_dominance_min:
            tp = axis_to_trend_plunge(vectors[:, 0])
            orientation = {"type": "axial", "azimuth": tp["trend"], "dip": tp["plunge"], "note": None, "reason": None}
        else:
            orientation = {"type": "no_interpretable", "azimuth": None, "dip": None, "note": None,
                           "reason": "similar_eigenvalues"}
    else:
        ad = plane_normal_to_azimuth_dip(vectors[:, 2])
        if ad["azimuth"] is None:
            orientation = {"type": "no_interpretable", "azimuth": None, "dip": ad["dip"], "note": ad["note"],
                           "reason": ad["note"]}
        else:
            orientation = {"type": "planar", "azimuth": ad["azimuth"], "dip": ad["dip"], "note": ad["note"], "reason": None}

    return {
        "char_version": CHAR_VERSION, "profile": PROFILE, "status": "ok", "error": None, "params": asdict(params),
        "n_points": int(len(points)), "eigenvalues": [float(x) for x in values],
        "dispersion": {"a": a, "b": b, "c": c}, "axes": [[float(x) for x in vectors[:, i]] for i in range(3)],
        "body_type": body_type, "evidence": evidence, "orientation": orientation,
    }
