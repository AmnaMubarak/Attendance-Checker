# Daily log

Project days vs calendar days. The headings below are *project* days,
and project work was front-loaded. Day 1 and Day 2 landed on separate
calendar days (Thu 2026-10-15 and Fri 2026-10-16). Day 3, Day 4 and
Day 5 were compressed into a single calendar day (Mon 2026-10-19)
because I missed the weekend. Day 6 is today (Tue 2026-10-20) and
covers submission prep and recording. The brief said "A short log for
each of the 5 days" of project work; this file keeps that promise and
adds the compression note here for honesty.

## Day 1 (Thu 2026-10-15)

* Read and ratified the design: minimal CSV schema, five anomaly codes,
  neutral one-sentence explanations, five-day plan.
* Renamed `intend.md` -> `intent.md` and `daily-log.md` -> `daily_log.md`
  for consistency.
* Pinned the ambiguity points: `max_gap_days = 10` with strict
  greater-than break; half-day leave as a documented v1 limitation;
  weekly caps deferred; leave on unscheduled days is valid; unusual
  dates warn only.
* Built the first module: `attendance_checker/schema.py` with
  `ValidationIssue`, `SchemaValidationError`, `ValidationResult`,
  `read_csv`, `validate`, `validate_csv`. Validation collects every
  error before raising; original input is deep-copied, never mutated.
* Built `attendance_checker/config.py` with the `DetectionConfig`
  frozen dataclass and defensive `__post_init__` validation.
* Created the fixtures: `clean_minimal.csv`, seven files in
  `tests/fixtures/malformed/`, and seven in `tests/fixtures/edge/`
  including the leave-on-unscheduled-day and high-but-valid-hours
  cases I need for later detectors.
* Wrote `tests/test_schema.py` (21 tests) and `tests/test_config.py`
  (15 tests). All 36 passed.

## Day 2 (Fri 2026-10-16)

* Implemented three detectors in `attendance_checker/detectors.py`:
  `detect_unrecorded_attendance`, `detect_contradictory_leave`,
  `detect_duplicate_record`. Shared `FLAG_COLUMNS` contract and
  `_build_flags` helper for consistent output.
* Pinned every reason string as a module-level constant so tests can
  compare against them directly.
* Added fixtures: `unrecorded_attendance.csv`,
  `contradictory_leave.csv`, `half_day_partial_work.csv`,
  `duplicates.csv`.
* Wrote `tests/test_detectors.py` (22 tests at this point). Verified
  that approved leave with zero hours is NOT flagged, that duplicates
  are flagged non-destructively with group size in the reason, and
  that no reason string contains the words
  `{absent, absence, misconduct, fraud, fraudulent}`.
* First `pytest` run was red (12 failures): my fixtures had commas
  inside the `notes` column, which pandas was treating as extra
  fields. Rewrote the four fixtures to use " - " instead of commas.
  58/58 passed on the second run.

## Day 2.5 (sample dataset, Fri 2026-10-16)

* The test fixtures proved specific detector behaviors but there was
  no realistic bulk dataset for the UI to demo on. Built
  `scripts/generate_sample_data.py` with a fixed seed: 25 fictional
  employees x 8 weeks (1400 base rows plus 1 injected duplicate =
  1401\), weekdays scheduled at 8h with small variance, 5% random
  leave, and one deliberate injection of each anomaly at pinned
  coordinates (listed at the top of the script).
* First run surfaced a bug: the row the generator picked for the
  DUPLICATE\_RECORD injection happened to be a random leave day, and
  bumping worked\_hours on the duplicate accidentally triggered a
  secondary CONTRADICTORY\_LEAVE. Fixed by normalizing the duplicate
  target to a clean workday before copying.
* Verified end-to-end: the three Day 2 detectors catch exactly the
  injected rows, no more, no less.

## Day 3 (Mon 2026-10-19)

* Added the remaining two detectors: `detect_implausible_hours`
  (strict `>` comparison against `max_plausible_hours`) and
  `detect_sustained_overtime` with the full streak definition
  decided on Day 1 (scheduled-workday sequence, over-variance,
  leave / unscheduled / missing days skipped, calendar gap >
  `max_gap_days` breaks).
