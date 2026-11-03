"""Runs the mesh analysis in a separate process with a per-file time limit.

A mesh that hangs or kills the native libraries must not take the API down:
the child is killed, that file is reported as "failed" with the reason, and a
fresh child serves the next files. One mesh is in memory at a time.
"""

from __future__ import annotations

import importlib
import multiprocessing as mp
import os
from pathlib import Path
from typing import Any

from solids.domain.metrics import Metric
from typing import Callable

from solids.geometry.qc import failed_result, to_jsonable

# One thread per numerical library in the worker: predictable CPU use on a shared host with a CPU quota
# (the plan asks for one library thread per process). Respects values already set by the operator.
_SINGLE_THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")

DEFAULT_TARGET = "solids.geometry.qc:analyze_mesh"
DEFAULT_TIMEOUT = 180.0
START_TIMEOUT = 120.0  # a fresh child importing the native libraries on a slow host; not charged to the file
_WARM_UP = ("numpy", "scipy.spatial", "trimesh", "manifold3d")


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
    for name in _WARM_UP:  # pay the import cost before the first file's clock starts
        try:
            importlib.import_module(name)
        except Exception:
            pass
    conn.send(("ready", None))
    while True:
        paths = conn.recv()
        if paths is None:
            return
        try:
            conn.send(("ok", to_jsonable(_plain(analyze(*[Path(p) for p in paths])))))
        except Exception as exc:  # the analyzer failed for this file only
            conn.send(("error", f"{exc.__class__.__name__}: {exc}"[:200]))


class _StartFailed(Exception):
    pass


def _plain_failure(factory: Callable[[str], dict], error: str) -> dict[str, Any]:
    return to_jsonable(_plain(factory(error)))  # plain JSON, like every result that crosses the pipe


class IsolatedAnalyzer:
    def __init__(self, target: str = DEFAULT_TARGET, timeout: float = DEFAULT_TIMEOUT,
                 failure: Callable[[str], dict] = failed_result, start_timeout: float = START_TIMEOUT) -> None:
        self._failure = failure
        self._target = target
        self._timeout = timeout
        self._start_timeout = start_timeout
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
        previous = {k: os.environ.get(k) for k in _SINGLE_THREAD_ENV}
        for key in _SINGLE_THREAD_ENV:
            os.environ.setdefault(key, "1")  # the child inherits the environment at start
        try:
            self._proc.start()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
        child.close()
        self._conn = parent
        try:
            started = parent.poll(self._start_timeout) and parent.recv()[0] == "ready"
        except (EOFError, OSError):
            started = False
        if not started:
            self._kill()
            raise _StartFailed()

    def _kill(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.kill()
            self._proc.join(timeout=5)
        if self._conn is not None:
            self._conn.close()
        self._proc, self._conn = None, None

    def analyze(self, *paths: Path) -> dict[str, Any]:
        try:
            self._ensure_child()
        except _StartFailed:
            return _plain_failure(self._failure, "the analysis process could not start")
        try:
            self._conn.send([str(p) for p in paths])
            if not self._conn.poll(self._timeout):
                self._kill()
                return _plain_failure(self._failure, f"timeout after {self._timeout:.0f} s")
            kind, payload = self._conn.recv()
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
            self._kill()
            return _plain_failure(self._failure, "process ended unexpectedly while analyzing this file")
        return payload if kind == "ok" else _plain_failure(self._failure, payload)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
            except Exception:
                pass
        self._kill()
