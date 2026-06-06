# -*- coding: utf-8 -*-
"""
Track B 三层评分测试

测试 Layer2/Layer3/SemanticQualityScorer 核心功能：
- Layer2: 组件覆盖率 / 框架匹配 / evidence 检查
- Layer3: rubric 加载 / prompt 构建 / JSON 解析 / 回退
- SemanticQualityScorer: 三层融合 / Layer1 跳过逻辑
- 框架 components 字段验证
"""

import json
import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.core.quality.layer2_methodology import Layer2MethodologyScorer, Layer2Result
from src.core.quality.layer3_depth import Layer3DepthScorer, Layer3Result, _DEFAULT_DIMENSIONS
from src.core.quality.semantic_scorer import SemanticQualityScorer, SectionScore


# ========== Fixtures ==========

MARKET_SIZE_FRAMEWORK = {
    "id": "market_sizing_top_down",
    "name": "Top-down 市场规模测算",
    "components": [
        {"id": "macro_indicator", "name": "宏观总量指标", "keywords": ["GDP", "总产值", "总规模"]},
        {"id": "industry_filter", "name": "行业占比筛选", "keywords": ["占比", "份额", "渗透率"]},
        {"id": "segment_breakdown", "name": "细分市场分配", "keywords": ["细分", "产品线", "区域"]},
        {"id": "cross_validation", "name": "交叉验证", "keywords": ["交叉验证", "偏差", "校准"]},
        {"id": "assumption_disclosure", "name": "假设与口径说明", "keywords": ["假设", "口径", "数据来源"]},
    ],
    "evidence_required": ["宏观统计数据", "行业研究报告", "企业财报或官方数据", "至少2个独立数据源"],
}

GOOD_MARKET_CONTENT = """
## 市场规模分析

根据国家统计局GDP数据和行业研究报告，2024年中国新能源汽车市场规模达到1.2万亿元。
从宏观总量看，GDP中新能源汽车占比约8.5%，渗透率持续提升。

按产品线细分，纯电动车占60%，插电混动占35%，增程式占5%。区域方面，
华东地区占比最高约35%，华南约25%。交叉验证显示，与中汽协数据偏差<3%，
口径以零售价计算，数据来源包括中汽协、乘联会和国家统计局。

市场增长驱动因素包括政策支持、电池成本下降和充电基础设施完善。
预计2025年市场规模将达到1.5万亿元，CAGR约25%。
"""


# ========== Layer 2 ==========

class TestLayer2ComponentCoverage:
    def test_full_coverage(self):
        scorer = Layer2MethodologyScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size", [MARKET_SIZE_FRAMEWORK])
        assert result.component_coverage_rate > 0.6
        assert result.component_coverage.get("macro_indicator") is True
        assert result.component_coverage.get("segment_breakdown") is True

    def test_low_coverage_poor_content(self):
        scorer = Layer2MethodologyScorer()
        content = "新能源汽车市场很好"
        result = scorer.score(content, "market_size", [MARKET_SIZE_FRAMEWORK])
        assert result.component_coverage_rate < 0.5

    def test_empty_content_returns_zero(self):
        scorer = Layer2MethodologyScorer()
        result = scorer.score("", "market_size", [MARKET_SIZE_FRAMEWORK])
        assert result.score == 0.0

    def test_no_frameworks_returns_zero(self):
        scorer = Layer2MethodologyScorer()
        result = scorer.score("some content", "market_size", [])
        assert result.score == 0.0

    def test_framework_without_components(self):
        fw = {"id": "basic", "name": "Basic", "content": "简单框架"}
        scorer = Layer2MethodologyScorer()
        result = scorer.score("一些内容", "market_size", [fw])
        assert result.score > 0

    def test_max_frameworks_limit(self):
        fw1 = {"id": "fw1", "name": "FW1", "components": [{"id": "c1", "keywords": ["GDP"]}]}
        fw2 = {"id": "fw2", "name": "FW2", "components": [{"id": "c2", "keywords": ["竞争"]}]}
        fw3 = {"id": "fw3", "name": "FW3", "components": [{"id": "c3", "keywords": ["技术"]}]}
        scorer = Layer2MethodologyScorer()
        result = scorer.score("GDP增长带动竞争和技术发展", "market_size", [fw1, fw2, fw3], max_frameworks=2)
        assert result.details.get("evaluated_frameworks")
        assert len(result.details["evaluated_frameworks"]) <= 2

    def test_best_framework_selected(self):
        fw1 = {"id": "poor_match", "name": "Poor", "components": [{"id": "c", "keywords": ["量子计算"]}]}
        fw2 = {"id": "good_match", "name": "Good", "components": [{"id": "c", "keywords": ["GDP", "市场"]}]}
        scorer = Layer2MethodologyScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size", [fw1, fw2])
        assert result.framework_name == "Good"


