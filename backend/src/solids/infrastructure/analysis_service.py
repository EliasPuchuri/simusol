"""Background worker that runs one kind of per-solid analysis over a whole dataset.

Heavy work is serialized across kinds by a shared slot, so memory stays predictable
on a shared host. Results are cached by content hash and algorithm version.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from solids.infrastructure.catalog import Catalog
from solids.infrastructure.qc_runner import IsolatedAnalyzer


class AnalysisService:
    def __init__(self, catalog: Catalog, files_dir: Path, *, kind: str, target: str, version: str,
                 timeout: float, failure: Callable[[str], dict], slot: threading.Lock) -> None:
        self._catalog, self._files_dir = catalog, files_dir
        self._kind, self._target, self._version = kind, target, version
        self._timeout, self._failure, self._slot = timeout, failure, slot
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def submit(self, dataset_id: str) -> tuple[dict, bool]:
        """Queue a run. Returns (run, created); an active run is reused, not duplicated."""
        with self._lock:
            active = self._catalog.active_run(self._kind, dataset_id)
            if active:
                return active, False
            run = self._catalog.create_run(self._kind, dataset_id, total=len(self._catalog.files(dataset_id)))
            self._queue.put(run["id"])
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name=f"{self._kind}-worker", daemon=True)
                self._thread.start()
            return run, True

    def _loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                with self._slot:
                    self._process(run_id)
            except Exception as exc:  # the worker must survive any single run
                self._catalog.update_run(self._kind, run_id, state="failed", error=str(exc)[:200], finished_at=self._now())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _process(self, run_id: str) -> None:
        run = self._catalog.get_run(self._kind, run_id)
        files = self._catalog.files(run["dataset_id"])
        self._catalog.update_run(self._kind, run_id, state="running", done=0)
        analyzer: IsolatedAnalyzer | None = None
        failed = 0
        try:
            for index, entry in enumerate(files, start=1):
                cached = self._catalog.get_cached(self._kind, entry["sha256"], self._version)
                if cached is None or cached.get("status") == "failed":  # failures are retried
                    analyzer = analyzer or IsolatedAnalyzer(self._target, self._timeout, self._failure)
                    result = analyzer.analyze(self._files_dir / entry["stored_name"])
                    self._catalog.put_cached(self._kind, entry["sha256"], self._version, result)
                    failed += result.get("status") == "failed"
                self._catalog.update_run(self._kind, run_id, done=index)
        finally:
            if analyzer is not None:
                analyzer.close()  # release the native libraries' memory between runs
        self._catalog.update_run(self._kind, run_id, state="completed_with_issues" if failed else "completed",
                                 finished_at=self._now())
