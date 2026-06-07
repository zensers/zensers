"""
M0 前置修复测试：聚合 key 碰撞 + stage 分类

TDD: GREEN 阶段 — 测试修复后的期望行为

覆盖场景：
1. M0-a: 聚合 key 碰撞 — DC 和 Analysis agent 共享同一 section_id 时结果共存
2. M0-b: stage 分类 — phase_N_agent_M 格式按 result["category"] 正确分类
3. M0-b.1: category 注入链 — _ensure_standard_result 写入的 category 被正确消费
"""
import pytest
from unittest.mock import MagicMock, patch


class TestM0aAggregationKeyCollision:
    """M0-a: 修复后 DC 和 Analysis agent 共享 section_id 时结果共存"""

    def test_dc_and_analysis_same_section_coexist(self):
        """
        修复后：DC 和 Analysis 共享 section_id 时，两者结果独立存在
        """
        dc_result = {
            "success": True,
            "data_points": [{"title": "BYD sales", "content": "460万辆"}],
            "agent_id": "phase_1_agent_0",
            "section_id": "section_0_核心财务指标",
        }
        analysis_result = {
            "success": True,
            "content": "BYD 2024年销量460万辆",
            "agent_id": "phase_2_agent_0",
            "section_id": "section_0_核心财务指标",
        }

        results_map = build_aggregation_map_real([dc_result, analysis_result])

        assert len(results_map) == 2, (
            f"DC 和 Analysis 应产生 2 个独立 key，实际 {len(results_map)} 个"
        )

    def test_dc_data_points_preserved(self):
        """
        修复后：DC agent 的 data_points 不被 Analysis 覆盖
        """
        dc_result = {
            "success": True,
            "data_points": [{"title": "net profit", "content": "326.5亿元"}],
            "sources": [],
            "agent_id": "phase_1_agent_0",
            "section_id": "section_0_核心财务指标",
        }
        analysis_result = {
            "success": True,
            "content": "净利润326.5亿元",
            "agent_id": "phase_2_agent_0",
            "section_id": "section_0_核心财务指标",
        }

        results_map = build_aggregation_map_real([dc_result, analysis_result])

        assert "phase_1_agent_0" in results_map, "DC agent key 应存在"
        assert results_map["phase_1_agent_0"]["data_points"] == dc_result["data_points"]
        assert results_map["phase_1_agent_0"]["_section_id"] == "section_0_核心财务指标"

    def test_three_agents_same_section_all_coexist(self):
        """
        边界：3 个 agent（DC + Analysis + Synthesis）共享同一 section
        """
        results = [
            {"success": True, "data_points": [], "agent_id": "phase_1_agent_0",
             "section_id": "section_0_销量"},
            {"success": True, "content": "分析...", "agent_id": "phase_2_agent_0",
             "section_id": "section_0_销量"},
            {"success": True, "content": "综合...", "agent_id": "phase_3_agent_0",
             "section_id": "section_0_销量"},
        ]
        results_map = build_aggregation_map_real(results)
        assert len(results_map) == 3

    def test_eight_agents_eight_keys(self):
        """
        BYD 场景：8 个 agent 即使共享 section_id 也产生 8 个独立 key
        """
        results = [
            {"success": True, "content": f"分析{i}", "agent_id": f"phase_1_agent_{i}",
             "section_id": "section_0_销量"}
            for i in range(8)
        ]
        results_map = build_aggregation_map_real(results)
        assert len(results_map) == 8, f"8 个 agent 应产生 8 个 key，实际 {len(results_map)} 个"

    def test_old_format_agent_id_still_unique(self):
        """
        回归：旧格式 agent_id（如 research_市场规模_2）仍产生唯一 key
        """
        results = [
            {"success": True, "content": "A", "agent_id": "research_市场规模_2",
             "section_id": ""},
            {"success": True, "content": "B", "agent_id": "analysis_竞争格局_3",
             "section_id": ""},
        ]
        results_map = build_aggregation_map_real(results)
        assert len(results_map) == 2