class TestLayer2Evidence:
    def test_evidence_quality_good_content(self):
        scorer = Layer2MethodologyScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size", [MARKET_SIZE_FRAMEWORK])
        assert result.evidence_quality > 40

    def test_evidence_quality_poor_content(self):
        scorer = Layer2MethodologyScorer()
        result = scorer.score("新能源汽车很好", "market_size", [MARKET_SIZE_FRAMEWORK])
        assert result.evidence_quality < 50


class TestLayer2LLMMatch:
    def test_no_llm_uses_coverage_as_proxy(self):
        scorer = Layer2MethodologyScorer(llm_client=None)
        fw = {"id": "test", "name": "Test", "components": [
            {"id": "c1", "keywords": ["GDP"]},
            {"id": "c2", "keywords": ["细分"]},
        ]}
        result = scorer.score("GDP数据显示市场细分明显", "market_size", [fw])
        assert result.framework_match_score > 0


# ========== Layer 3 ==========

class TestLayer3RubricLoading:
    def test_loads_existing_rubric(self):
        scorer = Layer3DepthScorer()
        rubric = scorer._load_rubric("market_size")
        assert rubric is not None
        assert rubric.get("rubric_id") is not None

    def test_fallback_to_default_for_unknown_type(self):
        scorer = Layer3DepthScorer()
        rubric = scorer._load_rubric("nonexistent_type_xyz")
        assert rubric.get("rubric_id") == "default"

    def test_dimensions_extracted_from_rubric(self):
        scorer = Layer3DepthScorer()
        rubric = scorer._load_rubric("market_size")
        dims = scorer._extract_dimensions(rubric)
        assert len(dims) >= 3
        assert all("name" in d and "weight" in d for d in dims)
        total_weight = sum(d["weight"] for d in dims)
        assert abs(total_weight - 1.0) < 0.01

    def test_default_dimensions_weights_sum_to_one(self):
        total = sum(d["weight"] for d in _DEFAULT_DIMENSIONS)
        assert abs(total - 1.0) < 0.001


class TestLayer3PromptBuilding:
    def test_prompt_contains_dimensions(self):
        scorer = Layer3DepthScorer()
        dims = [{"name": "洞察力", "weight": 0.25, "description": "test"}]
        prompt = scorer._build_prompt("some content", dims)
        assert "洞察力" in prompt
        assert "25%" in prompt

    def test_prompt_truncates_long_content(self):
        scorer = Layer3DepthScorer()
        dims = _DEFAULT_DIMENSIONS
        long_content = "x" * 20000
        prompt = scorer._build_prompt(long_content, dims)
        assert len(prompt) < 25000


class TestLayer3ResponseParsing:
    def test_parse_valid_json(self):
        scorer = Layer3DepthScorer()
        dims = _DEFAULT_DIMENSIONS
        response = json.dumps({
            "洞察力": 80, "逻辑链完整性": 75, "数据批判性": 60,
            "前瞻性": 50, "可验证性": 70, "issues": ["缺乏数据来源"]
        })
        result = scorer._parse_response(response, dims)
        assert result is not None
        assert result["洞察力"] == 80
        assert "缺乏数据来源" in result["_issues"]

    def test_parse_with_surrounding_text(self):
        scorer = Layer3DepthScorer()
        dims = _DEFAULT_DIMENSIONS
        response = f'Here: {json.dumps({"洞察力": 70, "逻辑链完整性": 65, "数据批判性": 55, "前瞻性": 45, "可验证性": 60, "issues": []})} end'
        result = scorer._parse_response(response, dims)
        assert result is not None
        assert result["洞察力"] == 70

    def test_parse_invalid_returns_none(self):
        scorer = Layer3DepthScorer()
        result = scorer._parse_response("not json", _DEFAULT_DIMENSIONS)
        assert result is None

    def test_parse_missing_dims_get_default_50(self):
        scorer = Layer3DepthScorer()
        dims = _DEFAULT_DIMENSIONS
        response = json.dumps({"洞察力": 80, "issues": []})
        result = scorer._parse_response(response, dims)
        assert result is not None
        assert result["逻辑链完整性"] == 50

    def test_score_clamped_to_100(self):
        scorer = Layer3DepthScorer()
        dims = _DEFAULT_DIMENSIONS
        response = json.dumps({
            "洞察力": 150, "逻辑链完整性": 100, "数据批判性": 100,
            "前瞻性": 100, "可验证性": 100, "issues": []
        })
        result = scorer._parse_response(response, dims)
        assert result["洞察力"] == 100


