"""Analyzer whose import is slow, like a worker loading heavy native libraries."""

import time

time.sleep(1.5)


def analyze(path):
    return {"status": "ok", "metrics": {}}
