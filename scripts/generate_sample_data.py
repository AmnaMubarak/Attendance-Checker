"""Generate a realistic-looking fictional attendance CSV for demo purposes.

Writes ``sample_data/attendance_sample.csv`` with:

- 25 fictional employees (``EMP001`` .. ``EMP025``).
- 8 consecutive weeks starting Monday 2026-01-05 (56 calendar days).
- One row per employee per calendar day = 1400 base rows (plus 1 duplicate
  row injected for ``DUPLICATE_RECORD``, so 1401 total).
- Weekdays scheduled_hours = 8 with small realistic variance in
  worked_hours; weekends unscheduled (scheduled = worked = 0).
- ~5 percent of weekdays are taken as sick or vacation leave (worked = 0).
- Exactly ONE deliberate instance of each of the five anomalies, pinned to
  specific (employee_id, date) coordinates documented below so you can
  verify them.

The dataset is produced with a fixed seed so re-running the script yields
byte-identical output.

Run from the project root::

    python scripts/generate_sample_data.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Generator parameters
# ---------------------------------------------------------------------------

SEED: int = 20260101
NUM_EMPLOYEES: int = 25
WEEKS: int = 8
START_DATE: date = date(2026, 1, 5)  # must be a Monday
LEAVE_PROBABILITY: float = 0.05
WORKED_HOURS_MIN: float = 7.5
WORKED_HOURS_MAX: float = 8.5

# Deliberate anomaly injections. Change coordinates here if you want to
# re-pin them; keep each anomaly's precondition in mind (SUSTAINED_OVERTIME
# needs a Monday start to span one business week).
ANOMALY_UNRECORDED = ("EMP007", date(2026, 1, 15))       # Thursday
ANOMALY_CONTRADICTORY = ("EMP012", date(2026, 1, 20))    # Tuesday
ANOMALY_DUPLICATE = ("EMP003", date(2026, 1, 12))        # Monday
ANOMALY_IMPLAUSIBLE = ("EMP015", date(2026, 2, 2))       # Monday, worked = 18h
ANOMALY_OVERTIME_START = ("EMP020", date(2026, 1, 26))   # Monday; spans Mon-Fri

OUTPUT_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "sample_data"
    / "attendance_sample.csv"
)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _employee_id(n: int) -> str:
    return f"EMP{n:03d}"


def _base_rows(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    all_dates = [START_DATE + timedelta(days=i) for i in range(WEEKS * 7)]
    for emp_num in range(1, NUM_EMPLOYEES + 1):
        emp_id = _employee_id(emp_num)
        for d in all_dates:
            weekday = d.weekday()  # Mon=0 .. Sun=6
            if weekday >= 5:
                # Weekend: unscheduled.
                rows.append(
                    {
                        "employee_id": emp_id,
                        "date": d.isoformat(),
                        "scheduled_hours": 0,
                        "worked_hours": 0,
                        "leave_status": "",
                        "notes": "",
                    }
                )
                continue
            # Weekday: either leave or normal work with small variance.
            if rng.random() < LEAVE_PROBABILITY:
                rows.append(
                    {
                        "employee_id": emp_id,
                        "date": d.isoformat(),
                        "scheduled_hours": 8,
                        "worked_hours": 0,
                        "leave_status": rng.choice(["sick", "vacation"]),
                        "notes": "",
                    }
                )
            else:
                worked = round(
                    rng.uniform(WORKED_HOURS_MIN, WORKED_HOURS_MAX), 1
                )
                rows.append(
                    {
                        "employee_id": emp_id,
                        "date": d.isoformat(),
                        "scheduled_hours": 8,
                        "worked_hours": worked,
                        "leave_status": "",
                        "notes": "",
                    }
                )
    return rows


def _row_index(df: pd.DataFrame, emp_id: str, d: date) -> int:
    mask = (df["employee_id"] == emp_id) & (df["date"] == d.isoformat())
    matches = df.index[mask]
    if len(matches) == 0:
        raise RuntimeError(f"no base row for {emp_id} on {d}")
    if len(matches) > 1:
        raise RuntimeError(f"unexpected multiple base rows for {emp_id} on {d}")
    return int(matches[0])


def _inject_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    # 1. UNRECORDED_ATTENDANCE: scheduled day, zero worked, no leave.
    emp, d = ANOMALY_UNRECORDED
    i = _row_index(df, emp, d)
    df.loc[i, "scheduled_hours"] = 8
    df.loc[i, "worked_hours"] = 0
    df.loc[i, "leave_status"] = ""
    df.loc[i, "notes"] = "injected UNRECORDED_ATTENDANCE"

    # 2. CONTRADICTORY_LEAVE: leave entry plus a full worked day.
    emp, d = ANOMALY_CONTRADICTORY
    i = _row_index(df, emp, d)
    df.loc[i, "scheduled_hours"] = 8
    df.loc[i, "worked_hours"] = 8
    df.loc[i, "leave_status"] = "sick"
    df.loc[i, "notes"] = "injected CONTRADICTORY_LEAVE"

    # 3. IMPLAUSIBLE_HOURS: 18 worked hours (schema valid; above default
    #    max_plausible_hours = 16).
    emp, d = ANOMALY_IMPLAUSIBLE
    i = _row_index(df, emp, d)
    df.loc[i, "worked_hours"] = 18
    df.loc[i, "notes"] = "injected IMPLAUSIBLE_HOURS"

    # 4. SUSTAINED_OVERTIME: 5 consecutive weekdays with worked - scheduled
    #    = 3h (>= overtime_margin = 2h and >= overtime_streak = 5).
    emp, start = ANOMALY_OVERTIME_START
    if start.weekday() != 0:
        raise RuntimeError(
            f"SUSTAINED_OVERTIME start {start} must be a Monday."
        )
    for offset in range(5):
        d = start + timedelta(days=offset)
        i = _row_index(df, emp, d)
        df.loc[i, "scheduled_hours"] = 8
        df.loc[i, "worked_hours"] = 11
        df.loc[i, "leave_status"] = ""
        df.loc[i, "notes"] = (
            f"injected SUSTAINED_OVERTIME day {offset + 1} of 5"
        )

    # 5. DUPLICATE_RECORD: insert a second row for the same (employee, date).
    #    Normalize the first row to a clean workday first, so the duplicate
    #    cannot accidentally trip CONTRADICTORY_LEAVE if the originally
    #    sampled day happened to be a leave day.
    emp, d = ANOMALY_DUPLICATE
    i = _row_index(df, emp, d)
    df.loc[i, "scheduled_hours"] = 8
    df.loc[i, "worked_hours"] = 8.0
    df.loc[i, "leave_status"] = ""
    df.loc[i, "notes"] = "injected DUPLICATE_RECORD first row for same date"
    duplicate = df.loc[i].copy()
    duplicate["worked_hours"] = 7.5
    duplicate["notes"] = "injected DUPLICATE_RECORD second row for same date"
    df = pd.concat(
        [df.iloc[: i + 1], pd.DataFrame([duplicate]), df.iloc[i + 1 :]],
        ignore_index=True,
    )
    return df


def generate() -> pd.DataFrame:
    if START_DATE.weekday() != 0:
        raise RuntimeError("START_DATE must be a Monday.")
    rng = random.Random(SEED)
    df = pd.DataFrame(_base_rows(rng))
    df = _inject_anomalies(df)
    return df


def main() -> None:
    df = generate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Force ISO 8601 dates regardless of whether pandas inferred the column
    # as datetime at some step in the pipeline; the schema validator only
    # accepts YYYY-MM-DD.
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")
    print("Injected anomalies (verify after running detectors):")
    print(f"  UNRECORDED_ATTENDANCE : {ANOMALY_UNRECORDED[0]} on {ANOMALY_UNRECORDED[1]}")
    print(f"  CONTRADICTORY_LEAVE   : {ANOMALY_CONTRADICTORY[0]} on {ANOMALY_CONTRADICTORY[1]}")
    print(f"  DUPLICATE_RECORD      : {ANOMALY_DUPLICATE[0]} on {ANOMALY_DUPLICATE[1]} (now 2 rows)")
    print(f"  IMPLAUSIBLE_HOURS     : {ANOMALY_IMPLAUSIBLE[0]} on {ANOMALY_IMPLAUSIBLE[1]} (worked = 18)")
    print(
        f"  SUSTAINED_OVERTIME    : {ANOMALY_OVERTIME_START[0]} "
        f"Mon-Fri starting {ANOMALY_OVERTIME_START[1]} (worked = 11)"
    )


if __name__ == "__main__":
    main()
