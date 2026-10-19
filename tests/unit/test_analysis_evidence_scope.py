"""Design-contract tests for chapter-scoped analysis evidence.

These tests intentionally describe the target contract before the production
implementation is changed.  They protect high-value shared evidence while
preventing unrelated or invalid records from entering an analysis prompt.
"""

import pytest


def _scope_builder():
    from src.core.orchestrator.execution.evidence_scope import EvidenceScope
    return EvidenceScope


def test_scope_keeps_only_declared_dependency_evidence():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    records = [
        {
            "source_agent_id": "research_market_size",
            "section_id": "section_1",
            "metric": "market_size",
            "content": "valid evidence",
            "evidence_id": "ev-1",
            "quality_score": 70,
        },
        {
            "source_agent_id": "research_competition",
            "section_id": "section_2",
            "metric": "market_share",
            "content": "unrelated evidence",
            "evidence_id": "ev-2",
            "quality_score": 95,
        },
    ]

    selected, audit = scope.select(records)

    assert [item["evidence_id"] for item in selected] == ["ev-1"]
    assert audit["excluded_by_dependency"] == 1


def test_scope_drops_invalid_records_but_retains_high_value_shared_data():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    records = [
        {
            "source_agent_id": "research_market_size",
            "section_id": "section_1",
            "metric": "market_size",
            "content": "",
            "evidence_id": "invalid-empty",
        },
        {
            "source_agent_id": "shared_memory",
            "section_id": "section_1",
            "metric": "market_size",
            "value": 100,
            "unit": "亿元",
            "content": "校准后的市场规模",
            "evidence_id": "canonical-1",
            "quality_score": 100,
            "is_canonical": True,
        },
    ]

    selected, audit = scope.select(records)

    assert [item["evidence_id"] for item in selected] == ["canonical-1"]
    assert audit["excluded_invalid"] == 1
    assert audit["retained_high_value"] == 1


def test_scope_filters_global_claims_by_target_metric_but_preserves_related_claims():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    claims = [
        {"claim_id": "c1", "metric": "market_size", "statement": "规模持续增长"},
        {"claim_id": "c2", "metric": "market_share", "statement": "份额变化"},
    ]

    selected = scope.select_claims(claims)

    assert [claim["claim_id"] for claim in selected] == ["c1"]


def test_scope_keeps_validated_narrative_without_machine_metric():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    selected, _ = scope.select([{
        "source_agent_id": "research_market_size",
        "section_id": "section_1",
        "content": "行业供需变化和结构性驱动因素",
        "evidence_id": "narrative-1",
        "is_validated": True,
    }])
    assert len(selected) == 1


def test_scope_keeps_relevant_canonical_and_excludes_other_metric():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    canonical = {
        "market_size_cny": {"value": 100, "unit": "亿元", "caliber": "canonical"},
        "market_share": {"value": 20, "unit": "%", "caliber": "canonical"},
    }
    selected = scope.select_canonical(canonical)
    assert list(selected) == ["market_size_cny"]


def test_high_quality_unrelated_agent_does_not_bypass_dependency_scope():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(
        section_id="section_1",
        allowed_source_agents={"research_market_size"},
        required_metrics={"market_size"},
    )
    selected, audit = scope.select([{
        "source_agent_id": "research_competition",
        "section_id": "section_1",
        "metric": "market_size",
        "content": "高质量但不属于依赖章节",
        "evidence_id": "foreign-high-quality",
        "quality_score": 99,
    }])
    assert selected == []
    assert audit["excluded_by_dependency"] == 1


def test_malformed_quality_score_does_not_crash_scope():
    EvidenceScope = _scope_builder()
    scope = EvidenceScope(section_id="section_1", allowed_source_agents={"research_market_size"})
    selected, _ = scope.select([{
        "source_agent_id": "research_market_size",
        "section_id": "section_1",
        "content": "narrative",
        "evidence_id": "bad-quality",
        "quality_score": "not-a-number",
    }])
    assert len(selected) == 1


def test_missing_aspect_does_not_inject_global_cache_prefix():
    from src.core.orchestrator.execution.engine import ExecutionEngine
    engine = ExecutionEngine.__new__(ExecutionEngine)
    assert engine._filter_data_by_aspect([{"content": "global cache"}], "") == []
