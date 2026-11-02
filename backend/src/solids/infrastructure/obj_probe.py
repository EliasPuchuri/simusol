"""Streaming sniffer that checks a byte stream looks like a Wavefront OBJ."""

from __future__ import annotations

_MAX_LINE = 64 * 1024


class ObjProbe:
    """Feed chunks; ``is_obj`` is true once a vertex and a face line were seen.

    Memory is bounded: a pending partial line longer than ``_MAX_LINE`` marks
    the stream as non-text and is discarded.
    """

    def __init__(self) -> None:
        self._tail = b""
        self.has_vertex = False
        self.has_face = False
        self.overlong_line = False

    def feed(self, chunk: bytes) -> None:
        lines = (self._tail + chunk).split(b"\n")
        self._tail = lines.pop()
        for line in lines:
            self._classify(line)
        if len(self._tail) > _MAX_LINE:
            self.overlong_line = True
            self._tail = b""

    def finish(self) -> None:
        self._classify(self._tail)
        self._tail = b""

    def _classify(self, line: bytes) -> None:
        text = line.lstrip()
        if text.startswith(b"v "):
            self.has_vertex = True
        elif text.startswith(b"f "):
            self.has_face = True

    @property
    def is_obj(self) -> bool:
        return self.has_vertex and self.has_face and not self.overlong_line
