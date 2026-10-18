"""Tests for ``attendance_checker.schema``.

Covers:
- Happy-path validation of a clean CSV.
- Preservation of the original input data (immutability guarantee).
- Each malformed-input class is rejected with the expected error code.
- Edge cases: empty CSV, single row, leave on an unscheduled day,
  high-but-valid hours, no leave_status column, case-insensitive leave.
- Date warnings (unusual dates warn only; they never fail validation).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from attendance_checker.schema import (
    ALLOWED_LEAVE_VALUES,
    REQUIRED_COLUMNS,
    SchemaValidationError,
    ValidationIssue,
    read_csv,
    validate,
    validate_csv,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _codes(errors: list[ValidationIssue]) -> list[str]:
    return [e.code for e in errors]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_clean_minimal_validates_without_errors(fixtures_dir: Path) -> None:
    result = validate_csv(fixtures_dir / "clean_minimal.csv")

    # 6 rows, correct columns and dtypes.
    assert len(result.data) == 6
    for col in REQUIRED_COLUMNS:
        assert col in result.data.columns
    assert "leave_status" in result.data.columns
    assert "source_row_index" in result.data.columns
    assert pd.api.types.is_datetime64_any_dtype(result.data["date"])
    assert pd.api.types.is_float_dtype(result.data["scheduled_hours"])
    assert pd.api.types.is_float_dtype(result.data["worked_hours"])

    # source_row_index is 0..N-1 and traces back to original rows.
    assert list(result.data["source_row_index"]) == list(range(6))

    # No warnings expected for recent in-range dates.
    assert result.warnings == []


def test_approved_leave_with_zero_hours_is_valid(fixtures_dir: Path) -> None:
    """A sick/vacation day with 0 worked hours is a clean, valid record."""
    result = validate_csv(fixtures_dir / "clean_minimal.csv")
    sick_rows = result.data[result.data["leave_status"] == "sick"]
    assert len(sick_rows) == 1
    assert float(sick_rows.iloc[0]["worked_hours"]) == 0.0
    # And no warnings fired on this row.
    assert result.warnings == []


# ---------------------------------------------------------------------------
# Immutability / preservation of the original
# ---------------------------------------------------------------------------


def test_original_data_is_preserved_untouched(fixtures_dir: Path) -> None:
    raw = read_csv(fixtures_dir / "clean_minimal.csv")
    raw_snapshot = raw.copy(deep=True)

    result = validate(raw)

    # Caller's input DataFrame not mutated.
    pd.testing.assert_frame_equal(raw, raw_snapshot)
    # result.original_data is a deep copy equal to the raw read.
    pd.testing.assert_frame_equal(result.original_data, raw_snapshot)
    # Mutating the validated copy must not affect the original.
    result.data.loc[0, "worked_hours"] = 999.0
    pd.testing.assert_frame_equal(result.original_data, raw_snapshot)


# ---------------------------------------------------------------------------
# Malformed inputs - one test per class
# ---------------------------------------------------------------------------


def test_missing_required_column_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "missing_column.csv")
    codes = _codes(excinfo.value.errors)
    assert codes == ["MISSING_REQUIRED_COLUMNS"]
    assert "worked_hours" in excinfo.value.errors[0].message


def test_bad_date_format_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "bad_date.csv")
    codes = _codes(excinfo.value.errors)
    assert codes == ["BAD_DATE_FORMAT"] * 3
    # Row indices are 0-based data rows (header excluded).
    assert [e.row_index for e in excinfo.value.errors] == [0, 1, 2]
    assert all(e.column == "date" for e in excinfo.value.errors)


def test_nonnumeric_hours_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "nonnumeric_hours.csv")
    codes = _codes(excinfo.value.errors)
    # Two errors: one for "eight" (row 0, scheduled_hours), one for the empty
    # worked_hours cell (row 1).
    assert codes == ["NON_NUMERIC_HOURS", "NON_NUMERIC_HOURS"]
    columns = [e.column for e in excinfo.value.errors]
    assert columns == ["scheduled_hours", "worked_hours"]


def test_negative_hours_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "negative_hours.csv")
    codes = _codes(excinfo.value.errors)
    assert codes == ["NEGATIVE_HOURS", "NEGATIVE_HOURS"]


def test_hours_over_24_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "hours_over_24.csv")
    codes = _codes(excinfo.value.errors)
    assert codes == ["HOURS_OUT_OF_RANGE", "HOURS_OUT_OF_RANGE"]


def test_unknown_leave_status_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "unknown_leave_status.csv")
    codes = _codes(excinfo.value.errors)
    assert codes == ["UNKNOWN_LEAVE_STATUS", "UNKNOWN_LEAVE_STATUS"]
    assert "holiday" in excinfo.value.errors[0].message


def test_empty_employee_id_rejected(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_csv(fixtures_dir / "malformed" / "empty_employee_id.csv")
    codes = _codes(excinfo.value.errors)
    # Both the fully empty cell and the whitespace-only cell count.
    assert codes == ["EMPTY_EMPLOYEE_ID", "EMPTY_EMPLOYEE_ID"]


def test_multiple_errors_are_all_collected() -> None:
    """One failed call should surface every error, not just the first."""
    df = pd.DataFrame(
        {
            "employee_id": ["EMP001", "", "EMP003"],
            "date": ["2026-01-05", "not-a-date", "2026-01-07"],
            "scheduled_hours": ["8", "8", "abc"],
            "worked_hours": ["8", "-1", "8"],
            "leave_status": ["", "", "holiday"],
        }
    )
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(df)
    codes = sorted(_codes(excinfo.value.errors))
    assert codes == sorted(
        [
            "EMPTY_EMPLOYEE_ID",
            "BAD_DATE_FORMAT",
            "NEGATIVE_HOURS",
            "NON_NUMERIC_HOURS",
            "UNKNOWN_LEAVE_STATUS",
        ]
    )


def test_error_messages_mention_row_and_column() -> None:
    """Error messages must be actionable: cite the row and the column."""
    df = pd.DataFrame(
        {
            "employee_id": ["EMP001"],
            "date": ["2026-01-05"],
            "scheduled_hours": ["8"],
            "worked_hours": ["bad"],
            "leave_status": [""],
        }
    )
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(df)
    err = excinfo.value.errors[0]
    assert err.row_index == 0
    assert err.column == "worked_hours"
    assert "Row 0" in err.message
    assert "worked_hours" in err.message


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_csv_is_valid(fixtures_dir: Path) -> None:
    result = validate_csv(fixtures_dir / "edge" / "empty.csv")
    assert len(result.data) == 0
    assert result.warnings == []
    for col in REQUIRED_COLUMNS:
        assert col in result.data.columns


def test_single_row_csv_is_valid(fixtures_dir: Path) -> None:
    result = validate_csv(fixtures_dir / "edge" / "single_row.csv")
    assert len(result.data) == 1
    assert result.data.iloc[0]["employee_id"] == "EMP001"
    assert float(result.data.iloc[0]["worked_hours"]) == 8.0


def test_leave_on_unscheduled_day_is_valid(fixtures_dir: Path) -> None:
    """Per the Day 1 decision, leave entries on scheduled_hours == 0 pass."""
    result = validate_csv(fixtures_dir / "edge" / "leave_on_unscheduled.csv")
    assert len(result.data) == 2
    assert set(result.data["leave_status"]) == {"vacation", "sick"}
    assert (result.data["scheduled_hours"] == 0).all()
    assert result.warnings == []


def test_high_but_valid_hours_pass_schema(fixtures_dir: Path) -> None:
    """17h must pass the schema (<= 24) so IMPLAUSIBLE_HOURS can flag it later."""
    result = validate_csv(fixtures_dir / "edge" / "high_but_valid_hours.csv")
    assert len(result.data) == 2
    assert float(result.data.iloc[0]["worked_hours"]) == 17.0
    assert float(result.data.iloc[1]["worked_hours"]) == 24.0


def test_no_leave_status_column_is_valid(fixtures_dir: Path) -> None:
    """leave_status is optional; its absence must not fail validation."""
    result = validate_csv(fixtures_dir / "edge" / "no_leave_status_column.csv")
    assert len(result.data) == 2
    # Validator fills in an empty leave_status column for downstream consumers.
    assert "leave_status" in result.data.columns
    assert (result.data["leave_status"] == "").all()


def test_leave_status_is_case_insensitive_and_trimmed(fixtures_dir: Path) -> None:
    result = validate_csv(fixtures_dir / "edge" / "case_insensitive_leave.csv")
    assert list(result.data["leave_status"]) == ["sick", "vacation", "unpaid"]
    for val in result.data["leave_status"]:
        assert val in ALLOWED_LEAVE_VALUES


# ---------------------------------------------------------------------------
# Warnings (non-fatal)
# ---------------------------------------------------------------------------


def test_unusual_dates_warn_but_do_not_fail(fixtures_dir: Path) -> None:
    result = validate_csv(fixtures_dir / "edge" / "unusual_date.csv")
    # Validation succeeds; 3 rows preserved.
    assert len(result.data) == 3
    # Two warnings: the 1999 date and the 2099 date. The 2026 date is fine.
    warn_codes = [w.code for w in result.warnings]
    assert warn_codes == ["UNUSUAL_DATE", "UNUSUAL_DATE"]
    warn_rows = [w.row_index for w in result.warnings]
    assert warn_rows == [0, 1]
    for w in result.warnings:
        assert w.kind == "warning"
        assert w.column == "date"


# ---------------------------------------------------------------------------
# Error-object shape
# ---------------------------------------------------------------------------


def test_schema_validation_error_summarises_count() -> None:
    df = pd.DataFrame(
        {
            "employee_id": ["", "", ""],
            "date": ["2026-01-05", "2026-01-06", "2026-01-07"],
            "scheduled_hours": ["8", "8", "8"],
            "worked_hours": ["8", "8", "8"],
        }
    )
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(df)
    assert "3 error(s)" in str(excinfo.value)
    assert len(excinfo.value.errors) == 3


def test_schema_validation_error_requires_errors() -> None:
    with pytest.raises(ValueError):
        SchemaValidationError([])