* Added `attendance_checker/pipeline.py` with `AnalysisResult`,
  `analyze`, and `analyze_csv`. The pipeline runs all five detectors
  in a fixed order, concatenates flags sorted by
  `(source_row_index, anomaly_code)`, and builds a summary dict
  containing all five codes even when counts are zero.
* Added fixtures: `implausible_hours.csv` (boundary coverage at the
  default 16h threshold), `overtime_boundary.csv` (streak length,
  leave-doesn't-break, gap > 10 splits, gap = 10 does not split),
  `one_of_each.csv` (golden end-to-end), plus `edge/only_leave.csv`
  and `edge/only_unscheduled.csv`.
* Extended `test_detectors.py` with per-detector tests for the two
  new detectors, parametrized the shared contract tests
  (empty-input, immutability, no-flags-on-clean) across all five
  detectors, and added the two new fixtures to the neutrality
  check.
* Added `tests/test_pipeline.py` and `tests/test_edge_cases.py`.
* One test failed on the first run: the sample dataset CSV had
  non-ISO dates like `05/01/2026` because pandas inferred the date
  column as datetime at some step and `to_csv` serialized it with
  the Windows locale. Fixed by forcing
  `df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")`
  before writing. Regenerated the sample.
* Full suite: 91 passed.

## Day 4 (Mon 2026-10-19)

* Built `attendance_checker/app.py`: Streamlit page with sidebar
  thresholds for every `DetectionConfig` field (including
  checkbox-to-disable `max_gap_days`), a two-way data-source choice
  (upload or bundled sample), summary metrics for all five codes
  plus total rows, a warnings expander, a filterable flags table
  with CSV download, and a view of the validated input.
* On schema failure the UI shows the full error table and stops
  (never runs detection on partial data).
* Byte-compiled the app for a quick syntax sanity check.

## Day 5 (Mon 2026-10-19)

* Wrote `README.md`: install, run, schema, error / warning codes,
  anomaly reference, `SUSTAINED_OVERTIME` streak rules, config,
  known limitations, testing, sample data, project layout.
* Backfilled this `daily_log.md`.
* Final `pytest` run: 91 passed. Nothing committed to Git.
* Follow-up fix after reported `ModuleNotFoundError: No module named
  'attendance_checker'` when launching the Streamlit UI. Root cause:
  `streamlit run attendance_checker/app.py` puts the script's own
  folder on `sys.path` but not the project root, and Streamlit does
  not read `conftest.py`. Added a 6-line `sys.path` bootstrap at the
  top of `attendance_checker/app.py` that inserts the project root
  before the `from attendance_checker import ...` line. No-op when
  the package is ever installed normally.
* Verified by actually launching Streamlit this time (headless on
  port 8599). Startup banner printed and an HTTP GET returned 200
  with no traceback. Server stopped afterwards.

## Day 6 - submission prep (Tue 2026-10-20)

* Added `Final directive.md` (the frozen spec after Day 1's two
  review rounds) and `unlearned.md` (one-page first-person
  reflection) because the submission form asks for both as separate
  deliverables.
* Wrote `raising-the-load.md` to make the "Raising the load (20%)"
  rubric item easy to score: scoreboard table at the top, 8
  harder-vs-easier choices, 4 honest failures, 6 PowerShell
  commands a reviewer can paste to prove any claim in 60 seconds,
  and a §4 "Where I did NOT raise the load" to call out my own
  ceiling (no pyproject.toml, no CI, no mypy gate, not stress-
  tested on large data).
* Cleaned up dead code: removed project-local `__pycache__` and
  `.pytest_cache`, and dropped one unused `Iterable` import in
  `schema.py`. Verified 91 tests still passing after cleanup.
* Built `attendance-checker-submission.zip` (60.5 KB, 46 files,
  caches excluded) ready to upload under the "Working code" slot.
* Plan for the rest of today: record the 5-minute demo video,
  record the Loom process video, personalize `unlearned.md` so the
  voice is mine, and submit on the Match Hire form.
* Nothing committed to Git yet.
