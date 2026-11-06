"""The real overlap analysis, logging every call so a test can tell cached results from recomputed ones."""

import os
from pathlib import Path

from solids.geometry import overlaps


def overlap(a, b):
    with open(os.environ["OVERLAP_LOG"], "a") as log:
        log.write(f"{Path(a).name}|{Path(b).name}\n")
    return overlaps.compute_overlap(a, b)
