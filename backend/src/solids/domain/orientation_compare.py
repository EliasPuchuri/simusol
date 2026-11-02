"""Difference between a computed orientation and a reference one (e.g. from Studio RM).

Planar orientations are compared as dip directions (period 360); axial ones are
equivalent every 180 degrees, so an axis reversed by the PCA sign is not a turn.
Orientations of different type or not interpretable are never compared.
"""

from __future__ import annotations

from typing import Any, Mapping


def _circular(a: float, b: float, period: float) -> float:
    d = abs(a - b) % period
    return min(d, period - d)


def compare_orientation(computed: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    kinds = (computed.get("type"), reference.get("type"))
    if "no_interpretable" in kinds:
        return {"comparable": False, "reason": "not_interpretable"}
    if kinds[0] != kinds[1]:
        return {"comparable": False, "reason": "different_orientation_type"}
    period = 180.0 if kinds[0] == "axial" else 360.0
    az_c, az_r = computed.get("azimuth"), reference.get("azimuth")
    dip_c, dip_r = computed.get("dip"), reference.get("dip")
    return {
        "comparable": True,
        "delta_azimuth_deg": None if az_c is None or az_r is None else _circular(az_c, az_r, period),
        "delta_dip_deg": None if dip_c is None or dip_r is None else abs(dip_c - dip_r),
    }
