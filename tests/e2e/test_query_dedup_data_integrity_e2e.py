# -*- coding: utf-8 -*-
"""
查询去重与数据完整性 端到端测试

模拟"比亚迪公司财务报告"场景，验证五阶段流水线从 intent 到最终数据的完整贯通：
  Stage 0: 数据源路由（结构化数据源优先于搜索）
  Stage 1: 3 级框架 + 查询规划（LLM 生成 section_data_specs）
  Stage 2: Engine 层统一查询去重 + 搜索执行
  Stage 3: 数据对账 + 补充
  Stage 4: 分析（不变，不在本测试范围）

5 个 E2E 场景：
  1. 完整流水线贯通
  2. 查询去重验证（共享指标只搜 1 次）
  3. 数据冲突解决（structured_source > search_result）
  4. 覆盖率补充闭环
  5. Fallback 路径（LLM 不返回 section_data_specs 时退化）
"""

import pytest
import asyncio
import copy
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


BYD_TOPIC = "比亚迪公司财务分析"
BYD_ASPECTS = [
    "核心指标与盈利能力",
    "研发创新投资",
    "供应成本效率",
    "核心市场规模",
    "资本回报率",
    "稳健性",
    "业内比较竞争力",
    "投资预测",
]

LLM_SECTION_DATA_SPECS = [
    {
        "section_id": "section_0",
        "name": "核心指标与盈利能力",
        "sub_sections": [
            {"sub_section_id": "sub_0_0", "name": "营收分析", "data_needs": ["营收", "营收增长率"], "data_source_type": "structured"},
            {"sub_section_id": "sub_0_1", "name": "利润分析", "data_needs": ["净利润", "毛利率", "净利率"], "data_source_type": "structured"},
            {"sub_section_id": "sub_0_2", "name": "盈利能力指标", "data_needs": ["ROE", "ROA"], "data_source_type": "structured"},
        ],
    },
    {
        "section_id": "section_1",
        "name": "研发创新投资",
        "sub_sections": [
            {"sub_section_id": "sub_1_0", "name": "研发投入", "data_needs": ["研发费用", "研发费用率"], "data_source_type": "structured"},
            {"sub_section_id": "sub_1_1", "name": "技术专利", "data_needs": ["专利数量", "技术突破"], "data_source_type": "search"},
        ],
    },
    {
        "section_id": "section_2",
        "name": "供应成本效率",
        "sub_sections": [
            {"sub_section_id": "sub_2_0", "name": "供应链", "data_needs": ["供应商集中度", "原材料成本"], "data_source_type": "search"},
            {"sub_section_id": "sub_2_1", "name": "成本结构", "data_needs": ["营业成本", "成本率"], "data_source_type": "both"},
        ],
    },
    {
        "section_id": "section_3",
        "name": "核心市场规模",
        "sub_sections": [
            {"sub_section_id": "sub_3_0", "name": "市场规模", "data_needs": ["TAM", "市场增速"], "data_source_type": "search"},
            {"sub_section_id": "sub_3_1", "name": "销量与份额", "data_needs": ["销量", "市场份额", "营收"], "data_source_type": "both"},
        ],
    },
    {
        "section_id": "section_4",
        "name": "资本回报率",
        "sub_sections": [
            {"sub_section_id": "sub_4_0", "name": "回报指标", "data_needs": ["ROE", "ROIC", "资本效率"], "data_source_type": "structured"},
            {"sub_section_id": "sub_4_1", "name": "资本结构", "data_needs": ["资产负债率", "权益乘数"], "data_source_type": "structured"},
        ],
    },
    {
        "section_id": "section_5",
        "name": "稳健性",
        "sub_sections": [
            {"sub_section_id": "sub_5_0", "name": "杠杆", "data_needs": ["资产负债率", "产权比率"], "data_source_type": "structured"},
            {"sub_section_id": "sub_5_1", "name": "流动性", "data_needs": ["流动比率", "速动比率", "现金流"], "data_source_type": "structured"},
        ],
    },
    {
        "section_id": "section_6",
        "name": "业内比较竞争力",
        "sub_sections": [
            {"sub_section_id": "sub_6_0", "name": "同行对比", "data_needs": ["营收排名", "市场份额对比"], "data_source_type": "both"},
            {"sub_section_id": "sub_6_1", "name": "竞争地位", "data_needs": ["竞争优势", "行业排名"], "data_source_type": "search"},
        ],
    },
    {
        "section_id": "section_7",
        "name": "投资预测",
        "sub_sections": [
            {"sub_section_id": "sub_7_0", "name": "估值", "data_needs": ["PE", "PB", "DCF估值"], "data_source_type": "both"},
            {"sub_section_id": "sub_7_1", "name": "增长预测", "data_needs": ["营收预测", "风险评估"], "data_source_type": "search"},
        ],
    },
]


