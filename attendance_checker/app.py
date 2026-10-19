"""Streamlit UI for the Attendance Checker.

Run from the project root with::

    streamlit run attendance_checker/app.py

The app wraps :func:`attendance_checker.pipeline.analyze_csv` and never
mutates the uploaded data. All five anomaly thresholds live in the sidebar
so a reviewer can tune them live.
"""

from __future__ import annotations

# --- sys.path bootstrap ----------------------------------------------------
# ``streamlit run attendance_checker/app.py`` puts the script's own folder
# on sys.path but NOT the project root, so ``from attendance_checker import
# ...`` would fail. Insert the project root up front. This has no effect
# when the package is installed normally.
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
# ---------------------------------------------------------------------------

import pandas as pd
import streamlit as st

from attendance_checker import (
    ANOMALY_CODES,
    DetectionConfig,
    SchemaValidationError,
    analyze_csv,
)


SAMPLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "sample_data"
    / "attendance_sample.csv"
)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Attendance Checker", layout="wide")
st.title("Attendance Checker")
st.caption(
    "Flags unusual patterns in attendance and leave records. "
    "Every flag means a record needs review - never that an employee did "
    "something wrong."
)


# ---------------------------------------------------------------------------
# Sidebar: detection thresholds
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Detection thresholds")
    st.caption("Changes apply immediately.")

    max_plausible_hours = st.slider(
        "IMPLAUSIBLE_HOURS: maximum plausible worked hours per day",
        min_value=1.0,
        max_value=24.0,
        value=16.0,
        step=0.5,
    )
    overtime_margin = st.slider(
        "SUSTAINED_OVERTIME: hours above scheduled to count as 'over'",
        min_value=0.0,
        max_value=8.0,
        value=2.0,
        step=0.25,
    )
    overtime_streak = st.slider(
        "SUSTAINED_OVERTIME: minimum streak length (workdays)",
        min_value=2,
        max_value=15,
        value=5,
        step=1,
    )
    gap_enabled = st.checkbox(
        "Break overtime streak on large calendar gap",
        value=True,
        help=(
            "When enabled, two entries in an employee's scheduled-workday "
            "sequence that are more than the configured number of calendar "
            "days apart will break the streak. Exactly at the limit does "
            "not break."
        ),
    )
    max_gap_days = (
        st.slider(
            "Gap threshold (calendar days)",
            min_value=1,
            max_value=60,
            value=10,
            step=1,
        )
        if gap_enabled
        else None
    )

    try:
        cfg = DetectionConfig(
            max_plausible_hours=max_plausible_hours,
            overtime_margin=overtime_margin,
            overtime_streak=overtime_streak,
            max_gap_days=max_gap_days,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()


# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------

st.subheader("1. Choose a data source")
source_choice = st.radio(
    "Data source",
    ("Upload a CSV", "Use the bundled sample dataset"),
    horizontal=True,
    label_visibility="collapsed",
)

source = None
if source_choice == "Upload a CSV":
    uploaded = st.file_uploader(
        "Attendance CSV",
        type=["csv"],
        help=(
            "Columns: employee_id, date (YYYY-MM-DD), scheduled_hours, "
            "worked_hours, leave_status (optional), notes (optional)."
        ),
    )
    if uploaded is not None:
        source = uploaded
else:
    if SAMPLE_PATH.exists():
        source = SAMPLE_PATH
        st.info(
            f"Using {SAMPLE_PATH.name} - 25 fictional employees over 8 "
            "weeks, with one deliberate instance of each anomaly."
        )
    else:
        st.warning(
            "Sample dataset not found. Run "
            "`python scripts/generate_sample_data.py` first."
        )

if source is None:
    st.stop()


# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

try:
    result = analyze_csv(source, config=cfg)
except SchemaValidationError as exc:
    st.subheader("Schema validation failed")
    st.error(
        f"{len(exc.errors)} error(s) found. Fix these in the CSV and try "
        "again. No detection was run."
    )
    err_df = pd.DataFrame(
        [
            {
                "code": err.code,
                "row (0-based)": err.row_index,
                "column": err.column,
                "message": err.message,
            }
            for err in exc.errors
        ]
    )
    st.dataframe(err_df, use_container_width=True)
    st.stop()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

st.subheader("2. Summary")
summary_cols = st.columns(len(ANOMALY_CODES) + 1)
summary_cols[0].metric("Total rows", len(result.data))
for col, code in zip(summary_cols[1:], ANOMALY_CODES):
    col.metric(code, result.summary.get(code, 0))

if result.warnings:
    with st.expander(f"{len(result.warnings)} validation warning(s)"):
        warn_df = pd.DataFrame(
            [
                {
                    "code": w.code,
                    "row (0-based)": w.row_index,
                    "column": w.column,
                    "message": w.message,
                }
                for w in result.warnings
            ]
        )
        st.dataframe(warn_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

st.subheader("3. Flagged records")

if result.flags.empty:
    st.success(
        "No anomalies detected in this dataset with the current thresholds."
    )
else:
    selected_codes = st.multiselect(
        "Filter by anomaly code",
        options=list(ANOMALY_CODES),
        default=list(ANOMALY_CODES),
    )
    filtered = result.flags[result.flags["anomaly_code"].isin(selected_codes)]
    display = filtered.copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.download_button(
        "Download flags as CSV",
        data=filtered.assign(
            date=filtered["date"].dt.strftime("%Y-%m-%d")
        ).to_csv(index=False).encode("utf-8"),
        file_name="attendance_flags.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Validated input
# ---------------------------------------------------------------------------

st.subheader("4. Validated input data")
st.caption(
    "The original CSV is not modified. This view shows the type-coerced "
    "copy that detectors consume: dates parsed, hours as numbers, "
    "leave_status normalized to lowercase."
)
display_data = result.data.copy()
display_data["date"] = display_data["date"].dt.strftime("%Y-%m-%d")
st.dataframe(display_data, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "Known limitations: half-day leave with partial work is flagged as "
    "CONTRADICTORY_LEAVE (schema has no half-day field); legitimate split "
    "shifts stored as two daily rows are flagged as DUPLICATE_RECORD. See "
    "README.md for the full list."
)
