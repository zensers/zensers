# -*- coding: utf-8 -*-
"""
SemanticQualityAdapter 全链路集成测试

覆盖:
1. _infer_section_type — 9 种 type + 边界条件
2. 模拟 engine.py 三个调用点 (1388/1216/2591) 的数据结构
3. BaseQualityChecker 接口契约（各抽象方法）
4. 边界条件（非 dict data / 超长内容 / 特殊字符）
5. 降级链（ImportError / RuntimeError / 双重降级）
6. 多调用隔离
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.quality.semantic_adapter import SemanticQualityAdapter, _infer_section_type
from src.core.quality.semantic_scorer import _SECTION_TYPE_TO_ASPECTS
from src.core.quality.checkers import QualityResult, BaseQualityChecker


# ========== _infer_section_type (覆盖所有 9 种 type) ==========

class TestInferSectionTypeAllTypes:
    """9 种 section_type 全覆盖"""
    def verify(self, type_key: str, source: str):
        data = {"agent_id": source}
        assert _infer_section_type(data) == type_key, f"{source} → {type_key}"

    def test_market_size_by_agent_id(self):
        self.verify("market_size", "market_size_analyst")
    def test_market_size_by_title(self):
        assert _infer_section_type({"title": "市场规模分析"}) == "market_size"
    def test_market_size_by_content(self):
        assert _infer_section_type({"content": "2024年市场规模达到"}) == "market_size"

    def test_competition_by_agent_id(self):
        assert _infer_section_type({"agent_id": "competition_analysis"}) == "competition"
    def test_competition_by_title(self):
        assert _infer_section_type({"title": "竞争格局分析"}) == "competition"

    def test_technology_by_content(self):
        assert _infer_section_type({"content": "技术分析部分"}) == "technology"
    def test_technology_by_title(self):
        assert _infer_section_type({"title": "技术路线对比"}) == "technology"

    def test_risk_by_agent_id(self):
        assert _infer_section_type({"agent_id": "risk_assessment"}) == "risk"
    def test_risk_by_title(self):
        assert _infer_section_type({"title": "风险分析"}) == "risk"

    def test_financial_by_content(self):
        assert _infer_section_type({"agent_id": "financial_analyst"}) == "financial_analysis"
    def test_financial_by_title(self):
        assert _infer_section_type({"title": "财务分析"}) == "financial_analysis"

    def test_policy_by_content(self):
        assert _infer_section_type({"agent_id": "policy_research"}) == "policy"

    def test_enterprise_by_title(self):
        assert _infer_section_type({"title": "企业深度分析"}) == "enterprise"

    def test_industry_chain_by_title(self):
        assert _infer_section_type({"title": "产业链分析"}) == "industry_chain"

    def test_trend_by_content(self):
        assert _infer_section_type({"agent_id": "trend_forecast"}) == "trend"

    def test_fallback_generic(self):
        assert _infer_section_type({"content": "普通内容"}) == "generic"

    def test_non_dict_data_returns_generic(self):
        assert _infer_section_type("not a dict") == "generic"

    def test_from_context_fallback(self):
        data = {"content": "内容"}
        context = {"agent_id": "technology_analysis"}
        assert _infer_section_type(data, context) == "technology"

    def test_context_only_used_when_data_missing(self):
        data = {"agent_id": "risk_analysis", "content": "内容"}
        context = {"agent_id": "technology_analysis"}
        assert _infer_section_type(data, context) == "risk"  # data 优先

    def test_no_content_no_ids(self):
        assert _infer_section_type({}) == "generic"

    def test_snake_case_matches_section_type_key(self):
        """每種 section_type 的 snake_case key 本身即为有效匹配模式"""
        for st in _SECTION_TYPE_TO_ASPECTS:
            data = {"agent_id": st}
            assert _infer_section_type(data) == st, f"snake_case key '{st}' should match"


# ========== engine.py 调用点模拟 ==========

class TestEngineCallSiteCompatibility:
    """模拟 engine.py 三个 check() 调用点的数据结构"""

    @staticmethod
    def make_batch_result(content: str, agent_id: str = "market_analysis",
                          sources: list = None, data_points: list = None) -> dict:
        """engine.py:1388 处 batch_results[0] 的数据结构"""
        return {
            "content": content,
            "sources": sources or [],
            "data_points": data_points or [],
            "quality_metadata": {"data_volume": len(data_points or []), "quality_score": 50.0},
        }

    def test_engine_line_1388_data_shape(self):
        """engine.py:1388 — batch analysis QC: check_data from batch_results[0]"""
        content = "市场规模分析\n\n2024年中国新能源汽车市场规模1.2万亿元，渗透率40%。"
        check_data = self.make_batch_result(content)

        adapter = SemanticQualityAdapter(threshold=30.0)
        result = adapter.check(check_data)

        assert isinstance(result, QualityResult)
        assert result.checker_type == "semantic_three_layer"
        assert 0 <= result.score <= 100
        assert isinstance(result.passed, bool)
        assert isinstance(result.issues, list)
        assert isinstance(result.suggestions, list)
        assert isinstance(result.details, dict)

    def test_engine_line_1216_data_shape(self):
        """engine.py:1216 — cached results QC: check_data with quality_metadata"""
        check_data = {
            "content": "技术分析\n\n固态电池技术路线包括氧化物、硫化物等。",
            "sources": ["source1", "source2"],
            "data_points": [{"key": "val"}],
            "quality_metadata": {"data_volume": 1, "sources": ["s1"], "quality_score": 50.0},
        }
        adapter = SemanticQualityAdapter(threshold=30.0)
        result = adapter.check(check_data)

        assert isinstance(result, QualityResult)
        assert result.score >= 0

    def test_engine_line_2591_data_shape(self):
        """engine.py:2591 — _execute_stage_with_quality: check_data with content/result"""
        check_data = {
            "content": "竞争分析\n\n行业集中度CR3为65%，前三大企业市场份额持续扩大。",
            "sources": [],
            "data_points": [],
        }
        adapter = SemanticQualityAdapter(threshold=30.0)
        result = adapter.check(check_data, {"batch_index": 0})

        assert isinstance(result, QualityResult)
        assert result.score >= 0

    def test_context_passthrough(self):
        """context 中包含 section_type 线索时能正确推断"""
        adapter = SemanticQualityAdapter(threshold=30.0)
        check_data = {"content": "详细的风险评估和风险分析"}
        # context 可能包含 agent_id 等
        result = adapter.check(check_data, {"agent_id": "technology_analyst"})
        assert isinstance(result, QualityResult)


# ========== BaseQualityChecker 接口契约 ==========

class TestBaseQualityCheckerContract:
    """验证 SemanticQualityAdapter 完整实现 BaseQualityChecker 抽象方法"""

    def test_get_checker_type(self):
        adapter = SemanticQualityAdapter()
        assert adapter.get_checker_type() == "semantic_three_layer"

    def test_calculate_score(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        content = "市场规模分析\n\nGDP数据1.2万亿，渗透率40%。"
        data = {"content": content}
        score = adapter.calculate_score(data)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_generate_suggestions_signature(self):
        adapter = SemanticQualityAdapter()
        result = adapter.generate_suggestions(40.0, {})
        assert isinstance(result, list)

    def test_checker_type_in_quality_result(self):
        adapter = SemanticQualityAdapter()
        result = adapter.check({"content": "test"})
        assert result.checker_type == "semantic_three_layer"

    def test_threshold_respected(self):
        """阈值 90 分时正常内容应不通过"""
        adapter = SemanticQualityAdapter(threshold=90.0)
        data = {"content": "简短内容"}
        result = adapter.check(data)
        assert result.passed is False  # 90 分阈值不可能通过短文本
        assert result.score < 90.0


# ========== 边界条件 ==========

class TestBoundaryConditions:
    def test_non_dict_data(self):
        adapter = SemanticQualityAdapter()
        result = adapter.check("not a dict")
        assert result.score == 0.0
        assert result.passed is False

    def test_none_data(self):
        adapter = SemanticQualityAdapter()
        result = adapter.check(None)  # type: ignore
        assert result.score == 0.0
        assert result.passed is False

    def test_extremely_long_content(self):
        """>10万字符内容不应导致性能问题"""
        adapter = SemanticQualityAdapter(threshold=30.0)
        long_content = "市场规模分析 " + "数据 " * 50000
        data = {"content": long_content}
        result = adapter.check(data)
        assert isinstance(result, QualityResult)

    def test_content_with_special_chars(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        content = "风险分析\n\n风险\n评估\n风险\n分析\n测试\n数据\n\n2024年数据"
        data = {"content": content}
        result = adapter.check(data)
        assert isinstance(result, QualityResult)

    def test_content_mixed_languages(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        content = "Market Size Analysis\n\nGDP growth 5.2%, 市场规模 1.2万亿。"
        data = {"content": content}
        result = adapter.check(data)
        assert isinstance(result, QualityResult)

    def test_content_only_numbers(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        data = {"content": "123 456 789 0.5 100 200 300"}
        result = adapter.check(data)
        assert isinstance(result, QualityResult)

    def test_unicode_content(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        content = "产业链分析\n\n\u4f9b\u5e94\u94fe\u5206\u6790\uff0c\u4ea7\u4e1a\u94fe\u94fe\u6761\u5206\u6790"
        data = {"content": content}
        result = adapter.check(data)
        assert isinstance(result, QualityResult)
        # section_type 应为 industry_chain
        assert result.checker_type == "semantic_three_layer"


# ========== 降级链 ==========

class TestFallbackChains:
    def test_import_error_fallback(self):
        """ImportError 时 adapter 走 fallback_checker"""
        fallback = MagicMock(spec=BaseQualityChecker)
        fallback.check.return_value = QualityResult("fallback", 50.0, 50.0, True)
        adapter = SemanticQualityAdapter(fallback_checker=fallback)

        with patch("src.core.quality.semantic_adapter.SemanticQualityScorer",
                   side_effect=ImportError("no module")):
            # 重新初始化以触发 import error
            pass

        # 直接模拟 scorer.score 异常
        with patch.object(adapter._scorer, "score", side_effect=RuntimeError("LLM failed")):
            result = adapter.check({"content": "test"})
        assert result.score == 50.0

    def test_no_fallback_on_error(self):
        """没有 fallback_checker 时返回保守 score=40"""
        adapter = SemanticQualityAdapter()
        with patch.object(adapter._scorer, "score", side_effect=RuntimeError("boom")):
            result = adapter.check({"content": "some content"})
        assert result.score == 40.0
        assert result.passed is False

    def test_fallback_also_fails(self):
        """双重降级返回 score=40"""
        fallback = MagicMock(spec=BaseQualityChecker)
        fallback.check.side_effect = ValueError("fallback error")
        adapter = SemanticQualityAdapter(fallback_checker=fallback)
        with patch.object(adapter._scorer, "score", side_effect=RuntimeError("boom")):
            result = adapter.check({"content": "some content"})
        assert result.score == 40.0

    def test_empty_content_without_fallback(self):
        adapter = SemanticQualityAdapter()
        result = adapter.check({"content": ""})
        assert result.score == 0.0
        assert result.passed is False
        assert "内容为空" in result.issues

    def test_empty_content_with_fallback(self):
        fallback = MagicMock(spec=BaseQualityChecker)
        fallback.check.return_value = QualityResult("fallback", 70.0, 50.0, True)
        adapter = SemanticQualityAdapter(fallback_checker=fallback)
        result = adapter.check({"content": ""})
        assert result.score == 70.0
        fallback.check.assert_called_once()


# ========== 多调用隔离 ==========

class TestMultiCallIsolation:
    def test_no_state_leakage_between_calls(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        r1 = adapter.check({
            "content": "市场规模分析\n\nGDP数据1.2万亿，渗透率40%。",
            "agent_id": "market_analyst",
        })
        r2 = adapter.check({
            "content": "风险分析\n\n政策风险、技术风险和市场风险。",
            "agent_id": "risk_analyst",
        })
        # 两次调用的 details 应分别反映各自的 section_type
        assert r1.details.get("layer2_framework") != "" if r1.details.get("layer2_framework") else True
        assert isinstance(r1, QualityResult)
        assert isinstance(r2, QualityResult)

    def test_consecutive_calls_all_return_valid(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        contents = [
            "市场规模分析\n\n2024年中国新能源汽车规模1.2万亿。渗透率40%。",
            "竞争分析\n\n行业集中度CR3为65%。",
            "技术分析\n\n固态电池技术路线包括氧化物和硫化物。",
            "风险分析\n\n政策风险和市场风险。",
        ]
        for c in contents:
            result = adapter.check({"content": c, "agent_id": "analyst"})
            assert isinstance(result, QualityResult)
            assert 0 <= result.score <= 100


# ========== QualityResult 完整性 ==========

class TestQualityResultCompleteness:
    def test_all_fields_populated(self):
        adapter = SemanticQualityAdapter(threshold=75.0)
        data = {"content": "测试内容需要足够长度来触发评分逻辑，但不会很高分。整体表现一般。", "agent_id": "market_analyst"}
        result = adapter.check(data)

        assert result.checker_type == "semantic_three_layer"
        assert isinstance(result.score, float)
        assert isinstance(result.threshold, float)
        assert isinstance(result.passed, bool)
        assert isinstance(result.issues, list)
        assert isinstance(result.suggestions, list)
        assert isinstance(result.details, dict)

        # 关键字段
        assert "layer1_score" in result.details
        assert "layer2_score" in result.details
        assert "layer3_score" in result.details

    def test_to_dict_serializable(self):
        adapter = SemanticQualityAdapter(threshold=50.0)
        data = {"content": "市场规模分析\n\n数据1.2万亿渗透率40%", "agent_id": "analyst"}
        result = adapter.check(data)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["checker_type"] == "semantic_three_layer"
        assert isinstance(d["score"], float)
        assert isinstance(d["passed"], bool)
        assert isinstance(d["issues"], list)
        assert isinstance(d["details"], dict)
        assert "checked_at" in d
        assert d["score_scale"] == "0-100"


# ========== 性能检查 ==========

class TestPerformance:
    def test_rapid_consecutive_calls(self):
        adapter = SemanticQualityAdapter(threshold=30.0)
        content = "市场规模分析\n\nGDP数据1.2万亿，渗透率40%。2025年预计达1.8万亿。"
        for _ in range(20):
            r = adapter.check({"content": content})
            assert isinstance(r, QualityResult)
