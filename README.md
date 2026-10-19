# Attendance Checker

A small, deterministic Python tool that reads a CSV of attendance and
leave records, flags unusual patterns, and explains every flag in one
neutral sentence.

Built in five days as a focused MVP:

* Strict schema validation before any detection runs.
* Five deterministic anomaly detectors with configurable thresholds.
* Streamlit UI with an upload, a sidebar for thresholds, a summary, a
  filterable flags table, and a CSV download.
* 91 pytest tests covering schema, each detector, the pipeline, and
  edge cases.

**Design principle:** every flag means a *record* needs review. No
detector labels an employee, implies absence, or alleges misconduct.
Reason strings end in `"record needs review"` or `"records need review"`.

## Install

Python 3.8+ with the three dependencies in `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the Streamlit UI

```powershell
streamlit run attendance_checker/app.py
```

The sidebar exposes every tunable threshold. Pick "Use the bundled sample
dataset" on first run to see all five anomalies fire.

## Programmatic use

```python
from attendance_checker import DetectionConfig, analyze_csv

result = analyze_csv("sample_data/attendance_sample.csv")
print(result.summary)
# {'UNRECORDED_ATTENDANCE': 1, 'CONTRADICTORY_LEAVE': 1,
#  'DUPLICATE_RECORD': 2, 'IMPLAUSIBLE_HOURS': 1, 'SUSTAINED_OVERTIME': 5}

