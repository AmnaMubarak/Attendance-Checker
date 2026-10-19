"""Schema validation for Attendance Checker CSV input.

Validation runs BEFORE any detector. If any error is found, every error is
collected and a single :class:`SchemaValidationError` is raised; detectors
never see partially valid data. The original DataFrame is never mutated:
:class:`ValidationResult` carries both a bitwise copy of what was read and a
new, type-coerced copy for detectors to consume.

Row indices in error messages are 0-based CSV data-row indices (the header
line is excluded), matching the ``source_row_index`` column added to the
validated DataFrame so detectors and the UI can trace a flag back to its
original row.

Design notes
------------
- CSVs are read with ``dtype=str, keep_default_na=False`` so this module
  controls parsing explicitly and emits precise, actionable errors.
- UTF-8 BOMs are tolerated via ``encoding="utf-8-sig"``.
- ``leave_status`` is case-insensitive. Empty / missing values are treated
  as "no leave" and are always valid.
- Per the Day 1 design decisions, dates outside a usual range (before 2000
  or in the future relative to today) are reported as WARNINGS, never
  errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import IO, List, Optional, Union

import pandas as pd

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: tuple[str, ...] = (
    "employee_id",
    "date",
    "scheduled_hours",
    "worked_hours",
)
OPTIONAL_COLUMNS: tuple[str, ...] = ("leave_status", "notes")

ALLOWED_LEAVE_VALUES: frozenset[str] = frozenset(
    {"sick", "vacation", "unpaid", "bereavement", "other"}
)

DATE_FORMAT: str = "%Y-%m-%d"
HOURS_MIN: float = 0.0
HOURS_MAX: float = 24.0

# Warn-only thresholds (never cause validation failure).
WARN_DATE_MIN: date = date(2000, 1, 1)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """One validation finding.

    ``kind`` is either ``"error"`` or ``"warning"``. ``row_index`` is the
    0-based CSV data-row index (header excluded); ``None`` means the issue
    is file-level (e.g. a missing required column). ``code`` is a stable
    machine-readable identifier that tests can assert on. ``message`` is a
    human-readable, actionable sentence.
    """

    kind: str
    code: str
    message: str
    row_index: Optional[int] = None
    column: Optional[str] = None


class SchemaValidationError(Exception):
    """Raised when schema validation finds one or more errors.

    The full list of :class:`ValidationIssue` entries (all with
    ``kind == "error"``) is available on the ``errors`` attribute. The
    exception message previews the first few for log readability.
    """

    def __init__(self, errors: List[ValidationIssue]) -> None:
        if not errors:
            raise ValueError(
                "SchemaValidationError requires at least one error."
            )
        self.errors: List[ValidationIssue] = list(errors)
        preview_count = 5
        preview = "\n".join(
            f"  - [{e.code}] {e.message}" for e in self.errors[:preview_count]
        )
        more = len(self.errors) - preview_count
        suffix = f"\n  ... and {more} more" if more > 0 else ""
        super().__init__(
            f"Schema validation failed with {len(self.errors)} error(s):\n"
            f"{preview}{suffix}"
        )


@dataclass(frozen=True)
class ValidationResult:
    """Result of a successful validation.

    ``data`` is a new, type-coerced DataFrame suitable for detectors.
    ``original_data`` is a deep copy of exactly what was read from the CSV
    (string dtypes, no coercion). ``warnings`` is a possibly-empty list of
    non-fatal findings.
    """

    data: pd.DataFrame
    original_data: pd.DataFrame
    warnings: List[ValidationIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PathOrBuffer = Union[str, Path, IO[str], IO[bytes]]


def read_csv(source: PathOrBuffer) -> pd.DataFrame:
    """Read a CSV as all-string values so this module controls parsing.

    ``keep_default_na=False`` means empty cells become empty strings (not
    NaN); ``encoding="utf-8-sig"`` tolerates UTF-8 BOMs.
    """
    return pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )


def validate_csv(source: PathOrBuffer) -> ValidationResult:
    """Convenience: read a CSV and validate it in one call."""
    return validate(read_csv(source))


def validate(df: pd.DataFrame) -> ValidationResult:
    """Validate ``df`` against the attendance schema.

    On any error, raises :class:`SchemaValidationError` with every error
    collected (not just the first). ``df`` is never modified.
    """
    errors: List[ValidationIssue] = []

    # --- File-level: required columns -----------------------------------
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(
            ValidationIssue(
                kind="error",
                code="MISSING_REQUIRED_COLUMNS",
                message=(
                    "CSV is missing required column(s): "
                    f"{', '.join(missing)}. Required columns are: "
                    f"{', '.join(REQUIRED_COLUMNS)}."
                ),
            )
        )
        # Cannot continue meaningfully without required columns.
        raise SchemaValidationError(errors)

    # --- Per-row checks --------------------------------------------------
    # Work on a reset-index copy so row_index values are 0..N-1 regardless
    # of what the caller passed in.
    working = df.reset_index(drop=True)

    parsed_dates: List[Optional[date]] = [None] * len(working)
    parsed_scheduled: List[Optional[float]] = [None] * len(working)
    parsed_worked: List[Optional[float]] = [None] * len(working)
    parsed_leave: List[str] = [""] * len(working)
    has_leave_column = "leave_status" in working.columns

    for i in range(len(working)):
        row = working.iloc[i]

        # employee_id
        emp_raw = row["employee_id"]
        emp_str = "" if _is_blank(emp_raw) else str(emp_raw).strip()
        if emp_str == "":
            errors.append(
                ValidationIssue(
                    kind="error",
                    code="EMPTY_EMPLOYEE_ID",
                    message=(
                        f"Row {i}: employee_id is empty; every row must "
                        "identify an employee."
                    ),
                    row_index=i,
                    column="employee_id",
                )
            )

        # date
        date_raw = row["date"]
        parsed_date = _parse_iso_date(date_raw)
        if parsed_date is None:
            errors.append(
                ValidationIssue(
                    kind="error",
                    code="BAD_DATE_FORMAT",
                    message=(
                        f"Row {i}: date {date_raw!r} is not in YYYY-MM-DD "
                        "format; use e.g. 2026-01-05."
                    ),
                    row_index=i,
                    column="date",
                )
            )
        else:
            parsed_dates[i] = parsed_date

        # scheduled_hours
        sh = _parse_hours(row["scheduled_hours"])
        if sh.error_code is not None:
            errors.append(
                ValidationIssue(
                    kind="error",
                    code=sh.error_code,
                    message=(
                        f"Row {i}: scheduled_hours {row['scheduled_hours']!r} "
                        f"{sh.error_detail}"
                    ),
                    row_index=i,
                    column="scheduled_hours",
                )
            )
        else:
            parsed_scheduled[i] = sh.value

        # worked_hours
        wh = _parse_hours(row["worked_hours"])
        if wh.error_code is not None:
            errors.append(
                ValidationIssue(
                    kind="error",
                    code=wh.error_code,
                    message=(
                        f"Row {i}: worked_hours {row['worked_hours']!r} "
                        f"{wh.error_detail}"
                    ),
                    row_index=i,
                    column="worked_hours",
                )
            )
        else:
            parsed_worked[i] = wh.value

        # leave_status (optional column)
        if has_leave_column:
            ls_raw = row["leave_status"]
            if _is_blank(ls_raw):
                parsed_leave[i] = ""
            else:
                normalized = str(ls_raw).strip().lower()
                if normalized in ALLOWED_LEAVE_VALUES:
                    parsed_leave[i] = normalized
                else:
                    errors.append(
                        ValidationIssue(
                            kind="error",
                            code="UNKNOWN_LEAVE_STATUS",
                            message=(
                                f"Row {i}: leave_status {ls_raw!r} is not "
                                "one of the allowed values: "
                                f"{sorted(ALLOWED_LEAVE_VALUES)}; use an "
                                "empty cell for no leave."
                            ),
                            row_index=i,
                            column="leave_status",
                        )
                    )

    if errors:
        raise SchemaValidationError(errors)

    # --- Build the validated, type-coerced DataFrame --------------------
    validated = pd.DataFrame(
        {
            "employee_id": [
                str(working.iloc[i]["employee_id"]).strip()
                for i in range(len(working))
            ],
            "date": pd.to_datetime(parsed_dates),
            "scheduled_hours": parsed_scheduled,
            "worked_hours": parsed_worked,
            "leave_status": parsed_leave,
            "source_row_index": list(range(len(working))),
        }
    )
    validated["scheduled_hours"] = validated["scheduled_hours"].astype(float)
    validated["worked_hours"] = validated["worked_hours"].astype(float)
    if "notes" in working.columns:
        validated["notes"] = working["notes"].astype(str).reset_index(drop=True)

    # --- Warnings pass (non-fatal) --------------------------------------
    warnings: List[ValidationIssue] = []
    today = pd.Timestamp(datetime.now().date())
    warn_min = pd.Timestamp(WARN_DATE_MIN)
    for i, d in enumerate(validated["date"]):
        if d < warn_min or d > today:
            warnings.append(
                ValidationIssue(
                    kind="warning",
                    code="UNUSUAL_DATE",
                    message=(
                        f"Row {i}: date {d.date().isoformat()} is before "
                        f"{WARN_DATE_MIN.isoformat()} or in the future; "
                        "review if this is intentional."
                    ),
                    row_index=i,
                    column="date",
                )
            )

    return ValidationResult(
        data=validated,
        original_data=df.copy(deep=True),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_blank(value: object) -> bool:
    """True if value is NaN, None, or a whitespace-only / empty string."""
    if value is None:
        return True
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_iso_date(value: object) -> Optional[date]:
    """Parse strictly as YYYY-MM-DD. Return ``None`` on any failure."""
    if _is_blank(value):
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        return None


@dataclass(frozen=True)
class _HoursParse:
    value: Optional[float] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


def _parse_hours(value: object) -> _HoursParse:
    """Parse an hours cell with specific error codes per failure mode."""
    if _is_blank(value):
        return _HoursParse(
            error_code="NON_NUMERIC_HOURS",
            error_detail=(
                "is empty; required numeric hours cells must contain a "
                "number (use 0 for a non-worked day)."
            ),
        )
    text = str(value).strip()
    try:
        parsed = float(text)
    except ValueError:
        return _HoursParse(
            error_code="NON_NUMERIC_HOURS",
            error_detail="cannot be parsed as a number.",
        )
    # Also reject NaN / inf that technically survived float()
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return _HoursParse(
            error_code="NON_NUMERIC_HOURS",
            error_detail="is not a finite number.",
        )
    if parsed < HOURS_MIN:
        return _HoursParse(
            error_code="NEGATIVE_HOURS",
            error_detail=(
                f"is negative; hours must be in the range "
                f"[{HOURS_MIN}, {HOURS_MAX}]."
            ),
        )
    if parsed > HOURS_MAX:
        return _HoursParse(
            error_code="HOURS_OUT_OF_RANGE",
            error_detail=(
                f"exceeds the maximum of {HOURS_MAX}; hours must be in the "
                f"range [{HOURS_MIN}, {HOURS_MAX}]."
            ),
        )
    return _HoursParse(value=parsed)


# Prevent accidental re-export of helpers via "from attendance_checker.schema import *".
__all__ = [
    "ALLOWED_LEAVE_VALUES",
    "DATE_FORMAT",
    "HOURS_MAX",
    "HOURS_MIN",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "SchemaValidationError",
    "ValidationIssue",
    "ValidationResult",
    "WARN_DATE_MIN",
    "read_csv",
    "validate",
    "validate_csv",
]
