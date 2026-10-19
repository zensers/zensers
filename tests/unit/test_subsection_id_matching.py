"""Regression tests for framework subsection IDs and rematching.

These tests intentionally exercise the ID-only path.  A title-only matcher can
hide this defect because the same content may happen to contain a similar
human-readable heading.
"""

import pytest

from src.core.orchestrator.aggregation.result_aggregator import (
    ResultAggregator,
    _build_subsections_from_skeleton,
    _match_content_to_sub_section,
)
from src.core.orchestrator.orchestrator import ResearchOrchestrator


def test_tree_builder_preserves_section_and_subsection_ids():
    orchestrator = ResearchOrchestrator.__new__(ResearchOrchestrator)

    details = orchestrator._build_section_details_from_tree([
        {
            "id": "market_size",
            "name": "市场规模",
            "sub_sections": [
                {"id": "market_size_tam", "name": "TAM", "points": ["总市场"]},
            ],
        }
    ])

    assert details[0]["id"] == "market_size"
    assert details[0]["sub_sections"][0]["id"] == "market_size_tam"


def test_template_builder_preserves_sub_section_id_alias():
    orchestrator = ResearchOrchestrator.__new__(ResearchOrchestrator)

    details = orchestrator._build_section_details_from_template([
        {
            "id": "market_size",
            "name": "市场规模",
            "sub_sections": [
                {"sub_section_id": "market_size_cagr", "name": "CAGR", "points": []},
            ],
        }
    ])

    assert details[0]["id"] == "market_size"
    assert details[0]["sub_sections"][0]["id"] == "market_size_cagr"


def test_id_only_heading_rematches_and_keeps_framework_subsection_id():
    content = "### market_size_tam\n\nTAM 为 100 亿元。\n"
    skeleton = [
        {"id": "market_size_tam", "name": "TAM（总可服务市场）", "points": []},
    ]

    matched = _match_content_to_sub_section(content, skeleton[0])
    assert "100 亿元" in matched

    subsections = _build_subsections_from_skeleton(content, skeleton)
    assert subsections[0]["id"] == "market_size_tam"
    assert "100 亿元" in subsections[0]["content"]


def test_same_title_subsections_are_isolated_by_stable_ids():
    content = (
        "### sub_a\n\nA 的证据。\n"
        "### sub_b\n\nB 的证据。\n"
    )
    skeleton = [
        {"id": "sub_a", "name": "共同标题", "points": []},
        {"id": "sub_b", "name": "共同标题", "points": []},
    ]

    subsections = _build_subsections_from_skeleton(content, skeleton)

    assert subsections[0]["id"] == "sub_a"
    assert subsections[1]["id"] == "sub_b"
    assert "A 的证据" in subsections[0]["content"]
    assert "B 的证据" in subsections[1]["content"]


def test_subsection_id_prefixes_do_not_cross_match():
    content = (
        "### sub_a_extended\n\n扩展章节证据。\n"
        "### sub_a\n\n精确章节证据。\n"
    )
    skeleton = [{"id": "sub_a", "name": "完全不同标题", "points": []}]

    matched = _match_content_to_sub_section(content, skeleton[0])

    assert "精确章节证据" in matched
    assert "扩展章节证据" not in matched


def test_section_name_provenance_is_not_reassigned_by_agent_index():
    """A display-name section target must beat phase-agent index fallback."""
    market_content = "市场规模证据。" * 30
    competition_content = "竞争格局证据。" * 30
    results = {
        # Deliberately reverse framework order vs. agent indexes.
        "phase_1_agent_0": {
            "agent_id": "phase_1_agent_0",
            "_section_id": "市场规模",
            "content": market_content,
            "category": "research",
        },
        "phase_1_agent_1": {
            "agent_id": "phase_1_agent_1",
            "_section_id": "竞争格局",
            "content": competition_content,
            "category": "research",
        },
    }
    section_details = [
        {"id": "competition", "name": "竞争格局", "content": ""},
        {"id": "market_size", "name": "市场规模", "content": ""},
    ]

    result = ResultAggregator().aggregate(results, section_details=section_details)
    sections = result.to_dict()["sections"]

    by_id = {section["id"]: section["content"] for section in sections}
    assert "竞争格局证据" in by_id["competition"]
    assert "市场规模证据" in by_id["market_size"]


def test_missing_section_id_never_uses_agent_index_to_silently_swap_content():
    """Unidentified phase results must not be assigned by completion order."""
    results = {
        # The result order is intentionally opposite to the framework order.
        "phase_1_agent_0": {
            "agent_id": "phase_1_agent_0",
            "content": "B 章节内容。" * 30,
            "category": "research",
        },
        "phase_1_agent_1": {
            "agent_id": "phase_1_agent_1",
            "content": "A 章节内容。" * 30,
            "category": "research",
        },
    }
    section_details = [
        {"id": "section_a", "name": "A 章节", "content": ""},
        {"id": "section_b", "name": "B 章节", "content": ""},
    ]

    result = ResultAggregator().aggregate(results, section_details=section_details)
    sections = {section["id"]: section["content"] for section in result.to_dict()["sections"]}

    # With no trustworthy identity, a placeholder is safer than a wrong
    # section.  In particular, A must never contain B's content.
    assert "B 章节内容" not in sections["section_a"]
    assert "A 章节内容" not in sections["section_b"]


def test_duplicate_framework_section_ids_are_rejected():
    results = {
        "section_a": {"content": "第一份内容。" * 30},
        "section_a_2": {"content": "第二份内容。" * 30},
    }
    section_details = [
        {"id": "section_a", "name": "第一章节", "content": ""},
        {"id": "section_a", "name": "第二章节", "content": ""},
    ]

    with pytest.raises(ValueError, match="duplicate framework section id"):
        ResultAggregator().aggregate(results, section_details=section_details)


def test_duplicate_framework_subsection_ids_are_rejected():
    content = "### sub_same\n\n证据。\n"
    skeleton = [
        {"id": "sub_same", "name": "第一标题", "points": []},
        {"id": "sub_same", "name": "第二标题", "points": []},
    ]

    with pytest.raises(ValueError, match="duplicate framework subsection id"):
        _build_subsections_from_skeleton(content, skeleton)