print(result.flags.head())
# source_row_index employee_id       date        anomaly_code  reason
# ...
```

`result.data` is the validated DataFrame; `result.original_data` is a
bitwise copy of the input; `result.flags` is a new DataFrame.
`analyze` never mutates its input.

## CSV schema

One row per `(employee_id, date)`.

| Column | Type | Required | Notes |
|---|---|---|---|
| `employee_id` | string | yes | Non-empty, trimmed. |
| `date` | ISO 8601 (`YYYY-MM-DD`) | yes | One timezone per file. |
| `scheduled_hours` | float in `[0, 24]` | yes | `0` means not scheduled (weekend / holiday). |
| `worked_hours` | float in `[0, 24]` | yes | `0` on a scheduled day with no leave triggers `UNRECORDED_ATTENDANCE`. |
| `leave_status` | enum, nullable | no | Case-insensitive. One of `sick, vacation, unpaid, bereavement, other`. Empty = no leave. |
| `notes` | string | no | Free text, ignored by detection. |

### Validation errors

Validation collects **every** error before raising, each with a stable
code, the 0-based row index, the column name, and an actionable message:

| Error code | Meaning |
|---|---|
| `MISSING_REQUIRED_COLUMNS` | A required column is absent from the header. |
| `BAD_DATE_FORMAT` | `date` is not strict `YYYY-MM-DD`. |
| `NON_NUMERIC_HOURS` | An hours cell is empty or not a number. |
| `NEGATIVE_HOURS` | An hours cell is below 0. |
| `HOURS_OUT_OF_RANGE` | An hours cell is above 24. |
| `UNKNOWN_LEAVE_STATUS` | `leave_status` value is outside the allowed enum. |
| `EMPTY_EMPLOYEE_ID` | `employee_id` cell is empty or whitespace-only. |

### Warnings (never fail validation)

| Warning code | Meaning |
|---|---|
| `UNUSUAL_DATE` | `date` is before 2000 or in the future; review if intentional. |

## Anomaly reference

| Code | Trigger | Default threshold | Reason template |
|---|---|---|---|
| `UNRECORDED_ATTENDANCE` | `scheduled_hours > 0` AND `worked_hours == 0` AND `leave_status` empty | n/a | "Scheduled day has zero recorded work hours and no leave entry; record needs review." |
| `CONTRADICTORY_LEAVE` | `leave_status` set AND `worked_hours > 0` | n/a | "Leave status is set but worked hours are greater than zero; record needs review." |
| `DUPLICATE_RECORD` | `(employee_id, date)` group size > 1 - all rows flagged | n/a | "Employee has more than one row for this date (group size N); records need review." |
| `IMPLAUSIBLE_HOURS` | `worked_hours > max_plausible_hours` | 16h | "Worked hours (H) exceed the configured plausible maximum (MAX); record needs review." |
| `SUSTAINED_OVERTIME` | Streak definition below | margin 2h, length 5, gap 10 | "Day is part of a N-workday streak where worked hours exceeded scheduled by at least MARGINh; schedule needs review." |

### `SUSTAINED_OVERTIME` streak definition

Per employee, build the **scheduled-workday sequence**: rows where
`scheduled_hours > 0` AND `leave_status` is empty. Sort by date
ascending. Within this sequence, a day is **over** when
`worked_hours - scheduled_hours >= overtime_margin`. A **streak** is a
maximal run of consecutive **over** entries in the sequence. The
detector flags every row inside any streak whose length is at least
`overtime_streak`.

Effect of each situation on a streak:

| Situation | In the sequence? | Effect |
|---|---|---|
| Scheduled over-variance day | yes | extends |
| Scheduled under-threshold day | yes | breaks |
| Unscheduled day (`scheduled_hours == 0`) | no | neither extends nor breaks |
| Leave day (`leave_status` set) | no | neither extends nor breaks |
| Missing date (no row at all) | no | neither extends nor breaks |

If `max_gap_days` is set (default `10`), two consecutive entries in the
sequence that are more than that many **calendar** days apart break
the streak. Exactly `max_gap_days` apart does **not** break (strict
greater-than). Set `max_gap_days=None` to disable gap-breaking.

## Configuration (`DetectionConfig`)

| Field | Default | Range | Meaning |
|---|---|---|---|
| `max_plausible_hours` | `16.0` | `(0, 24]` | Upper bound of plausible worked hours per day. |
| `overtime_margin` | `2.0` | `>= 0` | Minimum `worked - scheduled` to count as an "over" day. |
| `overtime_streak` | `5` | `>= 1` | Minimum streak length to flag. |
| `max_gap_days` | `10` | `>= 1` or `None` | Calendar-day gap that breaks a streak; `None` disables. |

Invalid values raise `ValueError` at construction time.

## Known limitations

* **Half-day leave.** The schema has no half-day field. A row with
  `leave_status = sick` and `worked_hours = 4` will fire
  `CONTRADICTORY_LEAVE`. Document half-days in `notes` for now; a
  dedicated field is a plausible v2 addition.
* **Split shifts.** The schema expects one aggregated row per
  `(employee_id, date)`. Legitimate split-shift records stored as two
  rows per day will fire `DUPLICATE_RECORD`. Aggregate upstream.
* **Timezones.** Dates are naive calendar dates. The whole file is
  assumed to be one timezone.
* **Holidays.** Not modeled explicitly. Use `scheduled_hours = 0`
  for holidays so they do not trigger `UNRECORDED_ATTENDANCE`.
* **Weekly caps.** The tool has no "worked > 60h per week" detector.
  Explicitly deferred from the first release.
* **Date sanity.** Dates before 2000 or in the future warn but never
  fail validation; a reviewer may legitimately be auditing historical
  data.

## Testing

```powershell
pytest
```

Expected: **91 passed**. Breakdown:

* `tests/test_config.py` - 15 tests for `DetectionConfig` validation.
* `tests/test_schema.py` - 21 tests for the schema validator.
* `tests/test_detectors.py` - 40 tests covering each detector plus
  shared contract tests (empty input, immutability, no-flags on clean
  data, no accusatory language in reasons).
* `tests/test_pipeline.py` - 8 end-to-end tests, including the bundled
  sample dataset.
* `tests/test_edge_cases.py` - 7 edge-case tests (empty, single row,
  only leave, only unscheduled, etc.).

Test fixtures live in `tests/fixtures/`. Each malformed-case CSV in
`tests/fixtures/malformed/` exercises one validator rejection class;
each file in `tests/fixtures/edge/` exercises one edge case; the
root-level fixtures (`clean_minimal.csv`, `unrecorded_attendance.csv`,
etc.) target individual detectors.

## Sample data

`sample_data/attendance_sample.csv` is a reproducible, fictional
25-employee x 8-week dataset. Regenerate with:

```powershell
python scripts/generate_sample_data.py
```

The script is seeded, so the output is byte-identical across runs. The
docstring at the top of `scripts/generate_sample_data.py` lists the
exact `(employee_id, date)` coordinates where each anomaly was
injected.

## Project layout

```
attendance_checker/
  __init__.py       # public exports
  config.py         # DetectionConfig dataclass
  schema.py         # validator, ValidationIssue, ValidationResult
  detectors.py      # the five detectors and the FLAG_COLUMNS contract
  pipeline.py       # analyze() + analyze_csv() + AnalysisResult
  app.py            # Streamlit UI
scripts/
  generate_sample_data.py
sample_data/
  attendance_sample.csv
tests/
  conftest.py
  test_config.py
  test_schema.py
  test_detectors.py
  test_pipeline.py
  test_edge_cases.py
  fixtures/
    clean_minimal.csv
    unrecorded_attendance.csv
    contradictory_leave.csv
    half_day_partial_work.csv
    duplicates.csv
    implausible_hours.csv
    overtime_boundary.csv
    one_of_each.csv
    edge/             # 7 edge-case CSVs
    malformed/        # 7 schema-rejection CSVs
conftest.py           # adds project root to sys.path for pytest
intent.md             # project intent document
daily_log.md          # per-day work notes
requirements.txt
README.md
```
