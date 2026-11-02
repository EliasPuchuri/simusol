"""Metric values that always carry their validity condition."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Validity(str, Enum):
    VALID = "valid"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class Metric:
    """A numeric result plus the condition under which it was (not) obtained.

    A failed or missing computation is never represented as 0 or NaN: its
    value is ``None`` and a reason is mandatory.
    """

    value: float | None
    validity: Validity
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.validity is Validity.VALID:
            if self.value is None or not math.isfinite(self.value):
                raise ValueError("a valid metric requires a finite value")
            if self.reason is not None:
                raise ValueError("a valid metric has no reason")
        else:
            if self.value is not None:
                raise ValueError("a non-valid metric must not carry a value")
            if not self.reason:
                raise ValueError("a non-valid metric requires a reason")

    @classmethod
    def valid(cls, value: float) -> Metric:
        return cls(float(value), Validity.VALID)

    @classmethod
    def not_applicable(cls, reason: str) -> Metric:
        return cls(None, Validity.NOT_APPLICABLE, reason)

    @classmethod
    def unavailable(cls, reason: str) -> Metric:
        return cls(None, Validity.UNAVAILABLE, reason)

    @classmethod
    def failed(cls, reason: str) -> Metric:
        return cls(None, Validity.FAILED, reason)

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "validity": self.validity.value, "reason": self.reason}
