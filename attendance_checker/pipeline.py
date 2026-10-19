"""End-to-end pipeline: validate -> run all detectors -> summarize.

Exposes:

- :class:`AnalysisResult` - everything a UI needs to render results.
- :func:`analyze` - run on an in-memory DataFrame.
- :func:`analyze_csv` - read a CSV, then :func:`analyze`.

The pipeline NEVER mutates the input. If validation fails, the pipeline
re-raises :class:`SchemaValidationError`; detectors never see partial
data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from attendance_checker.config import DetectionConfig
from attendance_checker.detectors import (
    ANOMALY_CODES,
    FLAG_COLUMNS,
    detect_contradictory_leave,
    detect_duplicate_record,
    detect_implausible_hours,
    detect_sustained_overtime,
    detect_unrecorded_attendance,
)
from attendance_checker.schema import (
    PathOrBuffer,
    ValidationIssue,
    read_csv,
    validate,
)


# Order matters only for stable iteration; the final flags DataFrame is
# re-sorted by (source_row_index, anomaly_code).
DETECTORS: Tuple[Tuple[str, Callable[[pd.DataFrame, DetectionConfig], pd.DataFrame]], ...] = (
    ("UNRECORDED_ATTENDANCE", detect_unrecorded_attendance),
    ("CONTRADICTORY_LEAVE", detect_contradictory_leave),
    ("DUPLICATE_RECORD", detect_duplicate_record),
    ("IMPLAUSIBLE_HOURS", detect_implausible_hours),
    ("SUSTAINED_OVERTIME", detect_sustained_overtime),
)


@dataclass(frozen=True)
class AnalysisResult:
    """Combined output of validation + all detectors.

    Attributes
    ----------
    data : pd.DataFrame
        Validated, type-coerced input (unchanged across the pipeline).
    original_data : pd.DataFrame
        Bitwise copy of what was read from CSV, for display / audit.
    warnings : list[ValidationIssue]
        Non-fatal findings from validation (e.g. unusual dates).
    flags : pd.DataFrame
        Concatenated flags from every detector, sorted by
        ``(source_row_index, anomaly_code)``. Columns match
        :data:`attendance_checker.detectors.FLAG_COLUMNS`.
    summary : dict[str, int]
        ``{anomaly_code: count}`` with ALL five codes present (zero when
        no flags). Useful for stable UI rendering.
    config : DetectionConfig
        The configuration used, included for reproducibility.
    """

    data: pd.DataFrame
    original_data: pd.DataFrame
    warnings: List[ValidationIssue]
    flags: pd.DataFrame
    summary: Dict[str, int]
    config: DetectionConfig = field(default_factory=DetectionConfig)


def analyze(
    df: pd.DataFrame, config: Optional[DetectionConfig] = None
) -> AnalysisResult:
    """Validate ``df`` and run every detector against the validated data."""
    cfg = config if config is not None else DetectionConfig()
    validation = validate(df)

    frames: List[pd.DataFrame] = []
    summary: Dict[str, int] = {code: 0 for code in ANOMALY_CODES}
    for code, detector in DETECTORS:
        flagged = detector(validation.data, cfg)
        summary[code] = int(len(flagged))
        if not flagged.empty:
            frames.append(flagged)

    if frames:
        combined = pd.concat(frames, ignore_index=True)[FLAG_COLUMNS]
        combined = combined.sort_values(
            ["source_row_index", "anomaly_code"], kind="mergesort"
        ).reset_index(drop=True)
    else:
        # Preserve the FLAG_COLUMNS dtype contract when there are no flags.
        combined = pd.DataFrame(
            {
                "source_row_index": pd.Series([], dtype="int64"),
                "employee_id": pd.Series([], dtype="object"),
                "date": pd.Series([], dtype="datetime64[ns]"),
                "anomaly_code": pd.Series([], dtype="object"),
                "reason": pd.Series([], dtype="object"),
            }
        )

    return AnalysisResult(
        data=validation.data,
        original_data=validation.original_data,
        warnings=list(validation.warnings),
        flags=combined,
        summary=summary,
        config=cfg,
    )


def analyze_csv(
    source: PathOrBuffer, config: Optional[DetectionConfig] = None
) -> AnalysisResult:
    """Convenience: read ``source`` as CSV and run :func:`analyze`."""
    return analyze(read_csv(source), config)


__all__ = [
    "AnalysisResult",
    "DETECTORS",
    "analyze",
    "analyze_csv",
]
