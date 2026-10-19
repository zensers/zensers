"""Regression tests for evidence duplication and analysis prompt growth."""

from src.core.agents.generic_agent import GenericAgent
from src.core.orchestrator.execution.engine import _evidence_record_key
from src.core.orchestrator.execution.engine import ExecutionEngine


def _agent():
    agent = GenericAgent.__new__(GenericAgent)
    agent._context = {}
    return agent


def test_analysis_prompt_deduplicates_without_truncating_large_evidence():
    duplicate = {
        "evidence_id": "ev-1",
        "title": "same source",
        "content": "x" * 20000,
        "url": "https://example.test/1",
    }
    points = [duplicate, dict(duplicate)] + [
        {"evidence_id": f"ev-{i}", "title": f"source {i}", "content": "y" * 20000}
        for i in range(2, 70)
    ]

    prompt = _agent()._build_analysis_prompt_with_data(
        topic="新能源汽车",
        aspect="市场规模",
        aspects=["市场规模"],
        data_points=points,
        sources=[],
    )

    assert len(prompt) > 100000
    assert prompt.count("same source") == 1
    assert "x" * 20000 in prompt
    assert "Deep Analysis Task" in prompt


def test_analysis_prompt_deduplicates_same_evidence_id_with_updated_payload():
    points = [
        {"evidence_id": "ev-1", "title": "same", "content": "old"},
        {"evidence_id": "ev-1", "title": "same", "content": "new"},
    ]
    prompt = _agent()._build_analysis_prompt_with_data(
        topic="新能源汽车", aspect="市场规模", aspects=["市场规模"], data_points=points, sources=[]
    )
    assert prompt.count("**same**") == 1


def test_evidence_key_keeps_distinct_content_without_ids_separate():
    first = {"url": "https://example.test", "title": "same", "content": "2024"}
    second = {"url": "https://example.test", "title": "same", "content": "2025"}
    assert _evidence_record_key(first, "data_point") != _evidence_record_key(second, "data_point")


def test_aspect_fallback_does_not_return_unrelated_prefix():
    engine = ExecutionEngine.__new__(ExecutionEngine)
    points = [{"title": "竞争格局", "content": "企业份额"}]
    assert engine._filter_data_by_aspect(points, "市场规模") == []
