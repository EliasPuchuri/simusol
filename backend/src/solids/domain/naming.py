"""Normalized key used to match the same solid across periods."""

from __future__ import annotations

_SUFFIX = "pt"


def normalize_key(filename: str) -> str:
    """Return the matching key of an OBJ file name.

    Lower-cases, trims, drops the ``.obj`` extension and removes a single
    *terminal* ``pt``. Occurrences of ``pt`` elsewhere in the name are kept.
    The original file name is never altered by this function.
    """
    stem = filename.strip().lower()
    if stem.endswith(".obj"):
        stem = stem[: -len(".obj")]
    if stem.endswith(_SUFFIX) and len(stem) > len(_SUFFIX):
        stem = stem[: -len(_SUFFIX)]
    return stem
