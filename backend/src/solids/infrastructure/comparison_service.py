"""Background worker that compares every matched pair of two closed periods."""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from solids.domain.matching import match_inventories
from solids.geometry.characterization import CHAR_VERSION
from solids.infrastructure.catalog import Catalog
from solids.infrastructure.qc_runner import IsolatedAnalyzer


class ComparisonService:
    def __init__(self, catalog: Catalog, files_dir: Path, *, target: str, version: str, timeout: float,
                 failure: Callable[[str], dict], slot: threading.Lock) -> None:
        self._catalog, self._files_dir = catalog, files_dir
        self._target, self._version, self._timeout = target, version, timeout
        self._failure, self._slot = failure, slot
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def _pairs(self, previous_id: str, current_id: str):
        result = match_inventories(self._catalog.inventory(previous_id), self._catalog.inventory(current_id))
        out = []
        for pair in result.pairs:
            prev = self._catalog.files_by_key(previous_id, pair.key)[0]
            curr = self._catalog.files_by_key(current_id, pair.key)[0]
            out.append((pair.key, prev, curr))
        return out

    def submit(self, previous_id: str, current_id: str) -> tuple[dict, bool]:
        with self._lock:
            active = self._catalog.active_comparison_run(previous_id, current_id)
            if active:
                return active, False
            run = self._catalog.create_comparison_run(previous_id, current_id, total=len(self._pairs(previous_id, current_id)))
            self._queue.put(run["id"])
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="comparison-worker", daemon=True)
                self._thread.start()
            return run, True

    def _loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                with self._slot:
                    self._process(run_id)
            except Exception as exc:
                self._catalog.update_comparison_run(run_id, state="failed", error=str(exc)[:200], finished_at=self._now())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _process(self, run_id: str) -> None:
        run = self._catalog.get_comparison_run(run_id)
        pairs = self._pairs(run["previous_id"], run["current_id"])
        self._catalog.update_comparison_run(run_id, state="running", done=0)
        analyzer: IsolatedAnalyzer | None = None
        failed = 0
        try:
            for index, (_, prev, curr) in enumerate(pairs, start=1):
                cached = self._catalog.get_pair(prev["sha256"], curr["sha256"], self._version)
                if cached is None or cached.get("status") == "failed":  # failures are retried
                    analyzer = analyzer or IsolatedAnalyzer(self._target, self._timeout, self._failure)
                    result = analyzer.analyze(self._files_dir / prev["stored_name"], self._files_dir / curr["stored_name"])
                    self._catalog.put_pair(prev["sha256"], curr["sha256"], self._version, result)
                    failed += result.get("status") == "failed"
                    for role, entry in (("previous", prev), ("current", curr)):  # Part 1 comes along for free
                        char = (result.get("characterization") or {}).get(role)
                        if char and char.get("status") == "ok" and self._catalog.get_cached("characterization", entry["sha256"], CHAR_VERSION) is None:
                            self._catalog.put_cached("characterization", entry["sha256"], CHAR_VERSION, char)
                self._catalog.update_comparison_run(run_id, done=index)
        finally:
            if analyzer is not None:
                analyzer.close()
        self._catalog.update_comparison_run(run_id, state="completed_with_issues" if failed else "completed", finished_at=self._now())
