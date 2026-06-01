"""Pytest fixtures for API tests."""

import os
from pathlib import Path
import pytest
from src.config.settings import Settings


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset the Settings singleton and clean up disk persistence before each test."""
    _clean_persist()
    Settings._reset_instance()
    yield
    Settings._reset_instance()
    _clean_persist()


def _clean_persist():
    path = Path("data/llm_config.json")
    if path.exists():
        path.unlink()
