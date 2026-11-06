"""Background worker that finds the volumetric overlaps between the solids of one period (RF-58).

Every pair is considered once. Boxes are cached per solid; pairs whose boxes cannot touch are discarded without
a boolean; the rest run in an isolated worker and are cached by content hash and algorithm version.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from solids.domain.overlaps import candidate_pairs
from solids.geometry.overlaps import CONTACT_M, OVERLAP_VERSION
from solids.infrastructure.catalog import Catalog
from solids.infrastructure.qc_runner import IsolatedAnalyzer

BOUNDS_VERSION = f"bounds-{OVERLAP_VERSION}"


class OverlapService:
    def __init__(self, catalog: Catalog, files_dir: Path, *, bounds_target: str, bounds_failure: Callable[[str], dict],
                 target: str, failure: Callable[[str], dict], timeout: float, slot: threading.Lock) -> None:
        self._catalog, self._files_dir = catalog, files_dir
        self._bounds_target, self._bounds_failure = bounds_target, bounds_failure
        self._target, self._failure, self._timeout, self._slot = target, failure, timeout, slot
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def submit(self, dataset_id: str) -> tuple[dict, bool]:
        with self._lock:
            active = self._catalog.active_run("overlap", dataset_id)
            if active:
                return active, False
            n = len(self._catalog.files(dataset_id))
            run = self._catalog.create_run("overlap", dataset_id, total=n * (n - 1) // 2)
            self._queue.put(run["id"])
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="overlap-worker", daemon=True)
                self._thread.start()
            return run, True

    def _loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                with self._slot:
                    self._process(run_id)
            except Exception as exc:
                self._catalog.update_run("overlap", run_id, state="failed", error=str(exc)[:200], finished_at=self._now())

    def _boxes(self, entries: list[dict]) -> tuple[dict, list[str]]:
        """Box of every solid (cached by content); the unreadable ones are reported, not skipped silently."""
        boxes, unreadable = {}, []
        analyzer: IsolatedAnalyzer | None = None
        try:
            for entry in entries:
                result = self._catalog.get_cached("single", entry["sha256"], BOUNDS_VERSION)
                if result is None or result.get("status") == "failed":
                    analyzer = analyzer or IsolatedAnalyzer(self._bounds_target, self._timeout, self._bounds_failure)
                    result = analyzer.analyze(self._files_dir / entry["stored_name"])
                    self._catalog.put_cached("single", entry["sha256"], BOUNDS_VERSION, result)
                if result.get("status") == "ok":
                    boxes[entry["filename"]] = (tuple(result["min"]), tuple(result["max"]))
                else:
                    unreadable.append(entry["filename"])
        finally:
            if analyzer is not None:
                analyzer.close()
        return boxes, unreadable

    def plan(self, dataset_id: str) -> dict | None:
        """Pairs to check and pairs discarded, from the cached boxes only. None until the boxes exist."""
        entries = self._catalog.files(dataset_id)
        boxes, unreadable = {}, []
        for entry in entries:
            result = self._catalog.get_cached("single", entry["sha256"], BOUNDS_VERSION)
            if result is None:
                return None
            if result.get("status") == "ok":
                boxes[entry["filename"]] = (tuple(result["min"]), tuple(result["max"]))
            else:
                unreadable.append(entry["filename"])
        candidates, discarded = candidate_pairs(boxes, tolerance=CONTACT_M)
        return {"entries": {e["filename"]: e for e in entries}, "candidates": candidates,
                "discarded": discarded, "unreadable": unreadable}

    def _process(self, run_id: str) -> None:
        run = self._catalog.get_run("overlap", run_id)
        dataset_id = run["dataset_id"]
        self._catalog.update_run("overlap", run_id, state="running", done=0)
        entries = self._catalog.files(dataset_id)
        boxes, unreadable = self._boxes(entries)
        candidates, discarded = candidate_pairs(boxes, tolerance=CONTACT_M)
        by_name = {e["filename"]: e for e in entries}
        total = len(entries) * (len(entries) - 1) // 2
        skipped = total - len(candidates)  # discarded by the boxes, or involving an unreadable solid
        self._catalog.update_run("overlap", run_id, done=skipped)
        analyzer: IsolatedAnalyzer | None = None
        failed = len(unreadable)
        try:
            for index, (a, b) in enumerate(candidates, start=1):
                ea, eb = by_name[a], by_name[b]
                cached = self._catalog.get_pair(ea["sha256"], eb["sha256"], OVERLAP_VERSION)
                if cached is None or cached.get("status") == "failed":
                    analyzer = analyzer or IsolatedAnalyzer(self._target, self._timeout, self._failure)
                    result = analyzer.analyze(self._files_dir / ea["stored_name"], self._files_dir / eb["stored_name"])
                    self._catalog.put_pair(ea["sha256"], eb["sha256"], OVERLAP_VERSION, result)
                    failed += result.get("status") == "failed"
                self._catalog.update_run("overlap", run_id, done=skipped + index)
        finally:
            if analyzer is not None:
                analyzer.close()
        self._catalog.update_run("overlap", run_id, state="completed_with_issues" if failed else "completed",
                                 done=total, finished_at=self._now())

    def report(self, dataset_id: str) -> dict:
        """Everything known about the overlaps of a period, read from the caches (nothing is recomputed)."""
        plan = self.plan(dataset_id)
        run = self._catalog.latest_run("overlap", dataset_id)
        summary = {"solids": len(self._catalog.files(dataset_id)), "pairs": 0, "discarded": 0, "overlapping": 0, "contact": 0,
                   "disjoint": 0, "not_evaluable": 0, "failed": 0, "pending": 0, "unreadable": []}
        if plan is None:
            return {"run": run, "evaluated": False, "summary": summary, "pairs": []}
        n = summary["solids"]
        summary.update(pairs=n * (n - 1) // 2, discarded=len(plan["discarded"]), unreadable=plan["unreadable"])
        pairs = []
        for a, b in plan["candidates"]:
            ea, eb = plan["entries"][a], plan["entries"][b]
            result = self._catalog.get_pair(ea["sha256"], eb["sha256"], OVERLAP_VERSION)
            if result is None:
                summary["pending"] += 1
                continue
            relation = result.get("relation") if result.get("status") == "ok" else None
            if result.get("status") == "failed":
                summary["failed"] += 1
            elif relation == "overlap":
                summary["overlapping"] += 1
            elif relation == "contact":
                summary["contact"] += 1
            elif relation == "disjoint":
                summary["disjoint"] += 1
            else:
                summary["not_evaluable"] += 1
            if relation in ("overlap", "contact", "not_evaluable", None):
                pairs.append({"a": a, "b": b, "key_a": ea["key"], "key_b": eb["key"], "status": result.get("status"),
                              "relation": relation, "common_m3": result.get("common_m3"),
                              "common_pct_of_smaller": result.get("common_pct_of_smaller"),
                              "volumes": result.get("volumes"), "reason": result.get("reason") or result.get("error"),
                              "warnings": result.get("warnings", [])})
        pairs.sort(key=lambda p: (-(p["common_m3"] or 0.0), p["a"], p["b"]))
        return {"run": run, "evaluated": True, "summary": summary, "pairs": pairs}

    def partners(self, dataset_id: str) -> dict[str, list[str]] | None:
        """For each solid, the solids it shares volume with. None until the analysis of the period is complete."""
        report = self.report(dataset_id)
        if not report["evaluated"] or report["summary"]["pending"]:
            return None
        found: dict[str, list[str]] = {e["filename"]: [] for e in self._catalog.files(dataset_id)}
        for pair in report["pairs"]:
            if pair["relation"] == "overlap":
                found[pair["a"]].append(pair["b"])
                found[pair["b"]].append(pair["a"])
        return {name: sorted(others) for name, others in found.items()}
