"""Detection configuration for the Attendance Checker.

A single immutable dataclass holding every tunable threshold used by the
detectors. Defaults were chosen in design review:

- ``max_plausible_hours = 16.0``  -> IMPLAUSIBLE_HOURS boundary.
- ``overtime_margin = 2.0``       -> SUSTAINED_OVERTIME variance threshold.
- ``overtime_streak = 5``         -> minimum streak length to flag.
- ``max_gap_days = 10``           -> break an overtime streak when
  consecutive entries in the scheduled-workday sequence are more than this
  many calendar days apart. Exactly ``max_gap_days`` apart does NOT break
  the streak (strictly greater than).

The dataclass is frozen so detectors can safely accept a shared instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DetectionConfig:
    """Thresholds used by the five detectors.

    Attributes:
        max_plausible_hours: Upper bound (inclusive) of worked_hours that is
            considered plausible. Values strictly greater than this are
            flagged by IMPLAUSIBLE_HOURS. Must be in the open-closed
            interval (0, 24].
        overtime_margin: Minimum positive variance (worked_hours minus
            scheduled_hours) that counts as an "over" day for the
            SUSTAINED_OVERTIME detector. Must be non-negative.
        overtime_streak: Minimum number of consecutive "over" days required
            to flag a streak. Must be at least 1.
        max_gap_days: Optional calendar-day gap threshold between
            consecutive entries in the per-employee scheduled-workday
            sequence. If the gap is strictly greater than this value, the
            streak breaks. Set to ``None`` to disable gap-breaking. Must be
            at least 1 when provided.
    """

    max_plausible_hours: float = 16.0
    overtime_margin: float = 2.0
    overtime_streak: int = 5
    max_gap_days: Optional[int] = 10

    def __post_init__(self) -> None:
        if not (0 < float(self.max_plausible_hours) <= 24):
            raise ValueError(
                "max_plausible_hours must be in the interval (0, 24]; "
                f"got {self.max_plausible_hours!r}."
            )
        if float(self.overtime_margin) < 0:
            raise ValueError(
                "overtime_margin must be >= 0; "
                f"got {self.overtime_margin!r}."
            )
        if int(self.overtime_streak) < 1:
            raise ValueError(
                "overtime_streak must be >= 1; "
                f"got {self.overtime_streak!r}."
            )
        if self.max_gap_days is not None and int(self.max_gap_days) < 1:
            raise ValueError(
                "max_gap_days must be >= 1 or None; "
                f"got {self.max_gap_days!r}."
            )
