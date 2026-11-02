"""Closed/open inventory of the solids of one period."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Incident:
    code: str
    message: str
    detail: dict[str, object] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class InventoryEntry:
    filename: str
    key: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Inventory:
    """Entries of one period. ``entries`` keeps every file, collisions included."""

    entries: tuple[InventoryEntry, ...]
    closed: bool

    @classmethod
    def from_entries(cls, entries: Iterable[InventoryEntry], *, closed: bool) -> Inventory:
        return cls(tuple(sorted(entries, key=lambda e: (e.key, e.filename))), closed)

    def by_key(self) -> dict[str, list[InventoryEntry]]:
        groups: dict[str, list[InventoryEntry]] = defaultdict(list)
        for entry in self.entries:
            groups[entry.key].append(entry)
        return dict(groups)

    def duplicate_incidents(self, period: str) -> tuple[Incident, ...]:
        """One incident per key shared by several files; no file is preferred."""
        return tuple(
            Incident(
                "duplicate_key",
                f"{len(group)} files share key '{key}' in the {period} period",
                {"key": key, "period": period, "filenames": [e.filename for e in group]},
            )
            for key, group in sorted(self.by_key().items())
            if len(group) > 1
        )