def _make_mock_search_results(topic, queries):
    results = {}
    for q in queries:
        results[q] = {
            "success": True,
            "query": q,
            "results": [
                {
                    "title": f"{topic} 搜索结果",
                    "body": f"关于{q}的最新数据显示，比亚迪表现强劲。营收6800.28亿元，净利润300亿元。",
                    "href": f"https://example.com/{q}",
                    "quality_score": 75,
                }
            ],
        }
    return results


def _make_mock_stock_data():
    return {
        "company_info": {
            "success": True,
            "data": {"股票简称": "比亚迪", "行业": "汽车制造", "总股本": "29.11亿"},
            "symbol": "002594",
        },
        "financials": {
            "success": True,
            "data": {
                "income_statement": [{"营业总收入": 6800.28, "净利润": 300.41}],
                "balance_sheet": [{"总资产": 8200.0, "资产负债率": 0.62}],
                "cash_flow": [{"经营现金流": 1500.0}],
            },
            "symbol": "002594",
        },
        "key_metrics": {
            "success": True,
            "data": {"ROE": 0.21, "ROA": 0.08, "毛利率": 0.22, "净利率": 0.044, "PE": 25.3, "PB": 5.3},
            "symbol": "002594",
        },
    }


# ============================================================
# Scenario 1: 完整流水线贯通
# ============================================================

class TestE2EFullPipeline:
    """验证五阶段流水线从 intent 到最终数据的完整贯通"""

    @pytest.mark.asyncio
    async def test_full_pipeline_intent_to_supplement(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer, DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        from src.core.decomposition.strategies import (
            IndustryResearchStrategy, SectionDataSpec, SubSectionSpec,
            _convert_specs_from_dicts, validate_section_data_specs, ResearchPhase,
        )
        from src.core.communication import SharedMemory

        # === Stage 1: LLM 输出解析 ===
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.9,
            "reasoning": "比亚迪财务分析",
            "complexity": "multi",
            "section_data_specs": LLM_SECTION_DATA_SPECS,
        }
        intent_result = analyzer._build_result(
            llm_output=llm_output, model_used="test", raw_response="", used_fallback=False
        )
        assert len(intent_result.section_data_specs) == 8, \
            f"LLM 应解析 8 个 section_data_specs，实际 {len(intent_result.section_data_specs)}"
        spec0 = intent_result.section_data_specs[0]
        assert spec0["name"] == "核心指标与盈利能力"
        assert len(spec0["sub_sections"]) == 3
        assert spec0["sub_sections"][0]["data_source_type"] == "structured"

        # === Stage 1 → 2: dict → SectionDataSpec 转换 ===
        section_data_specs = _convert_specs_from_dicts(intent_result.section_data_specs)
        assert len(section_data_specs) == 8
        assert isinstance(section_data_specs[0], SectionDataSpec)
        assert section_data_specs[0].all_data_needs == ["营收", "营收增长率", "净利润", "毛利率", "净利率", "ROE", "ROA"]
        assert section_data_specs[0].search_data_needs == []
        assert section_data_specs[1].search_data_needs == ["专利数量", "技术突破"]

        # === Stage 1: validate + 验证通过 ===
        validated, valid = validate_section_data_specs(section_data_specs, BYD_ASPECTS)
        assert valid is True

        # === Stage 1: decompose 注入 data_needs ===
        strategy = IndustryResearchStrategy()

        @dataclass
        class FakeReq:
            topic: str = BYD_TOPIC
            aspects: list = field(default_factory=lambda: list(BYD_ASPECTS))

        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""):
            plan = strategy.decompose(FakeReq(), intent_result, framework_config={})

        assert len(plan.section_data_specs) == 8
        assert isinstance(plan.section_data_specs[0], SectionDataSpec)

        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) == 8

        agent_0 = dc_agents[0]
        assert "data_needs" in agent_0.context
        assert len(agent_0.context["data_needs"]) > 0
        assert agent_0.context["section_id"].startswith("section_")

        # === Stage 2: write_canonical 优先级 ===
        sm = SharedMemory()
        await sm.write_canonical("营收", 6800.28, caliber="structured_source", source="akshare", publisher="agent_0")
        result = await sm.write_canonical("营收", 6420.0, caliber="search_result", source="web", publisher="agent_3")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 6800.28, "structured_source 应优先于 search_result"
        assert entry["caliber"] == "structured_source"

        # === Stage 3: 覆盖率检查 ===
        section_1 = section_data_specs[1]  # 研发创新投资: search=[专利数量, 技术突破]
        data_points = [
            {"title": "比亚迪研发", "content": "比亚迪专利数量4万项，技术突破显著"},
        ]
        from src.core.orchestrator.execution.engine import ExecutionEngine
        _eng = ExecutionEngine.__new__(ExecutionEngine)
        covered = _eng._get_covered_needs(section_1.search_data_needs, data_points)
        assert "专利数量" in covered
        assert "技术突破" in covered

        # === Stage 3: 补充搜索 ===
        missing = [n for n in section_1.search_data_needs if n not in covered]
        assert len(missing) == 0, "搜索数据需求已全部覆盖"


