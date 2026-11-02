"""Geological classification and technical execution states (kept separate)."""

from enum import Enum


class GeologicalState(str, Enum):
    NO_CHANGE = "SIN CAMBIOS"
    VARIABLE = "VARIABLE"
    NEW = "NUEVO"
    REMOVED = "ELIMINADO"


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    FAILED = "failed"
    CANCELLED = "cancelled"