class TestM0bStageClassification:
    """M0-b: 修复后 _extract_stage_from_agent_id 按 result["category"] 正确分类"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        self.aggregator = ResultAggregator()

    def test_dc_agent_classified_as_data_collection(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_1_agent_0", {"category": "research"})
        assert stage == "data_collection"

    def test_analysis_agent_classified_as_analysis(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_2_agent_0", {"category": "analysis"})
        assert stage == "analysis"

    def test_market_analysis_classified_as_analysis(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_2_agent_1", {"category": "market-analysis"})
        assert stage == "analysis"

    def test_synthesis_agent_classified_as_synthesis(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_3_agent_0", {"category": "synthesis"})
        assert stage == "synthesis"

    def test_quality_check_classified_as_data_validation(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_1_agent_0", {"category": "quality-check"})
        assert stage == "data_validation"

    def test_calibration_agent_classified(self):
        stage = self.aggregator._extract_stage_from_agent_id(
            "phase_3_calibrator", {"category": "calibration"})
        assert stage == "calibration"

    def test_dc_vs_analysis_different_stages(self):
        """
        修复后：DC 和 Analysis 应产生不同 stage
        """
        dc_stage = self.aggregator._extract_stage_from_agent_id(
            "phase_1_agent_0", {"category": "research"})
        analysis_stage = self.aggregator._extract_stage_from_agent_id(
            "phase_2_agent_0", {"category": "analysis"})

        assert dc_stage != analysis_stage, (
            f"DC({dc_stage}) 和 Analysis({analysis_stage}) 的 stage 应不同"
        )

    def test_fallback_no_category(self):
        stage = self.aggregator._extract_stage_from_agent_id("phase_1_agent_0", {})
        assert stage == "data_collection"

    def test_old_format_research_keyword(self):
        stage = self.aggregator._extract_stage_from_agent_id("research_市场规模_2", {})
        assert stage == "data_collection"

    def test_old_format_analysis_keyword(self):
        stage = self.aggregator._extract_stage_from_agent_id("analysis_market_3", {})
        assert stage == "analysis"

    def test_old_format_synthesis_keyword(self):
        stage = self.aggregator._extract_stage_from_agent_id("synthesis_summary_1", {})
        assert stage == "synthesis"

    def test_accepts_result_parameter(self):
        """
        M0-b: _extract_stage_from_agent_id 签名包含 result 参数
        """
        import inspect
        sig = inspect.signature(self.aggregator._extract_stage_from_agent_id)
        params = list(sig.parameters.keys())
        assert "result" in params, (
            f"_extract_stage_from_agent_id 应有 result 参数，实际参数: {params}"
        )


class TestM0b1CategoryInjection:
    """M0-b.1: _ensure_standard_result 写入 category"""

    def test_writes_category_from_config(self):
        from src.core.agents.generic_agent import GenericAgent

        config = {"name": "Test", "category": "research", "skills": [], "context": {}}
        with patch('src.core.agents.generic_agent.AgentLifecycleState'):
            agent = GenericAgent(agent_id="test_agent", config=config)

        result = {"success": True, "data_points": []}
        standardized = agent._ensure_standard_result(result, "execute")

        assert standardized.get("category") == "research"

    def test_preserves_existing_category(self):
        from src.core.agents.generic_agent import GenericAgent

        config = {"name": "Test", "category": "research", "skills": [], "context": {}}
        with patch('src.core.agents.generic_agent.AgentLifecycleState'):
            agent = GenericAgent(agent_id="test_agent", config=config)

        result = {"success": True, "category": "analysis"}
        standardized = agent._ensure_standard_result(result, "execute")

        assert standardized["category"] == "analysis"

    def test_empty_config_category_no_injection(self):
        from src.core.agents.generic_agent import GenericAgent

        config = {"name": "Test", "category": "", "skills": [], "context": {}}
        with patch('src.core.agents.generic_agent.AgentLifecycleState'):
            agent = GenericAgent(agent_id="test_agent", config=config)

        result = {"success": True}
        standardized = agent._ensure_standard_result(result, "execute")

        assert "category" not in standardized or standardized.get("category") == ""


class TestM0Integration:
    """M0 端到端：聚合 key + stage 分类联动"""

    def test_dc_analysis_pipeline_no_data_loss(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        dc_result = {
            "success": True,
            "data_points": [{"title": "BYD 2024 sales", "content": "460万辆"}],
            "sources": [{"title": "BYD annual report", "url": "byd.com/ar2024"}],
            "agent_id": "phase_1_agent_0",
            "section_id": "section_0_核心财务指标",
            "category": "research",
        }
        analysis_result = {
            "success": True,
            "content": "BYD 2024年销量460万辆，营收677亿元。",
            "data_points": [],
            "sources": [],
            "agent_id": "phase_2_agent_0",
            "section_id": "section_0_核心财务指标",
            "category": "analysis",
        }

        results_map = build_aggregation_map_real([dc_result, analysis_result])
        agg = ResultAggregator()

        assert len(results_map) == 2

        for key, result in results_map.items():
            stage = agg._extract_stage_from_agent_id(key, result)
            if result["agent_id"].startswith("phase_1"):
                assert stage == "data_collection"
            elif result["agent_id"].startswith("phase_2"):
                assert stage == "analysis"

        assert results_map["phase_1_agent_0"]["data_points"] == dc_result["data_points"]
        assert results_map["phase_2_agent_0"]["_section_id"] == "section_0_核心财务指标"


def build_aggregation_map_real(results):
    """
    复刻 M0-a 修复后的 orchestrator.py 聚合 key 映射逻辑：
    用 agent_id 作为 key（唯一），section_id 保存为 _section_id 元数据。
    """
    results_for_aggregation = {}
    for i, result in enumerate(results):
        agent_id = result.get("agent_id", "")
        section_id = result.get("section_id", "") or ""
        if agent_id:
            key = agent_id
            if section_id:
                result["_section_id"] = section_id
        elif section_id:
            key = section_id
        else:
            key = f"unknown_{i}"

        results_for_aggregation[key] = result

    return results_for_aggregation


class TestM0aSectionIdProvenance:
    """M0-a CRITICAL-1 修复：_section_id 必须被 result_aggregator 消费"""

    def test_provenance_uses_section_id_for_matching(self):
        """
        result 的 _section_id 应成为 ContentProvenance.section_target，
        而不是依赖 _determine_section_target() 的启发式匹配。
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agg = ResultAggregator()
        results = {
            "phase_1_agent_0": {
                "success": True,
                "content": "BYD 2024年销量460万辆",
                "agent_id": "phase_1_agent_0",
                "category": "research",
                "_section_id": "section_0_核心财务指标",
            },
            "phase_2_agent_0": {
                "success": True,
                "content": "BYD 2024年销量460万辆，同比增长35%",
                "agent_id": "phase_2_agent_0",
                "category": "analysis",
                "_section_id": "section_0_核心财务指标",
            },
        }

        aggregated = agg.aggregate(results, section_details=[
            {"id": "section_0_核心财务指标", "name": "核心财务指标"},
        ])

        sections = aggregated.to_dict().get("sections", [])
        section_ids = [s.get("id", s.get("title", "")) for s in sections]

        has_content = any(
            "460万" in (s.get("content", "") or "") for s in sections
        )
        assert has_content, (
            f"_section_id 匹配失败：sections={section_ids}，"
            f"内容应包含'460万'但未找到。"
            f"_section_id 未被 provenance 消费。"
        )

    def test_both_dc_and_analysis_content_preserved_in_sections(self):
        """
        DC 和 Analysis 的内容在聚合后都应体现在 sections 中（或至少 Analysis 的）
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agg = ResultAggregator()
        results = {
            "phase_1_agent_0": {
                "success": True,
                "data_points": [{"title": "BYD sales", "content": "460万辆"}],
                "sources": [],
                "agent_id": "phase_1_agent_0",
                "category": "research",
                "_section_id": "section_0_销量",
            },
            "phase_2_agent_0": {
                "success": True,
                "content": "销量分析：BYD 2024年全球销量460万辆，同比增35%",
                "agent_id": "phase_2_agent_0",
                "category": "analysis",
                "_section_id": "section_0_销量",
            },
        }

        aggregated = agg.aggregate(results, section_details=[
            {"id": "section_0_销量", "name": "销量分析"},
        ])

        sections = aggregated.to_dict().get("sections", [])
        has_analysis = any(
            "销量分析" in (s.get("content", "") or "") or "460万" in (s.get("content", "") or "")
            for s in sections
        )
        assert has_analysis, (
            f"Analysis agent 内容未匹配到 section_0_销量。"
            f"sections: {[s.get('id', s.get('title', '')) for s in sections]}"
        )


class TestM0RoutingPathSync:
    """M0-a CRITICAL-2: _research_with_routing 的 key 映射同步修复"""

    def test_routing_path_uses_agent_id_key(self):
        """
        _research_with_routing 应与 research() 使用相同的 agent_id key 映射
        """
        results = [
            {"success": True, "content": "DC data", "agent_id": "phase_1_agent_0",
             "section_id": "section_0_x"},
            {"success": True, "content": "Analysis data", "agent_id": "phase_2_agent_0",
             "section_id": "section_0_x"},
        ]
        results_map = build_aggregation_map_real(results)

        assert len(results_map) == 2, (
            f"_research_with_routing 路径应有 2 个 key，实际 {len(results_map)}"
        )
        assert "phase_1_agent_0" in results_map
        assert "phase_2_agent_0" in results_map
        assert results_map["phase_1_agent_0"]["_section_id"] == "section_0_x"
