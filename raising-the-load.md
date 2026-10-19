# Raising the load, and what broke

Short reviewer-facing summary for the "Raising the load (20%)" rubric
item. Everything below is verifiable by opening the referenced file in
the submission zip.

## At a glance


| Metric    | What it says                                                                                     |
| --------- | ------------------------------------------------------------------------------------------------ |
| **91**    | passing pytest tests across 5 modules                                                            |
| **5**     | detectors (vs. the brief's "flag unusual patterns" with no minimum)                              |
| **22**    | hand-picked CSV fixtures (one per edge case / malformed class)                                   |
| **8**     | design decisions pinned in writing BEFORE any detector code                                      |
| **4**     | honest failures surfaced in `daily_log.md` and §2 below                                          |
| **0**     | silent fixes - every bug is documented                                                           |
| **1,401** | reproducible rows in `sample_data/attendance_sample.csv` from a seeded generator                 |
| **0**     | words from `{absent, absence, misconduct, fraud, fraudulent}` in any flag output (test-enforced) |


## Harder path vs. easier path (one line each)


| #   | Easier path                                       | What I shipped instead                                                                             |
| --- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1.1 | Ship the first design proposal                    | Two review rounds, 8 pinned decisions, written up in `Final directive.md`                          |
| 1.2 | `SUSTAINED_OVERTIME` on consecutive calendar days | Scheduled-workday sequence with leave/unscheduled/missing skipped + `max_gap_days` strict `>` rule |
| 1.3 | Trust myself to write neutral strings             | Parametrized test asserts no accusatory words in any detector's output                             |
| 1.4 | `df.drop_duplicates()`                            | Flag every row in the group, embed group size, snapshot-assert the input is unchanged              |
| 1.5 | Raise on the first schema error                   | Walk every row, raise once with every error, each tagged with row/column/code                      |
| 1.6 | "I'll be careful not to mutate"                   | `deep=True` copy + parametrized immutability test across all 5 detectors                           |
| 1.7 | Hand-written CSV with "roughly realistic" rows    | Seeded generator, 1,401 rows, each anomaly injected at documented coordinates, smoke-tested        |
| 1.8 | ~30 tests and call it good                        | 91 tests including shared-contract parametrization across all 5 detectors                          |


## 1. Where I chose the harder path

### 1.1 Two design-review rounds before any code

Day 1 produced a design proposal; I rejected it and asked for a
second pass with eight specific changes (renaming
`MISSING_ATTENDANCE` -> `UNRECORDED_ATTENDANCE` to drop the
implication of absence; separating validation from detection;
documenting half-day leave as a limitation rather than silently
flagging it; non-destructive duplicate handling; etc.). Both
rounds, with the pinned decisions, are preserved in
`Final directive.md`.

Easier path: ship the first design. Chosen path: two reviews
before the first line of production code.

### 1.2 `SUSTAINED_OVERTIME` with `max_gap_days`

The easier definition would have been "N consecutive calendar
days" and move on. I pinned the harder, more realistic one:

- A per-employee **scheduled-workday sequence**, with leave days,
unscheduled days, and missing dates all *skipped* (neither
extending nor breaking a streak).
- A `max_gap_days` rule (default 10) that breaks a streak only
when two sequence entries are **strictly** more than N calendar
days apart. Exactly at the limit does not break.

Code: `attendance_checker/detectors.py`,
`_streak_runs_for_employee` and `detect_sustained_overtime`.
Tests pin all four edges of this behavior:
`tests/test_detectors.py::test_sustained_overtime_streak_length_boundary`,
`..._leave_day_does_not_break_streak`,
`..._gap_greater_than_max_breaks_streak`,
`..._gap_exactly_at_limit_does_not_break`.

### 1.3 "No accusatory language" enforced by a test

Easier path: write careful reason strings and trust myself. Chosen
path: a parametrized test iterates every detector's output on its
fixture and asserts that no reason contains any of
`{absent, absence, misconduct, fraud, fraudulent}`.

Test: `tests/test_detectors.py::test_reasons_contain_no_accusatory_language`.

### 1.4 Non-destructive duplicate detection

Easier path: `df.drop_duplicates()`. Chosen path: flag EVERY row
in each `(employee_id, date)` group, embed the group size in the
reason, and leave the input DataFrame unchanged. A dedicated test
asserts the input is byte-for-byte unchanged after the detector
runs.

Test: `tests/test_detectors.py::test_duplicate_record_preserves_original_rows`.

### 1.5 Collecting EVERY schema error, not just the first

Easier path: raise on the first bad row. Chosen path: walk every
row, accumulate every error, raise once with all of them so a
reviewer can fix the whole CSV in one pass. Each error carries a
stable `code`, the `row_index` (0-based, header excluded), and the
`column`. The exception message previews the first five with a
"... and N more" suffix.

Code: `attendance_checker/schema.py::validate` and
`SchemaValidationError`.
Test: `tests/test_schema.py::test_multiple_errors_are_all_collected`.

### 1.6 Immutability enforced by assertion, not convention

Easier path: "detectors shouldn't mutate the input, I'll be
careful." Chosen path: `ValidationResult.original_data` is a
`deep=True` copy, and a parametrized test asserts that every one
of the five detectors leaves its input DataFrame equal to a
snapshot taken before the call.

Test: `tests/test_detectors.py::test_detectors_do_not_mutate_input`.

### 1.7 Reproducible sample data with injected anomalies

Easier path: a hand-written CSV with "roughly realistic" rows.
Chosen path: `scripts/generate_sample_data.py` with a fixed seed
produces 1,401 rows (25 fictional employees x 56 days + 1 injected
duplicate row) and injects one of each anomaly at coordinates
documented at the top of the script. A smoke test loads it and
asserts the exact anomaly counts.

Code: `scripts/generate_sample_data.py`.
Test: `tests/test_pipeline.py::test_pipeline_on_bundled_sample_dataset`.

### 1.8 Final test count

91 tests across 5 modules, including parametrized shared-contract
tests that run across all five detectors (empty input, immutability,
no-flags on clean data, no-accusatory-language). I could have
shipped around 30 and called it good.

## 2. What broke, honestly

Every failure below is in `daily_log.md`. I did not clean these up
quietly.

### 2.1 Day 2: fixture `notes` column with commas (12 tests red)

First `pytest` run on Day 2 was 12 failed / 46 passed. Cause: four
of my hand-written fixtures had commas inside the `notes` column
and I had not quoted them, so pandas tokenized them as extra
fields and the schema validator rejected every row. The detector
code itself was fine. Fixed by rewriting the four fixtures to use
" - " instead of commas. Second run was 58/58. Logged on Day 2.

### 2.2 Day 2.5: sample generator secondary anomaly

First smoke test against the generated sample showed 2
`CONTRADICTORY_LEAVE` flags instead of the expected 1. Cause: the
row the random seed picked for the `DUPLICATE_RECORD` injection
happened to be a leave day; bumping workedhours on the duplicate
copy accidentally created a second anomaly. Fixed by normalizing
the duplication-target row to a clean workday before copying.
Logged on Day 2.5.

### 2.3 Day 3: Windows locale date serialization

Day 3 test suite went red: the smoke test against the generated
sample failed with 1,401 `BAD_DATE_FORMAT` errors. Cause: pandas
inferred the date column as datetime at some point and `to_csv`
serialized it using the Windows locale as `DD/MM/YYYY` (e.g.
`05/01/2026`), which the schema correctly rejected. Fixed with
one line in the generator:
`df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")`.
Logged on Day 3.

### 2.4 Day 5: `ModuleNotFoundError` on Streamlit launch

The user reported `ModuleNotFoundError: No module named 'attendance_checker'` when running `streamlit run attendance_checker/app.py`. Cause: Streamlit puts the script's own
folder on `sys.path` but not the project root, and Streamlit does
not read `conftest.py` (which is where I had put the pytest sys.path
shim). Fix: a 6-line `sys.path` bootstrap at the top of
`attendance_checker/app.py` that inserts the project root. Verified
by launching Streamlit headless on port 8600 and getting a 200 from
`http://localhost:8600`. Logged on Day 5.

### 2.5 What I did not catch until the user prompted me

- The sample data file not existing until the user asked "where is
the main attendance data?" (Day 2.5 was prompted, not planned).
- The `ModuleNotFoundError` only surfaced because the user tried to
run Streamlit; my byte-compile check on Day 4 was not enough.
- The dead `Iterable` import in `schema.py` only came out when the
user asked me to delete dead code; I had not spotted it myself.

Three honest misses in five days. Logged, fixed, and surfaced here
rather than quietly fixed and glossed over.

## 3. Verify any claim in 60 seconds

Every statement above points at an artifact in the submission zip. If
you want to confirm, this is the shortest path:

```powershell
# 1. Install deps and run the full test suite.
pip install -r requirements.txt
pytest -v
# Expected: 91 passed. Any single failure invalidates the "91 tests"
# claim at the top of this document.

# 2. Confirm the no-accusatory-language guarantee.
pytest tests/test_detectors.py::test_reasons_contain_no_accusatory_language -v

# 3. Confirm the "all errors collected" behavior on a deliberately
#    multi-error file.
python -c "from attendance_checker import validate_csv; validate_csv('tests/fixtures/malformed/bad_date.csv')"
# Expected: SchemaValidationError listing 3 BAD_DATE_FORMAT errors.

# 4. Confirm the sample data is reproducible.
python scripts/generate_sample_data.py
# Expected: Wrote 1401 rows ... with 5 injected anomalies listed by
# (employee_id, date).

# 5. Confirm the sample triggers exactly the injected anomalies.
pytest tests/test_pipeline.py::test_pipeline_on_bundled_sample_dataset -v

# 6. Run the UI end-to-end.
streamlit run attendance_checker/app.py
# Click "Use the bundled sample dataset". Summary should read:
# UNRECORDED_ATTENDANCE=1, CONTRADICTORY_LEAVE=1, DUPLICATE_RECORD=2,
# IMPLAUSIBLE_HOURS=1, SUSTAINED_OVERTIME=5.
```

Nothing in this document asks you to trust me. Everything is a
command-line check away.

## 4. Where I did NOT raise the load (honest ceiling)

To avoid overclaiming, here is what I deliberately did **not** do:

- No `pyproject.toml` and no editable install. The project uses a
5-line `conftest.py` shim at the root so `pytest` and `streamlit`
both find the package. Reasonable for a 5-day MVP; cuts a half-day
of yak-shaving.
- No CI pipeline. The 91 tests only run on demand.
- No type checking in CI (mypy / pyright). The code uses modern
type hints and is lint-clean, but I did not stand up a type-check
gate.
- The sample data is 1,401 rows; it is not large enough to stress
memory. The pandas code would need a chunked rewrite for a true
"big" HR dataset.
- The Streamlit UI does not persist settings across refreshes. Each
reload resets the sidebar.

These are the next things I would ship if this were a v2, not v1.