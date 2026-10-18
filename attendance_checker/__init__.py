"""Attendance Checker package.

A small, deterministic tool for flagging unusual patterns in attendance and
leave CSV records. Day 1 of implementation only ships schema validation and
the detection configuration; detectors, pipeline, and the Streamlit UI will
follow in later phases.
"""

from attendance_checker.config import DetectionConfig
from attendance_checker.schema import (
    ALLOWED_LEAVE_VALUES,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    SchemaValidationError,
    ValidationIssue,
    ValidationResult,
    read_csv,
    validate,
    validate_csv,
)

__all__ = [
    "ALLOWED_LEAVE_VALUES",
    "DetectionConfig",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "SchemaValidationError",
    "ValidationIssue",
    "ValidationResult",
    "read_csv",
    "validate",
    "validate_csv",
]