class TestLayer3EmptyAndEdgeCases:
    def test_empty_content_returns_zero(self):
        scorer = Layer3DepthScorer()
        result = scorer.score("", "market_size")
        assert result.score == 0.0
        assert "内容为空" in result.issues

    def test_none_content_returns_zero(self):
        scorer = Layer3DepthScorer()
        result = scorer.score(None, "market_size")
        assert result.score == 0.0


# ========== SemanticQualityScorer ==========

class TestSemanticScorerIntegration:
    def test_full_three_layer_scoring(self):
        scorer = SemanticQualityScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size")
        assert result.total > 0
        assert result.layer1_score > 0
        assert 0 <= result.layer1_score <= 100
        assert 0 <= result.layer2_score <= 100
        assert 0 <= result.layer3_score <= 100

    def test_layer1_skip_threshold(self):
        scorer = SemanticQualityScorer()
        poor_content = "市场规模很好。" * 3
        result = scorer.score(poor_content, "market_size")
        if result.layer1_score < 30:
            assert "layer2" in result.skipped_layers
            assert "layer3" in result.skipped_layers
            assert result.layer2_score == 0.0

    def test_weights_sum_correctly(self):
        scorer = SemanticQualityScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size")
        if not result.skipped_layers:
            expected = round(
                result.layer1_score * 0.25 +
                result.layer2_score * 0.40 +
                result.layer3_score * 0.35, 1
            )
            assert result.total == expected

    def test_custom_elements_override(self):
        custom_elements = {
            "test_type": [
                {"id": "custom", "patterns": ["自定义关键词"], "weight": 1.0}
            ]
        }
        scorer = SemanticQualityScorer(section_elements=custom_elements)
        result = scorer.score("包含自定义关键词的内容分析报告", "test_type")
        assert result.layer1_score > 0

    def test_details_populated(self):
        scorer = SemanticQualityScorer()
        result = scorer.score(GOOD_MARKET_CONTENT, "market_size")
        assert "layer1" in result.layers_detail
        assert "layer3" in result.layers_detail


# ========== Framework Components Validation ==========

class TestFrameworkComponents:
    def test_market_sizing_has_components(self):
        from src.methodologies.registry import load_frameworks, _frameworks
        load_frameworks()
        fw = next((f for f in _frameworks if f.get("id") == "market_sizing_top_down"), None)
        assert fw is not None
        assert "components" in fw
        assert len(fw["components"]) >= 4
        assert "evidence_required" in fw

    def test_porter_five_forces_has_components(self):
        from src.methodologies.registry import load_frameworks, _frameworks
        load_frameworks()
        fw = next((f for f in _frameworks if f.get("id") == "porter_five_forces"), None)
        assert fw is not None
        assert "components" in fw
        assert len(fw["components"]) == 5

    def test_technology_s_curve_has_components(self):
        from src.methodologies.registry import load_frameworks, _frameworks
        load_frameworks()
        fw = next((f for f in _frameworks if f.get("id") == "technology_s_curve"), None)
        assert fw is not None
        assert "components" in fw
        assert len(fw["components"]) == 5

    def test_component_keywords_are_list(self):
        from src.methodologies.registry import load_frameworks, _frameworks
        load_frameworks()
        for fw in _frameworks:
            for comp in fw.get("components", []):
                assert isinstance(comp.get("keywords", []), list), f"{fw['id']}.{comp['id']}"
