"""Shared test fixtures and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the ``tests/fixtures/`` directory."""
    return FIXTURES_DIR
