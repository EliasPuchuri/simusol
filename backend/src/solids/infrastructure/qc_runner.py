"""Runs the mesh analysis in a separate process with a per-file time limit.

A mesh that hangs or kills the native libraries must not take the API down:
the child is killed, that file is reported as "failed" with the reason, and a
fresh child serves the next files. One mesh is in memory at a time.
"""

from __future__ import annotations

import importlib
import multiprocessing as mp
from pathlib import Path
from typing import Any

from solids.domain.metrics import Metric
from solids.geometry.qc import failed_result, to_jsonable

DEFAULT_TARGET = "solids.geometry.qc:analyze_mesh"
DEFAULT_TIMEOUT = 180.0


def _plain(value: Any) -> Any:
    if isinstance(value, Metric):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _child(conn, target: str) -> None:  # runs in the spawned process
    module_name, func_name = target.split(":")
    analyze = getattr(importlib.import_module(module_name), func_name)
    while True:
        path = conn.recv()
        if path is None:
            return
        try:
            conn.send(("ok", to_jsonable(_plain(analyze(Path(path))))))
        except Exception as exc:  # the analyzer failed for this file only
            conn.send(("error", f"{exc.__class__.__name__}: {exc}"[:200]))


def _failed(error: str) -> dict[str, Any]:
    return to_jsonable(_plain(failed_result(error)))  # plain JSON, like every result that crosses the pipe


class IsolatedAnalyzer:
    def __init__(self, target: str = DEFAULT_TARGET, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._target = target
        self._timeout = timeout
        self._ctx = mp.get_context("spawn")
        self._proc: mp.process.BaseProcess | None = None
        self._conn = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def _ensure_child(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        parent, child = self._ctx.Pipe()
        self._proc = self._ctx.Process(target=_child, args=(child, self._target), daemon=True)
        self._proc.start()
        child.close()
        self._conn = parent

    def _kill(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.kill()
            self._proc.join(timeout=5)
        if self._conn is not None:
            self._conn.close()
        self._proc, self._conn = None, None

    def analyze(self, path: Path) -> dict[str, Any]:
        self._ensure_child()
        try:
            self._conn.send(str(path))
            if not self._conn.poll(self._timeout):
                self._kill()
                return _failed(f"timeout after {self._timeout:.0f} s")
            kind, payload = self._conn.recv()
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
            self._kill()
            return _failed("process ended unexpectedly while analyzing this file")
        return payload if kind == "ok" else _failed(payload)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
            except Exception:
                pass
        self._kill()
