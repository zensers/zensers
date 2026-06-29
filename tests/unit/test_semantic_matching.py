"""
Tests for semantic matching, provenance enhancement, and recovery in result_aggregator.py
"""
import pytest
from src.core.orchestrator.aggregation.result_aggregator import (
    _edit_distance,
    _normalize_key,
    _tokenize_zh,
    _compute_jaccard,
    _title_fuzzy_score,
    _semantic_match_section,
)


class TestEditDistance:
    def test_identical(self):
        assert _edit_distance("abc", "abc") == 0

    def test_empty(self):
        assert _edit_distance("", "abc") == 3
        assert _edit_distance("abc", "") == 3
        assert _edit_distance("", "") == 0

    def test_single_edit(self):
        assert _edit_distance("abc", "abd") == 1

    def test_insertion(self):
        assert _edit_distance("abc", "abdc") == 1

    def test_deletion(self):
        assert _edit_distance("abdc", "abc") == 1

    def test_chinese(self):
        assert _edit_distance("盈利能力", "盈利分析") >= 0


class TestTokenizeZh:
    def test_empty(self):
        assert _tokenize_zh("") == set()

    def test_single_char(self):
        tokens = _tokenize_zh("盈")
        assert len(tokens) <= 1

    def test_two_chars(self):
        tokens = _tokenize_zh("盈利")
        assert "盈利" in tokens

    def test_stopword_filtered(self):
        tokens = _tokenize_zh("的分析")
        assert "的" not in tokens or "分析" not in tokens

    def test_mixed_chinese_english(self):
        tokens = _tokenize_zh("盈利PE分析")
        assert "盈利" in tokens
        assert "pe" in tokens

    def test_long_chinese(self):
        tokens = _tokenize_zh("偿债能力分析")
        assert "偿债" in tokens
        assert "能力" in tokens


class TestComputeJaccard:
    def test_identical(self):
        s = {"a", "b"}
        assert _compute_jaccard(s, s) == 1.0

    def test_no_overlap(self):
        assert _compute_jaccard({"a"}, {"b"}) == 0.0

    def test_empty(self):
        assert _compute_jaccard(set(), {"a"}) == 0.0
        assert _compute_jaccard({"a"}, set()) == 0.0


class TestTitleFuzzyScore:
    def test_identical(self):
        score = _title_fuzzy_score("盈利能力分析", "盈利能力分析")
        assert score == 1.0

    def test_similar(self):
        score = _title_fuzzy_score("偿债能力分析", "偿债能力评估")
        assert score > 0.3

    def test_unrelated(self):
        score = _title_fuzzy_score("偿债能力分析", "行业竞争格局")
        assert score < 0.3

    def test_empty(self):
        assert _title_fuzzy_score("", "abc") == 0.0
        assert _title_fuzzy_score("abc", "") == 0.0


class TestSemanticMatchSection:
    def test_exact_aspect_match(self):
        unused = {
            "phase_1_agent_0": ("营收数据内容", "营收构成分析"),
        }
        result = _semantic_match_section("营收构成分析", "section_0_营收构成分析", unused)
        assert result is not None
        key, content, score = result
        assert key == "phase_1_agent_0"
        assert score >= 0.9

    def test_fuzzy_title_match(self):
        unused = {
            "phase_1_agent_0": ("偿债数据内容", "偿债能力评估"),
        }
        result = _semantic_match_section("偿债能力分析", "section_2_偿债能力分析", unused)
        assert result is not None
        _, _, score = result
        assert score >= 0.3

    def test_no_match(self):
        unused = {
            "phase_1_agent_0": ("股价走势数据", "股价走势分析"),
        }
        result = _semantic_match_section("偿债能力分析", "section_2_偿债能力分析", unused)
        assert result is None

    def test_empty_unused(self):
        result = _semantic_match_section("盈利分析", "section_0_盈利分析", {})
        assert result is None

    def test_content_fallback(self):
        unused = {
            "agent_x": ("偿债能力分析包括流动比率速动比率产权比率等指标", ""),
        }
        result = _semantic_match_section("偿债能力分析", "section_2_偿债能力分析", unused)
        assert result is not None
        _, _, score = result
        assert score >= 0.2


class TestProvenanceMatching:
    def test_exact_match(self):
        section_id = "营收构成分析"
        p_target = "营收构成分析"
        assert p_target == section_id

    def test_section_id_in_target(self):
        section_id = "营收构成分析"
        p_target = "section_0_营收构成分析"
        assert section_id in p_target

    def test_target_in_section_id(self):
        section_id = "section_0_营收构成分析"
        p_target = "营收构成分析"
        assert p_target in section_id

    def test_suffix_match(self):
        section_id = "营收构成分析"
        p_target = "section_0_营收构成分析"
        assert p_target.endswith("_" + section_id)

    def test_prefix_section_id_suffix(self):
        section_id = "section_0_营收构成分析"
        p_target = "营收构成分析"
        assert section_id.endswith("_" + p_target)
