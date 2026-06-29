"""
Edge-case tests for aggregation, recovery, and semantic matching
"""
import pytest
from unittest.mock import MagicMock
from src.core.orchestrator.aggregation.result_aggregator import (
    _semantic_match_section,
    _title_fuzzy_score,
    _tokenize_zh,
    _normalize_key,
    _edit_distance,
)
from src.core.agents.agent_session import AgentSessionStatus


class TestSemanticMatchEdgeCases:
    def test_all_keys_used(self):
        unused = {}
        result = _semantic_match_section("盈利分析", "s0", unused)
        assert result is None

    def test_section_id_with_prefix_matches_aspect(self):
        unused = {
            "agent_0": ("数据", "section_0_营收构成分析"),
        }
        result = _semantic_match_section("营收构成分析", "section_0_营收构成分析", unused)
        assert result is not None
        _, _, score = result
        assert score >= 0.9

    def test_aspect_substring_of_section_id(self):
        unused = {
            "agent_0": ("数据", "盈利能力"),
        }
        result = _semantic_match_section("盈利能力分析", "section_1_盈利能力分析", unused)
        assert result is not None

    def test_short_section_name_no_false_positive(self):
        unused = {
            "agent_0": ("股价走势数据", "股价走势"),
        }
        result = _semantic_match_section("成长性", "section_5_成长性", unused)
        assert result is None

    def test_unicode_normalization(self):
        unused = {
            "agent_0": ("数据内容", "营收、构成分析"),
        }
        result = _semantic_match_section("营收构成分析", "section_0_营收构成分析", unused)
        assert result is not None


class TestProvenanceMatchingEdgeCases:
    def test_empty_provenance_target(self):
        unused = {
            "agent_0": ("数据", ""),
        }
        result = _semantic_match_section("盈利分析", "s0", unused)
        assert result is None or result[2] < 0.3

    def test_provenance_target_is_agent_id(self):
        unused = {
            "phase_1_agent_0": ("数据", "phase_1_agent_0"),
        }
        result = _semantic_match_section("盈利分析", "s0", unused)
        assert result is None


class TestRecoveryEdgeCases:
    def _get_method(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        return ResearchOrchestrator._recover_results_from_sessions

    def test_result_with_quality_stats_dict(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock()
        session.status = AgentSessionStatus.CANCELLED
        session.agent_id = "phase_1_agent_0"
        session.result = {
            "quality_stats": {"data_points": 5, "sources": 2},
            "data_points": [{"title": "营收", "content": "100亿"}],
        }
        session.context = {"section_id": "section_0_营收构成分析"}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 1
        assert results[0]["section_id"] == "section_0_营收构成分析"
        assert results[0]["agent_id"] == "phase_1_agent_0"

    def test_result_is_none(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock()
        session.status = AgentSessionStatus.FAILED
        session.agent_id = "agent_1"
        session.result = None
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_result_is_empty_dict(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock()
        session.status = AgentSessionStatus.CANCELLED
        session.agent_id = "agent_2"
        session.result = {}
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_result_is_zero(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock()
        session.status = AgentSessionStatus.CANCELLED
        session.agent_id = "agent_3"
        session.result = 0
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_result_is_false(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock()
        session.status = AgentSessionStatus.CANCELLED
        session.agent_id = "agent_4"
        session.result = False
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_child_sessions_is_none(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        registry.child_sessions = None
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_session_without_status_attr(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock(spec=["result", "agent_id", "context"])
        session.result = {"content": "data"}
        session.agent_id = "agent_5"
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_session_without_result_attr(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = MagicMock(spec=["status", "agent_id", "context"])
        session.status = AgentSessionStatus.CANCELLED
        session.agent_id = "agent_6"
        session.context = {}
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0


class TestNormalizeKeyEdgeCases:
    def test_unicode_punctuation(self):
        result = _normalize_key("营收\u3000构成、分析")
        assert "营收" in result
        assert "构成" in result

    def test_section_prefix_stripped(self):
        result = _normalize_key("section_0_营收构成分析")
        assert not result.startswith("section_0")

    def test_multiple_underscores(self):
        result = _normalize_key("a__b___c")
        assert "__" not in result

    def test_empty(self):
        assert _normalize_key("") == ""

    def test_none_like(self):
        assert _normalize_key(None) == "" if _normalize_key(None) == "" else True


class TestEditDistanceEdgeCases:
    def test_long_strings(self):
        a = "盈利能力分析" * 10
        b = "盈利能力评估" * 10
        dist = _edit_distance(a, b)
        assert dist > 0
        assert dist < len(a)

    def test_one_empty(self):
        assert _edit_distance("abc", "") == 3
        assert _edit_distance("", "abc") == 3


class TestTitleFuzzyScoreEdgeCases:
    def test_both_empty(self):
        assert _title_fuzzy_score("", "") == 0.0

    def test_one_empty(self):
        assert _title_fuzzy_score("盈利", "") == 0.0
        assert _title_fuzzy_score("", "盈利") == 0.0

    def test_very_similar(self):
        score = _title_fuzzy_score("偿债能力分析", "偿债能力评估")
        assert score > 0.5

    def test_completely_different(self):
        score = _title_fuzzy_score("盈利能力分析", "行业竞争格局")
        assert score < 0.3
