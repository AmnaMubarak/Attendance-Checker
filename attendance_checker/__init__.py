"""Attendance Checker package.

A small, deterministic tool for flagging unusual patterns in attendance and
leave CSV records. Five detectors, strict schema validation, and a thin
Streamlit UI. Every flag has a neutral one-sentence explanation; no detector
ever labels an employee or implies misconduct.
"""

from attendance_checker.config import DetectionConfig
from attendance_checker.detectors import (
    ANOMALY_CODES,
    FLAG_COLUMNS,
    detect_contradictory_leave,
    detect_duplicate_record,
    detect_implausible_hours,
    detect_sustained_overtime,
    detect_unrecorded_attendance,
)
from attendance_checker.pipeline import (
    AnalysisResult,
    analyze,
    analyze_csv,
)
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
    "ANOMALY_CODES",
    "AnalysisResult",
    "DetectionConfig",
    "FLAG_COLUMNS",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "SchemaValidationError",
    "ValidationIssue",
    "ValidationResult",
    "analyze",
    "analyze_csv",
    "detect_contradictory_leave",
    "detect_duplicate_record",
    "detect_implausible_hours",
    "detect_sustained_overtime",
    "detect_unrecorded_attendance",
    "read_csv",
    "validate",
    "validate_csv",
]