# ============================================================
# Scenario 2: 查询去重验证
# ============================================================

class TestE2EQueryDedup:
    """验证共享指标（营收/ROE/资产负债率）时同一查询只搜 1 次"""

    @pytest.mark.asyncio
    async def test_shared_queries_deduplicated(self):
        from src.core.search.query_deduplicator import SearchQueryDeduplicator

        dedup = SearchQueryDeduplicator()
        call_count = 0

        search_results = {
            "比亚迪": {"success": True, "results": [{"title": "比亚迪", "body": "数据"}]},
            "比亚迪 营收": {"success": True, "results": [{"title": "营收", "body": "6800亿"}]},
            "比亚迪 ROE": {"success": True, "results": [{"title": "ROE", "body": "21%"}]},
        }

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            q = kwargs.get("query", "")
            for key, val in search_results.items():
                if key.lower() in q.lower():
                    return copy.deepcopy(val)
            return {"success": True, "results": []}

        mock_skill = MagicMock()
        mock_skill.execute = mock_execute

        result_0 = await dedup.search("比亚迪 营收 2025", "section_0", mock_skill)
        result_3 = await dedup.search("比亚迪 营收 2025", "section_3", mock_skill)
        result_4 = await dedup.search("比亚迪 ROE 2025", "section_0", mock_skill)
        result_4b = await dedup.search("比亚迪 ROE 2025", "section_4", mock_skill)

        shared = dedup.get_shared_queries()
        assert len(shared) >= 2, f"应有至少 2 个共享查询，实际 {len(shared)}"

        assert call_count == 2, \
            f"4 次搜索（2 去重对）应只调 execute 2 次，实际 {call_count} 次"

    @pytest.mark.asyncio
    async def test_different_queries_both_execute(self):
        from src.core.search.query_deduplicator import SearchQueryDeduplicator

        dedup = SearchQueryDeduplicator()
        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"success": True, "results": [{"title": kwargs.get("query", ""), "body": "data"}]}

        mock_skill = AsyncMock()
        mock_skill.execute = mock_execute

        await dedup.search("比亚迪 竞争优势", "section_6", mock_skill)
        await dedup.search("比亚迪 专利数量", "section_1", mock_skill)

        assert call_count == 2, "不同查询应各自执行一次"

    @pytest.mark.asyncio
    async def test_normalized_dedup(self):
        from src.core.search.query_deduplicator import SearchQueryDeduplicator

        dedup = SearchQueryDeduplicator()
        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"success": True, "results": []}

        mock_skill = AsyncMock()
        mock_skill.execute = mock_execute

        await dedup.search("比亚迪  营收  2025", "section_0", mock_skill)
        await dedup.search("比亚迪 营收 2025", "section_3", mock_skill)

        assert call_count == 1, "规范化后相同查询应命中缓存"


