"""Tests for the Day 2 detectors.

Covers, for each of ``detect_unrecorded_attendance``,
``detect_contradictory_leave``, and ``detect_duplicate_record``:

- Exact ``(source_row_index, employee_id, date)`` tuples flagged on a
  dedicated fixture.
- Rows that must NOT be flagged, including: approved leave with zero
  worked hours, unscheduled days, normal full/partial days, leave on an
  unscheduled day, and non-duplicate rows.
- The documented half-day leave limitation.
- Clean records (``clean_minimal.csv``) producing zero flags.
- Empty-DataFrame input producing an empty flags frame with the correct
  schema.
- Immutability of the input DataFrame.
- Flag schema shape and neutral reason strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pandas as pd
import pytest

from attendance_checker.config import DetectionConfig
from attendance_checker.detectors import (
    ANOMALY_CODES,
    FLAG_COLUMNS,
    REASON_CONTRADICTORY_LEAVE,
    REASON_UNRECORDED_ATTENDANCE,
    _empty_flags,
    detect_contradictory_leave,
    detect_duplicate_record,
    detect_implausible_hours,
    detect_sustained_overtime,
    detect_unrecorded_attendance,
)
from attendance_checker.schema import validate_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tuples(flags: pd.DataFrame) -> List[Tuple[int, str, str]]:
    """Return a list of ``(source_row_index, employee_id, YYYY-MM-DD)`` tuples."""
    return [
        (int(row["source_row_index"]), str(row["employee_id"]),
         pd.Timestamp(row["date"]).date().isoformat())
        for _, row in flags.iterrows()
    ]


def _load(fixtures_dir: Path, name: str) -> pd.DataFrame:
    return validate_csv(fixtures_dir / name).data


DEFAULT_CFG = DetectionConfig()


# ---------------------------------------------------------------------------
# Shared contract: flag schema shape
# ---------------------------------------------------------------------------


ALL_DETECTORS = [
    detect_unrecorded_attendance,
    detect_contradictory_leave,
    detect_duplicate_record,
    detect_implausible_hours,
    detect_sustained_overtime,
]


@pytest.mark.parametrize("detector", ALL_DETECTORS)
def test_empty_input_returns_empty_flags_with_schema(detector) -> None:
    empty = pd.DataFrame(
        {
            "employee_id": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="datetime64[ns]"),
            "scheduled_hours": pd.Series([], dtype="float"),
            "worked_hours": pd.Series([], dtype="float"),
            "leave_status": pd.Series([], dtype="object"),
            "source_row_index": pd.Series([], dtype="int64"),
        }
    )
    out = detector(empty, DEFAULT_CFG)
    assert list(out.columns) == FLAG_COLUMNS
    assert len(out) == 0


@pytest.mark.parametrize("detector", ALL_DETECTORS)
def test_detectors_do_not_mutate_input(detector, fixtures_dir: Path) -> None:
    data = _load(fixtures_dir, "clean_minimal.csv")
    snapshot = data.copy(deep=True)
    detector(data, DEFAULT_CFG)
    pd.testing.assert_frame_equal(data, snapshot)


@pytest.mark.parametrize("detector", ALL_DETECTORS)
def test_clean_records_produce_no_flags(detector, fixtures_dir: Path) -> None:
    data = _load(fixtures_dir, "clean_minimal.csv")
    out = detector(data, DEFAULT_CFG)
    assert len(out) == 0, (
        f"{detector.__name__} unexpectedly flagged clean records:\n{out}"
    )


# ---------------------------------------------------------------------------
# UNRECORDED_ATTENDANCE
# ---------------------------------------------------------------------------


def test_unrecorded_attendance_flags_expected_rows(fixtures_dir: Path) -> None:
    data = _load(fixtures_dir, "unrecorded_attendance.csv")
    flags = detect_unrecorded_attendance(data, DEFAULT_CFG)
    # Rows 0 and 5 (0-based data rows) should be the only flags.
    assert _tuples(flags) == [
        (0, "EMP001", "2026-01-05"),
        (5, "EMP006", "2026-01-06"),
    ]
    # Every flag carries the agreed anomaly code and neutral reason string.
    assert set(flags["anomaly_code"]) == {"UNRECORDED_ATTENDANCE"}
    assert set(flags["reason"]) == {REASON_UNRECORDED_ATTENDANCE}


def test_unrecorded_attendance_ignores_approved_leave_zero_hours(
    fixtures_dir: Path,
) -> None:
    """Explicit coverage for the Day 2 requirement.

    A row with ``leave_status`` set and ``worked_hours == 0`` must never be
    flagged by UNRECORDED_ATTENDANCE regardless of scheduled hours.
    """
    data = _load(fixtures_dir, "unrecorded_attendance.csv")
    flags = detect_unrecorded_attendance(data, DEFAULT_CFG)
    flagged_rows = set(int(x) for x in flags["source_row_index"])
    # Row 1 is the sick/zero-hours row; must not be in the flagged set.
    assert 1 not in flagged_rows


def test_unrecorded_attendance_ignores_unscheduled_days(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "unrecorded_attendance.csv")
    flags = detect_unrecorded_attendance(data, DEFAULT_CFG)
    flagged_rows = set(int(x) for x in flags["source_row_index"])
    # Row 2 is scheduled_hours == 0; never a scheduled workday.
    assert 2 not in flagged_rows


# ---------------------------------------------------------------------------
# CONTRADICTORY_LEAVE
# ---------------------------------------------------------------------------


def test_contradictory_leave_flags_expected_rows(fixtures_dir: Path) -> None:
    data = _load(fixtures_dir, "contradictory_leave.csv")
    flags = detect_contradictory_leave(data, DEFAULT_CFG)
    # Rows 0 (sick + 8h) and 4 (vacation + 2h) are the flags.
    assert _tuples(flags) == [
        (0, "EMP001", "2026-01-05"),
        (4, "EMP005", "2026-01-05"),
    ]
    assert set(flags["anomaly_code"]) == {"CONTRADICTORY_LEAVE"}
    assert set(flags["reason"]) == {REASON_CONTRADICTORY_LEAVE}


def test_contradictory_leave_ignores_approved_leave_zero_hours(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "contradictory_leave.csv")
    flags = detect_contradictory_leave(data, DEFAULT_CFG)
    flagged_rows = set(int(x) for x in flags["source_row_index"])
    assert 1 not in flagged_rows  # sick, worked=0
    assert 3 not in flagged_rows  # vacation on unscheduled day, worked=0


def test_contradictory_leave_flags_half_day_as_documented_limitation(
    fixtures_dir: Path,
) -> None:
    """Documented limitation: half-day leave with partial work is flagged.

    The v1 schema has no half-day field, so a half-day sick entry with 4
    worked hours trips CONTRADICTORY_LEAVE. The test pins this behavior so
    any future change (e.g. adding a half-day field) must update it
    deliberately.
    """
    data = _load(fixtures_dir, "half_day_partial_work.csv")
    flags = detect_contradictory_leave(data, DEFAULT_CFG)
    assert _tuples(flags) == [(0, "EMP001", "2026-01-05")]


# ---------------------------------------------------------------------------
# DUPLICATE_RECORD
# ---------------------------------------------------------------------------


def test_duplicate_record_flags_all_rows_in_each_group(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "duplicates.csv")
    flags = detect_duplicate_record(data, DEFAULT_CFG)
    # Pair: rows 0, 1 (EMP001). Triple: rows 3, 4, 5 (EMP003).
    # Rows 2, 6, 7 are unique and must NOT be flagged.
    assert _tuples(flags) == [
        (0, "EMP001", "2026-01-05"),
        (1, "EMP001", "2026-01-05"),
        (3, "EMP003", "2026-01-05"),
        (4, "EMP003", "2026-01-05"),
        (5, "EMP003", "2026-01-05"),
    ]
    assert set(flags["anomaly_code"]) == {"DUPLICATE_RECORD"}


def test_duplicate_record_reason_includes_group_size(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "duplicates.csv")
    flags = detect_duplicate_record(data, DEFAULT_CFG)
    # Build a {source_row_index: reason} map for easier assertions.
    reasons = {int(r["source_row_index"]): r["reason"] for _, r in flags.iterrows()}
    # Pair rows must report group size 2.
    assert "group size 2" in reasons[0]
    assert "group size 2" in reasons[1]
    # Triple rows must report group size 3.
    assert "group size 3" in reasons[3]
    assert "group size 3" in reasons[4]
    assert "group size 3" in reasons[5]
    # Every reason is a neutral, one-sentence string ending with the
    # agreed phrase.
    for r in reasons.values():
        assert r.endswith("records need review.")


def test_duplicate_record_preserves_original_rows(fixtures_dir: Path) -> None:
    """The input DataFrame must not be deduplicated or otherwise modified."""
    data = _load(fixtures_dir, "duplicates.csv")
    before = data.copy(deep=True)
    detect_duplicate_record(data, DEFAULT_CFG)
    pd.testing.assert_frame_equal(data, before)
    # Also: the number of input rows is 8 and no row has been dropped.
    assert len(data) == 8


# ---------------------------------------------------------------------------
# Neutrality / shape
# ---------------------------------------------------------------------------


FORBIDDEN_WORDS = {"absent", "absence", "misconduct", "fraud", "fraudulent"}


@pytest.mark.parametrize(
    "detector,fixture",
    [
        (detect_unrecorded_attendance, "unrecorded_attendance.csv"),
        (detect_contradictory_leave, "contradictory_leave.csv"),
        (detect_duplicate_record, "duplicates.csv"),
        (detect_implausible_hours, "implausible_hours.csv"),
        (detect_sustained_overtime, "overtime_boundary.csv"),
    ],
)
def test_reasons_contain_no_accusatory_language(
    detector, fixture, fixtures_dir: Path
) -> None:
    data = _load(fixtures_dir, fixture)
    flags = detector(data, DEFAULT_CFG)
    for reason in flags["reason"]:
        lowered = str(reason).lower()
        for word in FORBIDDEN_WORDS:
            assert word not in lowered, (
                f"{detector.__name__} reason contains forbidden word "
                f"{word!r}: {reason!r}"
            )


def test_empty_flags_helper_shape() -> None:
    empty = _empty_flags()
    assert list(empty.columns) == FLAG_COLUMNS
    assert len(empty) == 0
    assert str(empty["source_row_index"].dtype) == "int64"
    assert str(empty["date"].dtype) == "datetime64[ns]"


# ---------------------------------------------------------------------------
# IMPLAUSIBLE_HOURS
# ---------------------------------------------------------------------------


def test_implausible_hours_flags_above_default_threshold(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "implausible_hours.csv")
    flags = detect_implausible_hours(data, DetectionConfig())
    # Default max_plausible_hours = 16. Rows 2, 3, 4 (16.5, 20, 24) must flag;
    # rows 0 (15) and 1 (16 - equality is NOT above) must not.
    assert _tuples(flags) == [
        (2, "EMP003", "2026-01-05"),
        (3, "EMP004", "2026-01-05"),
        (4, "EMP005", "2026-01-05"),
    ]
    assert set(flags["anomaly_code"]) == {"IMPLAUSIBLE_HOURS"}
    for reason in flags["reason"]:
        assert "16" in reason  # threshold
        assert reason.endswith("record needs review.")


def test_implausible_hours_threshold_is_configurable(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "implausible_hours.csv")
    # Lift the threshold to 20 -> only rows strictly > 20 flag (24).
    cfg = DetectionConfig(max_plausible_hours=20)
    flags = detect_implausible_hours(data, cfg)
    assert _tuples(flags) == [(4, "EMP005", "2026-01-05")]


def test_implausible_hours_boundary_is_strict_greater_than(
    fixtures_dir: Path,
) -> None:
    """Exactly ``max_plausible_hours`` must NOT be flagged."""
    data = _load(fixtures_dir, "implausible_hours.csv")
    cfg = DetectionConfig(max_plausible_hours=16.5)
    flags = detect_implausible_hours(data, cfg)
    # Row 2 is worked=16.5 and must NOT flag now.
    flagged_rows = set(int(x) for x in flags["source_row_index"])
    assert 2 not in flagged_rows
    assert flagged_rows == {3, 4}


# ---------------------------------------------------------------------------
# SUSTAINED_OVERTIME
# ---------------------------------------------------------------------------


def _overtime_rows(flags: pd.DataFrame) -> List[Tuple[int, str, int]]:
    """Return [(source_row_index, employee_id, parsed_streak_length), ...]."""
    out = []
    for _, r in flags.iterrows():
        reason = str(r["reason"])
        # Reason: "Day is part of a {N}-workday streak where..."
        length = int(reason.split("part of a ")[1].split("-workday")[0])
        out.append((int(r["source_row_index"]), str(r["employee_id"]), length))
    return out


def test_sustained_overtime_streak_length_boundary(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    flags = detect_sustained_overtime(data, DetectionConfig())
    # EMP001 (4-day streak): NOT flagged.
    # EMP002 (5-day streak): rows 5..9 flagged with length 5.
    # EMP003 (6-day streak with a leave day in middle): rows 10,11,13,14,15,16
    #   (NOT 12 - that's the leave day, which the detector skips).
    # EMP004 (gap > 10 days splits into 5 + 5): all 10 flagged, each with
    #   length 5 (not 10).
    # EMP005 (gap == 10 days does NOT break - single streak of 10): all 10
    #   flagged, each with length 10.
    emp_lengths = {}
    for src, emp, length in _overtime_rows(flags):
        emp_lengths.setdefault(emp, []).append((src, length))

    assert "EMP001" not in emp_lengths

    emp002 = sorted(emp_lengths["EMP002"])
    assert [s for s, _ in emp002] == [5, 6, 7, 8, 9]
    assert set(length for _, length in emp002) == {5}


def test_sustained_overtime_leave_day_does_not_break_streak(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    flags = detect_sustained_overtime(data, DetectionConfig())
    emp003 = sorted(
        s for s, e, _ in _overtime_rows(flags) if e == "EMP003"
    )
    # Row 12 (2026-01-07) is leave=sick - detector skips it (not in sequence).
    # The surrounding 6 over days still form a streak of 6.
    assert emp003 == [10, 11, 13, 14, 15, 16]
    for _src, emp, length in _overtime_rows(flags):
        if emp == "EMP003":
            assert length == 6


def test_sustained_overtime_gap_greater_than_max_breaks_streak(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    flags = detect_sustained_overtime(data, DetectionConfig(max_gap_days=10))
    emp004 = [
        (s, length)
        for s, e, length in _overtime_rows(flags)
        if e == "EMP004"
    ]
    # 10 rows flagged (rows 17..26), split into two length-5 streaks.
    assert sorted(s for s, _ in emp004) == list(range(17, 27))
    assert set(length for _, length in emp004) == {5}


def test_sustained_overtime_gap_exactly_at_limit_does_not_break(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    flags = detect_sustained_overtime(data, DetectionConfig(max_gap_days=10))
    emp005 = [
        (s, length)
        for s, e, length in _overtime_rows(flags)
        if e == "EMP005"
    ]
    # Rows 27..36. 10-day gap from row 31 to row 32 must NOT break.
    assert sorted(s for s, _ in emp005) == list(range(27, 37))
    # All ten flags must report a single streak of 10.
    assert set(length for _, length in emp005) == {10}


def test_sustained_overtime_margin_is_configurable(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    # Raise margin to 3.5h: 11 - 8 = 3h is now BELOW margin, so no flags.
    cfg = DetectionConfig(overtime_margin=3.5)
    flags = detect_sustained_overtime(data, cfg)
    assert len(flags) == 0


def test_sustained_overtime_streak_length_is_configurable(
    fixtures_dir: Path,
) -> None:
    data = _load(fixtures_dir, "overtime_boundary.csv")
    # Lower overtime_streak to 4: EMP001's 4-day streak now flags.
    cfg = DetectionConfig(overtime_streak=4)
    flags = detect_sustained_overtime(data, cfg)
    emp001 = sorted(
        s for s, e, _ in _overtime_rows(flags) if e == "EMP001"
    )
    assert emp001 == [0, 1, 2, 3]


def test_sustained_overtime_disable_gap_breaking(
    fixtures_dir: Path,
) -> None:
    """With ``max_gap_days=None`` the EMP004 split becomes one 10-day streak."""
    data = _load(fixtures_dir, "overtime_boundary.csv")
    cfg = DetectionConfig(max_gap_days=None)
    flags = detect_sustained_overtime(data, cfg)
    emp004 = [
        (s, length)
        for s, e, length in _overtime_rows(flags)
        if e == "EMP004"
    ]
    # Still 10 rows, but each reports streak length 10 (not 5).
    assert len(emp004) == 10
    assert set(length for _, length in emp004) == {10}
