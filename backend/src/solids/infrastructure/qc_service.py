"""Single background worker that runs quality control one dataset at a time."""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

from solids.geometry.qc import QC_VERSION
from solids.infrastructure.catalog import Catalog
from solids.infrastructure.qc_runner import DEFAULT_TARGET, DEFAULT_TIMEOUT, IsolatedAnalyzer


class QcService:
    def __init__(self, catalog: Catalog, files_dir: Path, target: str = DEFAULT_TARGET,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        self._catalog, self._files_dir = catalog, files_dir
        self._target, self._timeout = target, timeout
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def submit(self, dataset_id: str) -> tuple[dict, bool]:
        """Queue a run. Returns (run, created); an active run is reused, not duplicated."""
        with self._lock:
            active = self._catalog.active_qc_run(dataset_id)
            if active:
                return active, False
            run = self._catalog.create_qc_run(dataset_id, total=len(self._catalog.files(dataset_id)))
            self._queue.put(run["id"])
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="qc-worker", daemon=True)
                self._thread.start()
            return run, True

    # ------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                self._process(run_id)
            except Exception as exc:  # the worker must survive any single run
                self._catalog.update_qc_run(run_id, state="failed", error=str(exc)[:200], finished_at=self._now())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _process(self, run_id: str) -> None:
        run = self._catalog.get_qc_run(run_id)
        files = self._catalog.files(run["dataset_id"])
        self._catalog.update_qc_run(run_id, state="running", done=0)
        analyzer: IsolatedAnalyzer | None = None
        failed = 0
        try:
            for index, entry in enumerate(files, start=1):
                cached = self._catalog.get_qc_cached(entry["sha256"], QC_VERSION)
                if cached is None or cached.get("status") == "failed":  # failures are retried
                    analyzer = analyzer or IsolatedAnalyzer(self._target, self._timeout)
                    result = analyzer.analyze(self._files_dir / entry["stored_name"])
                    self._catalog.put_qc(entry["sha256"], QC_VERSION, result)
                    failed += result.get("status") == "failed"
                self._catalog.update_qc_run(run_id, done=index)
        finally:
            if analyzer is not None:
                analyzer.close()  # release the native libraries' memory between runs
        self._catalog.update_qc_run(
            run_id, state="completed_with_issues" if failed else "completed", finished_at=self._now()
        )
