"""Analyzer used by tests to simulate files that hang or kill the process."""

import os
import time
from pathlib import Path

from solids.geometry.qc import analyze_mesh


def analyze(path):
    path = Path(path)
    head = path.read_text(errors="ignore")[:200]
    log = os.environ.get("QC_FAKE_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write(path.name + "\n")
    if "#hang" in head:
        time.sleep(120)
    if "#crash" in head:
        os._exit(1)
    return analyze_mesh(path)


def characterize(path):
    from solids.geometry.characterization import characterize_mesh

    path = Path(path)
    head = path.read_text(errors="ignore")[:200]
    log = os.environ.get("QC_FAKE_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write("char:" + path.name + "\n")
    if "#hang" in head:
        time.sleep(120)
    if "#crash" in head:
        os._exit(1)
    return characterize_mesh(path)


def compare(previous, current):
    from solids.geometry.pair_metrics import compute_pair_metrics

    head = Path(previous).read_text(errors="ignore")[:200]
    log = os.environ.get("QC_FAKE_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write("pair:" + Path(previous).name + "\n")
    if "#hang" in head:
        time.sleep(120)
    if "#crash" in head:
        os._exit(1)
    return compute_pair_metrics(previous, current)


def threads(path):
    return {"status": "ok", "threads": os.environ.get("OMP_NUM_THREADS")}


def single(path):
    from solids.geometry.pair_metrics import compute_single

    path = Path(path)
    head = path.read_text(errors="ignore")[:200]
    log = os.environ.get("QC_FAKE_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write("single:" + path.name + "\n")
    if "#hang" in head:
        time.sleep(120)
    if "#crash" in head:
        os._exit(1)
    return compute_single(path)


def regions(previous, current, out_dir, base):
    from solids.geometry.regions import compute_regions

    head = Path(previous).read_text(errors="ignore")[:200]
    log = os.environ.get("QC_FAKE_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write("regions:" + Path(previous).name + "\n")
    if "#crash" in head:
        os._exit(1)
    return compute_regions(previous, current, out_dir, base)
