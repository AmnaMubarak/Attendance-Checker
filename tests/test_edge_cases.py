"""Edge-case tests for the full pipeline.

Covers inputs that the detectors must handle gracefully: empty files, a
single row, employees whose entire window is leave, and files with only
unscheduled days.
"""

from __future__ import annotations

from pathlib import Path

from attendance_checker import analyze_csv
from attendance_checker.detectors import ANOMALY_CODES, FLAG_COLUMNS


def test_empty_csv_produces_no_flags_and_no_errors(fixtures_dir: Path) -> None:
    result = analyze_csv(fixtures_dir / "edge" / "empty.csv")
    assert len(result.data) == 0
    assert len(result.flags) == 0
    assert list(result.flags.columns) == FLAG_COLUMNS
    assert set(result.summary.keys()) == set(ANOMALY_CODES)
    assert all(count == 0 for count in result.summary.values())


def test_single_row_csv_runs_cleanly(fixtures_dir: Path) -> None:
    result = analyze_csv(fixtures_dir / "edge" / "single_row.csv")
    assert len(result.data) == 1
    assert len(result.flags) == 0


def test_employee_with_only_leave_rows_produces_no_flags(
    fixtures_dir: Path,
) -> None:
    """A full week of vacation must trip zero anomalies."""
    result = analyze_csv(fixtures_dir / "edge" / "only_leave.csv")
    assert len(result.data) == 5
    assert len(result.flags) == 0


def test_file_with_only_unscheduled_days_produces_no_flags(
    fixtures_dir: Path,
) -> None:
    result = analyze_csv(fixtures_dir / "edge" / "only_unscheduled.csv")
    assert len(result.data) == 2
    assert len(result.flags) == 0


def test_leave_on_unscheduled_day_produces_no_flags(fixtures_dir: Path) -> None:
    """Per the Day 1 decision, leave on an unscheduled day is ignored."""
    result = analyze_csv(fixtures_dir / "edge" / "leave_on_unscheduled.csv")
    assert len(result.data) == 2
    assert len(result.flags) == 0


def test_high_but_valid_hours_fires_implausible_hours_only(
    fixtures_dir: Path,
) -> None:
    """17h and 24h must flag IMPLAUSIBLE_HOURS and nothing else."""
    result = analyze_csv(fixtures_dir / "edge" / "high_but_valid_hours.csv")
    assert result.summary["IMPLAUSIBLE_HOURS"] == 2
    for code in ANOMALY_CODES:
        if code == "IMPLAUSIBLE_HOURS":
            continue
        assert result.summary[code] == 0


def test_no_leave_status_column_is_tolerated(fixtures_dir: Path) -> None:
    result = analyze_csv(fixtures_dir / "edge" / "no_leave_status_column.csv")
    assert len(result.data) == 2
    # EMP002 (scheduled=8, worked=0, no leave column) must flag
    # UNRECORDED_ATTENDANCE; EMP001 (scheduled=8, worked=8) is clean.
    assert result.summary["UNRECORDED_ATTENDANCE"] == 1
