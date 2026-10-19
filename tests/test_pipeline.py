"""End-to-end tests for ``attendance_checker.pipeline``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from attendance_checker import (
    AnalysisResult,
    DetectionConfig,
    SchemaValidationError,
    analyze,
    analyze_csv,
    read_csv,
)
from attendance_checker.detectors import ANOMALY_CODES, FLAG_COLUMNS


def test_one_of_each_produces_one_flag_per_detector(fixtures_dir: Path) -> None:
    """The golden fixture triggers exactly one instance of every anomaly."""
    result = analyze_csv(fixtures_dir / "one_of_each.csv")
    assert isinstance(result, AnalysisResult)
    expected = {
        "UNRECORDED_ATTENDANCE": 1,
        "CONTRADICTORY_LEAVE": 1,
        "DUPLICATE_RECORD": 2,  # both rows of the pair are flagged
        "IMPLAUSIBLE_HOURS": 1,
        "SUSTAINED_OVERTIME": 5,  # 5 rows in the streak
    }
    assert result.summary == expected
    assert len(result.flags) == sum(expected.values())
    assert list(result.flags.columns) == FLAG_COLUMNS
    # Flags are sorted by (source_row_index, anomaly_code) for stable UI.
    assert result.flags["source_row_index"].is_monotonic_increasing


def test_pipeline_summary_includes_all_codes_even_when_zero(
    fixtures_dir: Path,
) -> None:
    result = analyze_csv(fixtures_dir / "clean_minimal.csv")
    assert set(result.summary.keys()) == set(ANOMALY_CODES)
    assert all(count == 0 for count in result.summary.values())
    assert len(result.flags) == 0
    assert list(result.flags.columns) == FLAG_COLUMNS


def test_pipeline_preserves_original_input(fixtures_dir: Path) -> None:
    raw = read_csv(fixtures_dir / "one_of_each.csv")
    snapshot = raw.copy(deep=True)
    result = analyze(raw)
    pd.testing.assert_frame_equal(raw, snapshot)
    pd.testing.assert_frame_equal(result.original_data, snapshot)


def test_pipeline_reraises_schema_errors(fixtures_dir: Path) -> None:
    with pytest.raises(SchemaValidationError):
        analyze_csv(fixtures_dir / "malformed" / "bad_date.csv")


def test_pipeline_respects_custom_config(fixtures_dir: Path) -> None:
    """Changing config.max_plausible_hours should shift IMPLAUSIBLE_HOURS counts."""
    # Default config: IMPLAUSIBLE_HOURS fires once in one_of_each.csv (worked=18).
    default = analyze_csv(fixtures_dir / "one_of_each.csv")
    assert default.summary["IMPLAUSIBLE_HOURS"] == 1
    # Raise max_plausible_hours above 18 - IMPLAUSIBLE_HOURS should disappear.
    permissive = analyze_csv(
        fixtures_dir / "one_of_each.csv",
        config=DetectionConfig(max_plausible_hours=20),
    )
    assert permissive.summary["IMPLAUSIBLE_HOURS"] == 0
    # Other anomaly counts should be unchanged.
    for code in ANOMALY_CODES:
        if code == "IMPLAUSIBLE_HOURS":
            continue
        assert default.summary[code] == permissive.summary[code]


def test_pipeline_result_stores_config_used(fixtures_dir: Path) -> None:
    custom = DetectionConfig(overtime_streak=3)
    result = analyze_csv(fixtures_dir / "clean_minimal.csv", config=custom)
    assert result.config == custom


def test_pipeline_on_bundled_sample_dataset() -> None:
    """Smoke test against the demo CSV at ``sample_data/attendance_sample.csv``."""
    sample_path = (
        Path(__file__).resolve().parent.parent
        / "sample_data"
        / "attendance_sample.csv"
    )
    if not sample_path.exists():
        pytest.skip("sample_data/attendance_sample.csv not generated")
    result = analyze_csv(sample_path)
    # The generator injects one instance of each anomaly at known coordinates.
    assert result.summary["UNRECORDED_ATTENDANCE"] == 1
    assert result.summary["CONTRADICTORY_LEAVE"] == 1
    assert result.summary["DUPLICATE_RECORD"] == 2  # both rows of the pair
    assert result.summary["IMPLAUSIBLE_HOURS"] == 1
    assert result.summary["SUSTAINED_OVERTIME"] == 5
    # Spot-check specific coordinates for the injected rows.
    emp007 = result.flags[
        (result.flags["employee_id"] == "EMP007")
        & (result.flags["anomaly_code"] == "UNRECORDED_ATTENDANCE")
    ]
    assert len(emp007) == 1
    assert str(emp007.iloc[0]["date"].date()) == "2026-01-15"


def test_pipeline_warnings_surface_from_validation(fixtures_dir: Path) -> None:
    result = analyze_csv(fixtures_dir / "edge" / "unusual_date.csv")
    # Validation generates two UNUSUAL_DATE warnings; detectors still run.
    codes = [w.code for w in result.warnings]
    assert codes == ["UNUSUAL_DATE", "UNUSUAL_DATE"]
