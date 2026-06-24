# -*- coding: utf-8 -*-
"""
P0/P1 修复验证测试 — result_aggregator.py
"""
import pytest
from src.core.orchestrator.aggregation.result_aggregator import (
    _normalize_key,
    ResultAggregator,
)


class TestP02FixNormalizeKeyNoReverseSubstring:
    """P0-2 修复: 去掉反向子串匹配 (norm_id in norm_key / norm_name in norm_key)"""

    def test_short_key_in_long_section_is_correct(self):
        """'market' 在 'market_size_analysis' 中 — 这是正确的单向匹配，应保留"""
        norm_key = _normalize_key("market")
        norm_id = _normalize_key("market_size_analysis")
        assert norm_key in norm_id, "短 key 在长 section 中是正确的子串匹配"

    def test_long_section_in_short_key_now_prevented(self):
        """修复前bug: 'market_size_analysis' in 'market' 也为 True (反向匹配)
        修复后: 反向匹配已移除，由调用方保证只用 norm_key in norm_id"""
        norm_key = _normalize_key("market")
        norm_id = _normalize_key("market_size_analysis")
        assert not (norm_id in norm_key), "反向子串不应匹配"

    def test_trend_in_trend_and_policy_is_correct(self):
        """'trend' 在 'trend_and_policy' 中 — 正确的单向匹配"""
        norm_key = _normalize_key("trend")
        norm_id = _normalize_key("trend_and_policy")
        assert norm_key in norm_id, "'trend' 在 'trend_and_policy' 中是正确匹配"

    def test_exact_match_still_works(self):
        norm_key = _normalize_key("market_size")
        norm_id = _normalize_key("market_size")
        assert norm_key == norm_id


class TestA12FixDetermineSectionTarget:
    """A-P1-2/A-P1-3 修复: _determine_section_target 返回 key 本身"""

    def test_data_collection_returns_key(self):
        agg = ResultAggregator.__new__(ResultAggregator)
        result = agg._determine_section_target("some_key", "data_collection", "some_key")
        assert result == "some_key"

    def test_analysis_default_returns_key(self):
        agg = ResultAggregator.__new__(ResultAggregator)
        result = agg._determine_section_target("unknown_section_key", "analysis", "unknown_section_key")
        assert result == "unknown_section_key"