# ============================================================
# Scenario 3: 数据冲突解决
# ============================================================

class TestE2EDataConflictResolution:
    """验证 structured_source > search_result > llm_inference 优先级"""

    @pytest.mark.asyncio
    async def test_structured_beats_search_beats_llm(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()

        await sm.write_canonical("ROE", 0.21, caliber="structured_source", source="akshare", publisher="agent_0")
        entry = await sm.get_canonical("ROE")
        assert entry["value"] == 0.21

        result = await sm.write_canonical("ROE", 0.18, caliber="search_result", source="web", publisher="agent_3")
        entry = await sm.get_canonical("ROE")
        assert entry["value"] == 0.21, "search_result 不应覆盖 structured_source"
        assert entry["caliber"] == "structured_source"

        result2 = await sm.write_canonical("ROE", 0.15, caliber="llm_inference", source="gpt", publisher="agent_5")
        entry = await sm.get_canonical("ROE")
        assert entry["value"] == 0.21, "llm_inference 不应覆盖 structured_source"

    @pytest.mark.asyncio
    async def test_search_beats_llm_when_no_structured(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()

        await sm.write_canonical("竞争优势", "技术领先", caliber="search_result", source="web", publisher="agent_6")
        await sm.write_canonical("竞争优势", "品牌优势", caliber="llm_inference", source="gpt", publisher="agent_7")
        entry = await sm.get_canonical("竞争优势")
        assert entry["value"] == "技术领先", "search_result 应优先于 llm_inference"

    @pytest.mark.asyncio
    async def test_same_priority_allows_update(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()

        await sm.write_canonical("营收", 6800.28, caliber="structured_source", source="akshare_q2", publisher="agent_0")
        await sm.write_canonical("营收", 7200.50, caliber="structured_source", source="akshare_q3", publisher="agent_0")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 7200.50, "同优先级应允许更新（取最新值）"

    @pytest.mark.asyncio
    async def test_non_numeric_value_no_crash(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()
        await sm.write_canonical("竞争优势", "技术领先", caliber="search_result", source="web", publisher="a0")
        result = await sm.write_canonical("竞争优势", "成本优势", caliber="search_result", source="web2", publisher="a1")
        entry = await sm.get_canonical("竞争优势")
        assert entry["value"] == "成本优势"

    @pytest.mark.asyncio
    async def test_numeric_conflict_detection(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()
        await sm.write_canonical("营收", 6800.28, caliber="search_result", source="web1", publisher="a0")
        await sm.write_canonical("营收", 130.0, caliber="search_result", source="web2", publisher="a1")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 130.0, "同优先级允许覆盖"


# ============================================================
# Scenario 4: 覆盖率补充闭环
# ============================================================

class TestE2ECoverageSupplement:
    """验证 data_needs 覆盖率检查 + 补充搜索闭环"""

    def test_coverage_below_threshold_triggers_supplement(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts, SectionDataSpec

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)
        section_1 = specs[1]  # 研发创新投资: search_data_needs = [专利数量, 技术突破]

        data_points = [
            {"title": "比亚迪研发投入", "content": "比亚迪研发费用200亿元"},
        ]

        from src.core.orchestrator.execution.engine import ExecutionEngine
        _eng = ExecutionEngine.__new__(ExecutionEngine)
        covered = _eng._get_covered_needs(section_1.search_data_needs, data_points)
        total_search_needs = section_1.search_data_needs
        coverage = len(covered) / max(len(total_search_needs), 1)

        assert coverage < 0.8, f"覆盖率 {coverage:.0%} 应低于 80% 阈值"
        missing = [n for n in total_search_needs if n not in covered]
        assert "专利数量" in missing
        assert "技术突破" in missing

    def test_coverage_above_threshold_no_supplement(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)
        section_2 = specs[2]  # 供应成本效率: search_data_needs = [供应商集中度, 原材料成本]

        data_points = [
            {"title": "供应链分析", "content": "供应商集中度较高，原材料成本持续上涨，营业成本增加，成本率优化"},
        ]

        from src.core.orchestrator.execution.engine import ExecutionEngine
        _eng = ExecutionEngine.__new__(ExecutionEngine)
        covered = _eng._get_covered_needs(section_2.search_data_needs, data_points)
        total_search_needs = section_2.search_data_needs
        coverage = len(covered) / max(len(total_search_needs), 1)

        assert coverage >= 0.8, f"覆盖率 {coverage:.0%} 应达到 80% 阈值"

    def test_shared_need_supplement_injects_into_multiple_sections(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts, SectionDataSpec

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)

        all_needs_map = {}
        for spec in specs:
            for need in spec.all_data_needs:
                all_needs_map.setdefault(need, []).append(spec.section_id)

        shared_needs = {k: v for k, v in all_needs_map.items() if len(v) > 1}
        assert "营收" in shared_needs, "营收应被 section_0 和 section_3 共享"
        assert len(shared_needs["营收"]) == 2
        assert "ROE" in shared_needs, "ROE 应被 section_0 和 section_4 共享"
        assert "资产负债率" in shared_needs, "资产负债率应被 section_4 和 section_5 共享"

    @pytest.mark.asyncio
    async def test_supplement_data_injected_into_correct_agents(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)

        all_results = [
            {"agent_id": "dc_section_0", "data_points": [{"title": "比亚迪", "content": "营收6800亿 ROE 21%"}], "sources": []},
            {"agent_id": "dc_section_1", "data_points": [], "sources": []},
            {"agent_id": "dc_section_6", "data_points": [{"title": "竞争", "content": "市场份额对比分析"}], "sources": []},
        ]

        supplement_data = {
            "专利数量": {"data_points": [{"title": "专利", "content": "比亚迪专利数量4万项"}], "sources": []},
            "技术突破": {"data_points": [{"title": "技术", "content": "刀片电池技术突破"}], "sources": []},
        }

        for need, supp in supplement_data.items():
            for result in all_results:
                aid = result.get("agent_id", "")
                sec_idx = int(aid.split("_")[-1]) if "_" in aid else -1
                if sec_idx < 0 or sec_idx >= len(specs):
                    continue
                spec = specs[sec_idx]
                if need in spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
                    result.setdefault("sources", []).extend(supp["sources"])

        assert len(all_results[1]["data_points"]) == 2, \
            "section_1 应收到专利数量和技术突破的补充数据"
        assert len(all_results[0]["data_points"]) == 1, \
            "section_0 不需要专利数量/技术突破，不应收到补充"

    def test_multi_round_supplement_converges(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)
        section_1 = specs[1]

        from src.core.orchestrator.execution.engine import ExecutionEngine
        _eng = ExecutionEngine.__new__(ExecutionEngine)

        dp_round0 = []
        covered_0 = _eng._get_covered_needs(section_1.search_data_needs, dp_round0)
        cov_0 = len(covered_0) / max(len(section_1.search_data_needs), 1)

        dp_round1 = [{"title": "专利", "content": "比亚迪专利数量4万项"}]
        covered_1 = _eng._get_covered_needs(section_1.search_data_needs, dp_round1)
        cov_1 = len(covered_1) / max(len(section_1.search_data_needs), 1)

        dp_round2 = dp_round1 + [{"title": "技术", "content": "刀片电池技术突破领先"}]
        covered_2 = _eng._get_covered_needs(section_1.search_data_needs, dp_round2)
        cov_2 = len(covered_2) / max(len(section_1.search_data_needs), 1)

        assert cov_0 < cov_1 < cov_2, f"覆盖率应单调递增: {cov_0:.0%} < {cov_1:.0%} < {cov_2:.0%}"
        assert cov_2 >= 0.8, f"2 轮补充后覆盖率应 ≥ 80%，实际 {cov_2:.0%}"


# ============================================================
# Scenario 5: Fallback 路径
# ============================================================

class TestE2EFallbackPath:
    """验证 LLM 不返回 section_data_specs 时退化到 1 级框架"""

    def test_llm_no_specs_fallback(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer
        from src.core.decomposition.strategies import validate_section_data_specs, _fallback_specs_from_names

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.7,
            "reasoning": "test",
            "complexity": "single",
        }
        intent_result = analyzer._build_result(
            llm_output=llm_output, model_used="test", raw_response="", used_fallback=False
        )
        assert intent_result.section_data_specs == []

        fallback_specs = _fallback_specs_from_names(BYD_ASPECTS)
        assert len(fallback_specs) == 8
        for spec in fallback_specs:
            assert len(spec.sub_sections) == 1
            assert spec.sub_sections[0].data_source_type == "search"
            assert len(spec.sub_sections[0].data_needs) == 1

        validated, valid = validate_section_data_specs(fallback_specs, BYD_ASPECTS)
        assert valid is True

    def test_llm_malformed_specs_fallback(self):
        from src.core.decomposition.strategies import (
            _convert_specs_from_dicts, validate_section_data_specs, _fallback_specs_from_names
        )

        malformed = [
            {"section_id": "section_0", "name": "Test"},
            "not_a_dict",
            {"bad_key": "no_section_id"},
        ]
        specs = _convert_specs_from_dicts(malformed)
        assert len(specs) >= 1

        validated, valid = validate_section_data_specs(specs, BYD_ASPECTS)
        assert valid is False or len(specs) != len(BYD_ASPECTS)

    def test_llm_partial_specs_mixed(self):
        from src.core.decomposition.strategies import (
            _convert_specs_from_dicts, validate_section_data_specs, _fallback_specs_from_names,
            SectionDataSpec, SubSectionSpec,
        )

        partial = [
            {
                "section_id": "section_0",
                "name": "核心指标与盈利能力",
                "sub_sections": [
                    {"sub_section_id": "sub_0_0", "name": "营收", "data_needs": ["营收", "ROE"], "data_source_type": "structured"},
                ],
            },
        ]
        specs = _convert_specs_from_dicts(partial)
        assert len(specs) == 1
        assert specs[0].all_data_needs == ["营收", "ROE"]

        validated, valid = validate_section_data_specs(specs, BYD_ASPECTS)
        assert valid is False, "1 个 spec vs 8 个 aspects 应不匹配"

        fallback = _fallback_specs_from_names(BYD_ASPECTS)
        assert len(fallback) == 8

    def test_keyword_fallback_intent_analyzer(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer, DeepIntentResult

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        result = analyzer._analyze_with_keyword("分析比亚迪公司财务", {"topic": "比亚迪", "aspects": []})
        assert isinstance(result, DeepIntentResult)
        assert result.used_fallback is True
        assert result.section_data_specs == []

    @pytest.mark.asyncio
    async def test_decompose_with_no_specs_uses_empty_data_needs(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity

        intent_result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.7,
            intent_reasoning="fallback",
            complexity=TaskComplexity.MULTI,
            section_data_specs=[],
        )

        @dataclass
        class FakeReq:
            topic: str = BYD_TOPIC
            aspects: list = field(default_factory=lambda: list(BYD_ASPECTS))

        strategy = IndustryResearchStrategy()
        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""):
            plan = strategy.decompose(FakeReq(), intent_result, framework_config={})

        from src.core.decomposition.strategies import ResearchPhase
        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) == 8

        agent_0 = dc_agents[0]
        data_needs = agent_0.context.get("data_needs", [])
        assert isinstance(data_needs, list), "无 section_data_specs 时 data_needs 应为列表"
        assert len(data_needs) >= 1, "无 specs 时应使用 aspect 名称作为 fallback data_need"


# ============================================================
# Scenario 6: 完整 Stage 0 数据源路由
# ============================================================

class TestE2EStage0DataRouting:
    """验证数据源路由：财务维度走 structured，竞争维度走 search"""

    def test_financial_aspect_gets_stock_data_skill(self):
        from src.core.decomposition.strategies import _get_data_collection_skills

        skills = _get_data_collection_skills("Financial Analysis", BYD_TOPIC)
        assert "stock_data" in skills
        assert "search_skill" in skills

    def test_competitive_aspect_no_stock_data(self):
        from src.core.decomposition.strategies import _get_data_collection_skills

        skills = _get_data_collection_skills("Competitive Landscape", BYD_TOPIC)
        assert "stock_data" not in skills
        assert "search_skill" in skills

    def test_infer_stock_actions_matches_skill_interface(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        actions = agent._infer_stock_actions("财务分析")
        valid_actions = {"company_info", "financials", "key_metrics", "price_history", "industry_comparison"}
        for action in actions:
            assert action in valid_actions, f"action '{action}' 不在 StockDataSkill 支持列表中"

    def test_infer_stock_actions_default_fallback(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        actions = agent._infer_stock_actions("unknown aspect")
        assert len(actions) >= 1, "未知 aspect 应有默认 action"
        valid_actions = {"company_info", "financials", "key_metrics", "price_history", "industry_comparison"}
        for action in actions:
            assert action in valid_actions


# ============================================================
# Scenario 7: 跨章节一致性验证
# ============================================================

class TestE2ECrossSectionConsistency:
    """验证同一指标（营收/ROE）跨章节值一致"""

    @pytest.mark.asyncio
    async def test_shared_metric_consistent_across_sections(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()

        await sm.write_canonical("营收", 6800.28, caliber="structured_source", source="akshare", publisher="agent_0")

        for agent_id in ["agent_0", "agent_3", "agent_6"]:
            entry = await sm.get_canonical("营收")
            assert entry is not None, f"agent {agent_id} 应能读取营收"
            assert entry["value"] == 6800.28, f"agent {agent_id} 读取的营收应为 6800.28"

        result = await sm.write_canonical("营收", 6420.0, caliber="search_result", source="web3", publisher="agent_3")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 6800.28, "搜索结果不应覆盖结构化数据源"

    @pytest.mark.asyncio
    async def test_roe_shared_between_sections(self):
        from src.core.communication import SharedMemory

        sm = SharedMemory()

        await sm.write_canonical("ROE", 0.21, caliber="structured_source", source="akshare", publisher="agent_0")

        entry_0 = await sm.get_canonical("ROE")
        assert entry_0["value"] == 0.21

        await sm.write_canonical("ROE", 0.18, caliber="search_result", source="web", publisher="agent_4")
        entry_4 = await sm.get_canonical("ROE")
        assert entry_4["value"] == 0.21, "section_4 读到的 ROE 应与 section_0 一致"


# ============================================================
# Scenario 8: 搜索查询质量
# ============================================================

class TestE2ESearchQueryQuality:
    """验证搜索查询覆盖各章节 data_needs，而非通用 data_focus"""

    def test_search_data_needs_only_for_search_type(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)
        section_0 = specs[0]

        assert section_0.search_data_needs == [], \
            f"section_0 全部 structured，search_data_needs 应为空，实际 {section_0.search_data_needs}"

        section_1 = specs[1]
        assert section_1.search_data_needs == ["专利数量", "技术突破"], \
            f"section_1 只有 search 类型的 need 应出现在 search_data_needs"

    def test_structured_needs_not_in_search_queries(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)

        pure_structured = set()
        pure_search = set()
        for spec in specs:
            for sub in spec.sub_sections:
                if sub.data_source_type == "structured":
                    pure_structured.update(sub.data_needs)
                elif sub.data_source_type == "search":
                    pure_search.update(sub.data_needs)

        overlap = pure_structured & pure_search
        assert len(overlap) == 0, \
            f"纯 structured 和纯 search 的 need 不应重叠: {overlap}"

    def test_no_generic_data_focus_queries(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts

        specs = _convert_specs_from_dicts(LLM_SECTION_DATA_SPECS)
        all_search_needs = set()
        for spec in specs:
            for sub in spec.sub_sections:
                if sub.data_source_type in ("search",):
                    all_search_needs.update(sub.data_needs)

        generic_terms = {"市场规模", "增长率", "消费者数据"}
        overlap = all_search_needs & generic_terms
        assert len(overlap) == 0, \
            f"search 类型 need 不应包含通用 data_focus 查询: {overlap}"
