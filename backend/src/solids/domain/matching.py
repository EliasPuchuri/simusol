"""One-to-one matching of two closed inventories by normalized key."""

from __future__ import annotations

from dataclasses import dataclass

from .inventory import Incident, Inventory, InventoryEntry


@dataclass(frozen=True)
class MatchedPair:
    key: str
    previous: InventoryEntry
    current: InventoryEntry


@dataclass(frozen=True)
class MatchResult:
    pairs: tuple[MatchedPair, ...]
    only_previous: tuple[InventoryEntry, ...]
    only_current: tuple[InventoryEntry, ...]
    incidents: tuple[Incident, ...]


def match_inventories(previous: Inventory, current: Inventory) -> MatchResult:
    """Match solids by key.

    Absences are only declared over closed inventories. A key that collides
    inside one period is reported as an incident and excluded from pairs and
    from new/removed: no file is chosen arbitrarily.
    """
    if not previous.closed or not current.closed:
        raise ValueError("both inventories must be closed before comparing")

    prev_groups, curr_groups = previous.by_key(), current.by_key()
    incidents = previous.duplicate_incidents("previous") + current.duplicate_incidents("current")
    ambiguous = {i.detail["key"] for i in incidents}

    keys_prev, keys_curr = set(prev_groups) - ambiguous, set(curr_groups) - ambiguous
    pairs = tuple(
        MatchedPair(k, prev_groups[k][0], curr_groups[k][0]) for k in sorted(keys_prev & keys_curr)
    )
    only_prev = tuple(prev_groups[k][0] for k in sorted(keys_prev - keys_curr))
    only_curr = tuple(curr_groups[k][0] for k in sorted(keys_curr - keys_prev))
    return MatchResult(pairs, only_prev, only_curr, incidents)
