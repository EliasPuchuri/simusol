"""Turns the stored geometric result of a pair (plus Part 1 data) into the inputs of the rules."""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from .comparison_rules import Profile, classify_pair
from .orientation_compare import compare_orientation


def _axis_angle(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return math.degrees(math.acos(float(np.clip(abs(np.dot(a, b)), 0.0, 1.0))))


def orientation_input(prev: Mapping[str, Any] | None, curr: Mapping[str, Any] | None) -> dict[str, Any]:
    """Comparable orientation delta between the Part 1 results of both periods."""
    if not prev or not curr or prev.get("status") != "ok" or curr.get("status") != "ok":
        return {"comparable": False, "reason": "not_interpretable"}
    o1, o2 = prev["orientation"], curr["orientation"]
    result = compare_orientation(o1, o2)
    if result.get("comparable"):
        axis = 2 if o1["type"] == "planar" else 0  # plane: normal; axis: major direction
        result["angle_deg"] = _axis_angle(prev["axes"][axis], curr["axes"][axis])
    return result


def rules_input(pair: Mapping[str, Any]) -> dict[str, Any]:
    m = pair["metrics"]
    chars = pair.get("characterization") or {}
    prev, curr = chars.get("previous"), chars.get("current")
    curved = any((c or {}).get("body_type") == "TABULAR CURVO" for c in (prev, curr))
    components = pair.get("components") or {}
    return {
        **{k: m.get(k) for k in ("iou_pct", "no_coincidence_pct", "delta_volume_pct", "delta_volume_sym_pct",
                                  "added_pct", "removed_pct", "p95_m", "centroid_m")},
        "orientation": orientation_input(prev, curr),
        "local_change_deg": m.get("local_change_deg") if curved else None,  # only applies when a body is TABULAR CURVO
        "components_prev": components.get("previous"), "components_curr": components.get("current"),
    }


def classify_result(pair: Mapping[str, Any], profile: Profile = Profile()) -> dict[str, Any]:
    """Classification of a stored pair result; a failed pair stays unassigned with its cause."""
    if pair.get("status") != "ok":
        return {"state": None, "subtype": None, "events": [], "checks": [], "profile": profile.id,
                "incidents": [{"code": "pair_failed", "detail": pair.get("error")}],
                "description": f"No se pudo clasificar: el análisis del par falló ({pair.get('error')})."}
    return classify_pair(rules_input(pair), profile)
