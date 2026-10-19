"""Deterministic anomaly detectors.

Day 2 ships the first three detectors. Each one is a pure function with the
same signature so the eventual pipeline can call them uniformly::

    detect_<name>(data: pd.DataFrame, config: DetectionConfig) -> pd.DataFrame

Inputs
------
``data`` is the validated, type-coerced DataFrame produced by
``attendance_checker.schema.validate`` (``ValidationResult.data``). It is
guaranteed to have the required columns, correct dtypes, a normalized
``leave_status`` column (lowercased, empty string = no leave), and a
``source_row_index`` column that points back to the original CSV row.

Detectors never mutate ``data``. They return a *new* "flags" DataFrame.

Output ("flags" DataFrame)
--------------------------
Every detector returns a DataFrame with exactly these columns::

    source_row_index : int64        # 0-based CSV data row index
    employee_id      : object       # as validated
    date             : datetime64[ns]
    anomaly_code     : object       # stable, machine-readable code
    reason           : object       # one-sentence, neutral explanation

An empty-flags DataFrame still has these columns with the right dtypes so
callers can safely concatenate results.

Neutrality
----------
Every reason string ends in "record needs review" (or "records need review"
for group-level flags). No detector ever labels an employee, implies
absence, or alleges misconduct.
"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from attendance_checker.config import DetectionConfig


# ---------------------------------------------------------------------------
# Flag schema
# ---------------------------------------------------------------------------

FLAG_COLUMNS: List[str] = [
    "source_row_index",
    "employee_id",
    "date",
    "anomaly_code",
    "reason",
]

# Stable ordering of anomaly codes for summary tables and UI display.
ANOMALY_CODES: Tuple[str, ...] = (
    "UNRECORDED_ATTENDANCE",
    "CONTRADICTORY_LEAVE",
    "DUPLICATE_RECORD",
    "IMPLAUSIBLE_HOURS",
    "SUSTAINED_OVERTIME",
)

# Reason strings - frozen at the design-review stage.
REASON_UNRECORDED_ATTENDANCE: str = (
    "Scheduled day has zero recorded work hours and no leave entry; "
    "record needs review."
)
REASON_CONTRADICTORY_LEAVE: str = (
    "Leave status is set but worked hours are greater than zero; "
    "record needs review."
)
REASON_DUPLICATE_RECORD_TEMPLATE: str = (
    "Employee has more than one row for this date (group size {n}); "
    "records need review."
)
REASON_IMPLAUSIBLE_HOURS_TEMPLATE: str = (
    "Worked hours ({h:g}) exceed the configured plausible maximum "
    "({max:g}); record needs review."
)
REASON_SUSTAINED_OVERTIME_TEMPLATE: str = (
    "Day is part of a {length}-workday streak where worked hours exceeded "
    "scheduled by at least {margin:g}h; schedule needs review."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_flags() -> pd.DataFrame:
    """Return an empty flags DataFrame with the canonical dtypes."""
    return pd.DataFrame(
        {
            "source_row_index": pd.Series([], dtype="int64"),
            "employee_id": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="datetime64[ns]"),
            "anomaly_code": pd.Series([], dtype="object"),
            "reason": pd.Series([], dtype="object"),
        }
    )


def _build_flags(
    source_rows: pd.DataFrame,
    anomaly_code: str,
    reason: object,
) -> pd.DataFrame:
    """Construct a flags DataFrame from the matching rows of ``data``.

    ``reason`` may be a single string (broadcast to all rows) or an iterable
    with one reason per row (same length as ``source_rows``).
    """
    if source_rows.empty:
        return _empty_flags()
    flags = pd.DataFrame(
        {
            "source_row_index": source_rows["source_row_index"]
            .astype("int64")
            .to_numpy(),
            "employee_id": source_rows["employee_id"].to_numpy(),
            "date": pd.to_datetime(source_rows["date"].to_numpy()),
            "anomaly_code": anomaly_code,
            "reason": reason,
        }
    )
    # Preserve original CSV order for stable, reviewable output.
    return (
        flags[FLAG_COLUMNS]
        .sort_values("source_row_index", kind="mergesort")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def detect_unrecorded_attendance(
    data: pd.DataFrame, config: DetectionConfig
) -> pd.DataFrame:
    """UNRECORDED_ATTENDANCE: scheduled day with no work and no leave logged.

    Trigger
    -------
    ``scheduled_hours > 0`` AND ``worked_hours == 0`` AND ``leave_status``
    is empty.

    Notes
    -----
    - Does NOT imply the employee was absent; the record simply has no
      explanation for the missing hours and should be reviewed.
    - A sick/vacation day with zero worked hours is explicitly NOT flagged
      (leave_status is set).
    - A row with ``scheduled_hours == 0`` (weekend/holiday) is explicitly
      NOT flagged.
    - ``config`` is accepted for signature uniformity across detectors;
      this detector has no tunable threshold.
    """
    _ = config  # unused; kept for uniform signature
    if data.empty:
        return _empty_flags()
    mask = (
        (data["scheduled_hours"] > 0)
        & (data["worked_hours"] == 0)
        & (data["leave_status"] == "")
    )
    return _build_flags(
        data.loc[mask],
        anomaly_code="UNRECORDED_ATTENDANCE",
        reason=REASON_UNRECORDED_ATTENDANCE,
    )


def detect_contradictory_leave(
    data: pd.DataFrame, config: DetectionConfig
) -> pd.DataFrame:
    """CONTRADICTORY_LEAVE: leave entry present alongside worked hours.

    Trigger
    -------
    ``leave_status`` is set (non-empty) AND ``worked_hours > 0``.

    Known limitation (half-day leave)
    ---------------------------------
    The v1 schema has no half-day field, so a half-day leave recorded with
    partial worked hours (e.g. ``sick`` with 4 worked hours) will be
    flagged. This is documented in the README's Known Limitations section
    and is covered by a dedicated test fixture.

    ``config`` is accepted for signature uniformity; this detector has no
    tunable threshold.
    """
    _ = config  # unused; kept for uniform signature
    if data.empty:
        return _empty_flags()
    mask = (data["leave_status"] != "") & (data["worked_hours"] > 0)
    return _build_flags(
        data.loc[mask],
        anomaly_code="CONTRADICTORY_LEAVE",
        reason=REASON_CONTRADICTORY_LEAVE,
    )


def detect_duplicate_record(
    data: pd.DataFrame, config: DetectionConfig
) -> pd.DataFrame:
    """DUPLICATE_RECORD: more than one row for the same employee/date.

    Trigger
    -------
    For each ``(employee_id, date)`` group whose size is greater than 1,
    flag EVERY row in the group. The input DataFrame is never deduplicated
    or modified; the reviewer decides what to do with the duplicates.

    Each flag's reason includes the group size so the reviewer can see
    pairs vs triples at a glance.

    ``config`` is accepted for signature uniformity; this detector has no
    tunable threshold.
    """
    _ = config  # unused; kept for uniform signature
    if data.empty:
        return _empty_flags()

    group_sizes = data.groupby(["employee_id", "date"])[
        "employee_id"
    ].transform("size")
    mask = group_sizes > 1
    matched = data.loc[mask]
    if matched.empty:
        return _empty_flags()

    sizes_for_matched = group_sizes.loc[mask].astype(int).to_numpy()
    reasons = [
        REASON_DUPLICATE_RECORD_TEMPLATE.format(n=int(n))
        for n in sizes_for_matched
    ]
    return _build_flags(
        matched,
        anomaly_code="DUPLICATE_RECORD",
        reason=reasons,
    )


def detect_implausible_hours(
    data: pd.DataFrame, config: DetectionConfig
) -> pd.DataFrame:
    """IMPLAUSIBLE_HOURS: worked hours above the configured plausible maximum.

    Trigger
    -------
    ``worked_hours > config.max_plausible_hours``.

    Notes
    -----
    The schema already rejects negative values and values greater than 24,
    so this detector only needs to compare against the configurable upper
    bound. By default ``max_plausible_hours = 16``, which flags a 17-hour
    day (schema-valid, but worth a human sanity check).
    """
    if data.empty:
        return _empty_flags()
    threshold = float(config.max_plausible_hours)
    mask = data["worked_hours"] > threshold
    matched = data.loc[mask]
    if matched.empty:
        return _empty_flags()
    reasons = [
        REASON_IMPLAUSIBLE_HOURS_TEMPLATE.format(
            h=float(h), max=threshold
        )
        for h in matched["worked_hours"].to_numpy()
    ]
    return _build_flags(
        matched,
        anomaly_code="IMPLAUSIBLE_HOURS",
        reason=reasons,
    )


def _streak_runs_for_employee(
    group: pd.DataFrame, config: DetectionConfig
) -> List[Tuple[List[int], int]]:
    """Return ``[(source_row_indices, streak_length), ...]`` for one employee.

    ``group`` is already restricted to the employee's scheduled-workday
    sequence (``scheduled_hours > 0`` and ``leave_status == ""``) and
    sorted by ``date`` ascending. A run ends when the current entry is not
    "over" (``worked_hours - scheduled_hours < overtime_margin``) OR when
    the gap from the previous entry in the sequence exceeds
    ``config.max_gap_days`` calendar days (strict ``>``; equal does not
    break). Only runs of length ``>= config.overtime_streak`` are returned.
    """
    results: List[Tuple[List[int], int]] = []
    current: List[int] = []
    prev_date = None
    margin = float(config.overtime_margin)
    gap_limit = config.max_gap_days  # may be None (gap-breaking disabled)

    def _finalize() -> None:
        if len(current) >= config.overtime_streak:
            results.append((list(current), len(current)))

    for _, row in group.iterrows():
        d = row["date"]
        is_over = (
            float(row["worked_hours"]) - float(row["scheduled_hours"])
            >= margin
        )
        gap_too_big = (
            gap_limit is not None
            and prev_date is not None
            and (d - prev_date).days > int(gap_limit)
        )
        if gap_too_big or not is_over:
            _finalize()
            current = []
        if is_over:
            current.append(int(row["source_row_index"]))
        prev_date = d

    _finalize()
    return results


def detect_sustained_overtime(
    data: pd.DataFrame, config: DetectionConfig
) -> pd.DataFrame:
    """SUSTAINED_OVERTIME: long streak of positive worked-vs-scheduled variance.

    Precise definition (frozen at design review)
    --------------------------------------------
    Per employee, build the scheduled-workday sequence: rows where
    ``scheduled_hours > 0`` AND ``leave_status`` is empty. Sort by date
    ascending. Within this sequence, a day is "over" when
    ``worked_hours - scheduled_hours >= config.overtime_margin``. A streak
    is a maximal run of consecutive "over" entries in the sequence. A
    streak is flagged when its length is ``>= config.overtime_streak``.

    Effect of each situation on a streak:
    - Scheduled "over" day: extends the streak.
    - Scheduled under-threshold day: breaks the streak.
    - Unscheduled day (``scheduled_hours == 0``): skipped - neither
      extends nor breaks (not in the sequence).
    - Leave day (``leave_status`` set): skipped - neither extends nor
      breaks (not in the sequence).
    - Missing date (no row at all): skipped - neither extends nor
      breaks.

    If ``config.max_gap_days`` is set (default 10), two consecutive
    entries in the sequence that are more than that many CALENDAR days
    apart break the streak. Exactly ``max_gap_days`` apart does NOT
    break (strict greater-than).

    Each row inside a qualifying streak gets its own flag so the UI can
    show every affected day; the reason reports the length of the
    containing streak.
    """
    if data.empty:
        return _empty_flags()

    seq_mask = (data["scheduled_hours"] > 0) & (data["leave_status"] == "")
    seq = data.loc[seq_mask]
    if seq.empty:
        return _empty_flags()
    seq = seq.sort_values(["employee_id", "date"], kind="mergesort")

    flagged_source_rows: List[int] = []
    streak_length_by_row: dict = {}

    for _, group in seq.groupby("employee_id", sort=False):
        for row_indices, length in _streak_runs_for_employee(group, config):
            for src in row_indices:
                flagged_source_rows.append(src)
                streak_length_by_row[src] = length

    if not flagged_source_rows:
        return _empty_flags()

    matched = data.loc[data["source_row_index"].isin(flagged_source_rows)]
    reasons = [
        REASON_SUSTAINED_OVERTIME_TEMPLATE.format(
            length=streak_length_by_row[int(src)],
            margin=float(config.overtime_margin),
        )
        for src in matched["source_row_index"].to_numpy()
    ]
    return _build_flags(
        matched,
        anomaly_code="SUSTAINED_OVERTIME",
        reason=reasons,
    )


__all__ = [
    "ANOMALY_CODES",
    "FLAG_COLUMNS",
    "REASON_CONTRADICTORY_LEAVE",
    "REASON_DUPLICATE_RECORD_TEMPLATE",
    "REASON_IMPLAUSIBLE_HOURS_TEMPLATE",
    "REASON_SUSTAINED_OVERTIME_TEMPLATE",
    "REASON_UNRECORDED_ATTENDANCE",
    "detect_contradictory_leave",
    "detect_duplicate_record",
    "detect_implausible_hours",
    "detect_sustained_overtime",
    "detect_unrecorded_attendance",
]
