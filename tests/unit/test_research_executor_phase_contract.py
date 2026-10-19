"""Regression tests for research progress phase transitions."""

from unittest.mock import patch

from src.api.research_executor import _complete_orchestration_phase


def test_orchestration_phase_is_completed_before_execution():
    """The executor must close orchestration before execution begins."""
    with patch("src.api.research_executor.complete_phase") as complete:
        _complete_orchestration_phase("research_phase_contract")

    complete.assert_called_once_with("research_phase_contract", "orchestrating")
