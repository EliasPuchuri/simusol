"""Are two periods in a compatible spatial frame? (P02.2, RF-60)

Only what can be checked objectively: the declared reference and units, and whether the horizontal extents of the
two periods overlap at all. Nothing is converted or assumed: a missing declaration is reported as such.
"""

from __future__ import annotations

from typing import Any

Extent = tuple[tuple[float, float, float], tuple[float, float, float]]  # (minimum corner E,N,Z), (maximum corner)


def _norm(value: str | None) -> str | None:
    text = " ".join((value or "").lower().split())
    return text or None


def _extents_overlap(a: Extent, b: Extent) -> bool:
    return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in (0, 1))  # East and North; elevation may differ


def assess(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Each side: {spatial_reference, units, extent}. Returns status, issues and what was declared."""
    issues: list[str] = []
    for field, mismatch, undeclared in (("spatial_reference", "spatial_reference_mismatch", "spatial_reference_undeclared"),
                                        ("units", "units_mismatch", "units_undeclared")):
        a, b = _norm(previous.get(field)), _norm(current.get(field))
        if a and b and a != b:
            issues.append(mismatch)
        elif not (a and b):
            issues.append(undeclared)
    extent_checked = previous.get("extent") is not None and current.get("extent") is not None
    if extent_checked and not _extents_overlap(previous["extent"], current["extent"]):
        issues.append("extent_disjoint")

    if any(i.endswith("_mismatch") for i in issues):
        status = "mismatch"
    elif "extent_disjoint" in issues:
        status = "extent_disjoint"
    elif issues:
        status = "undeclared"
    else:
        status = "compatible"
    return {"status": status, "issues": issues, "extent_checked": extent_checked,
            "declared": {role: {"spatial_reference": side.get("spatial_reference"), "units": side.get("units")}
                         for role, side in (("previous", previous), ("current", current))}}
