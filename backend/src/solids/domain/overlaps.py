"""Which pairs of solids of one period must be checked for volumetric overlap (RF-58).

Every unordered pair is considered exactly once. A cheap, conservative axis-aligned box test discards the
pairs that cannot share volume; whatever it keeps still needs the exact (boolean) check.
"""

from __future__ import annotations

from itertools import combinations

Box = tuple[tuple[float, float, float], tuple[float, float, float]]  # (minimum corner, maximum corner)


def _may_touch(a: Box, b: Box, tolerance: float) -> bool:
    """Boxes that merely touch, or that are within ``tolerance``, count: the test must never discard a real overlap."""
    return all(a[0][i] - tolerance <= b[1][i] and b[0][i] - tolerance <= a[1][i] for i in range(3))


def candidate_pairs(boxes: dict[str, Box], tolerance: float = 0.0) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (pairs to check, pairs discarded as spatially separated), both sorted by name."""
    candidates: list[tuple[str, str]] = []
    discarded: list[tuple[str, str]] = []
    for a, b in combinations(sorted(boxes), 2):
        (candidates if _may_touch(boxes[a], boxes[b], tolerance) else discarded).append((a, b))
    return candidates, discarded
