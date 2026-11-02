"""Read-only folder scanning with block-wise SHA-256 hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

from solids.domain.inventory import InventoryEntry
from solids.domain.naming import normalize_key

DEFAULT_BLOCK_SIZE = 1024 * 1024


def _sha256(path: Path, block_size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def scan_obj_folder(folder: Path, *, block_size: int = DEFAULT_BLOCK_SIZE) -> list[InventoryEntry]:
    """List top-level ``.obj`` files of ``folder`` without modifying them."""
    entries = [
        InventoryEntry(
            filename=path.name,
            key=normalize_key(path.name),
            sha256=_sha256(path, block_size),
            size_bytes=path.stat().st_size,
        )
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".obj"
    ]
    return sorted(entries, key=lambda e: e.filename)
