"""Regression tests for DuckDuckGo burst protection."""

from src.skills.search_skill import MultiSearchSkill


def test_ddgs_has_process_wide_concurrency_limit():
    """Agent-local skill instances must share a bounded DDGS limit."""
    assert MultiSearchSkill._DDGS_MAX_CONCURRENCY == 4
    assert MultiSearchSkill._DDGS_CONCURRENCY is not None
