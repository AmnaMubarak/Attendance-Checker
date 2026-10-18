"""Tests for ``attendance_checker.config.DetectionConfig``."""

from __future__ import annotations

import pytest

from attendance_checker.config import DetectionConfig


def test_defaults_match_design() -> None:
    cfg = DetectionConfig()
    assert cfg.max_plausible_hours == 16.0
    assert cfg.overtime_margin == 2.0
    assert cfg.overtime_streak == 5
    assert cfg.max_gap_days == 10


def test_config_is_frozen() -> None:
    cfg = DetectionConfig()
    with pytest.raises((AttributeError, Exception)):
        cfg.overtime_streak = 99  # type: ignore[misc]


def test_max_gap_days_can_be_disabled() -> None:
    cfg = DetectionConfig(max_gap_days=None)
    assert cfg.max_gap_days is None


@pytest.mark.parametrize("bad_value", [0, -1.0, 24.0001, 25])
def test_rejects_invalid_max_plausible_hours(bad_value: float) -> None:
    with pytest.raises(ValueError, match="max_plausible_hours"):
        DetectionConfig(max_plausible_hours=bad_value)


def test_accepts_max_plausible_hours_at_boundary() -> None:
    # 24.0 is valid (interval is (0, 24]); 0.1 is valid too.
    DetectionConfig(max_plausible_hours=24.0)
    DetectionConfig(max_plausible_hours=0.1)


def test_rejects_negative_overtime_margin() -> None:
    with pytest.raises(ValueError, match="overtime_margin"):
        DetectionConfig(overtime_margin=-0.5)


def test_accepts_zero_overtime_margin() -> None:
    DetectionConfig(overtime_margin=0.0)


@pytest.mark.parametrize("bad_value", [0, -1, -10])
def test_rejects_invalid_overtime_streak(bad_value: int) -> None:
    with pytest.raises(ValueError, match="overtime_streak"):
        DetectionConfig(overtime_streak=bad_value)


@pytest.mark.parametrize("bad_value", [0, -5])
def test_rejects_invalid_max_gap_days(bad_value: int) -> None:
    with pytest.raises(ValueError, match="max_gap_days"):
        DetectionConfig(max_gap_days=bad_value)
