import sys
sys.path.insert(0, "src")

import pytest
from unittest.mock import MagicMock, patch
from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent, SECTION_ELEMENT_REQUIREMENTS


class TestLayer1SectionScore:

    def _score(self, content, issues, section_type):
        agent = QualityCheckAgent(agent_id="test_agent", config={})
        return agent._calculate_section_score(content, issues, section_type)

    def test_market_size_full_score(self):
        content = (
            "当前市场规模约为5000亿元。增速保持在15%以上。"
            "其中新能源占比30%，传统能源占70%。"
            "主要驱动因素包括政策支持和技术进步。"
            "交叉验证显示数据可信。预计2025年将达8000亿元。"
            "不确定性主要来自原材料价格波动。"
        )
        score = self._score(content, [], "market_size")
        assert score >= 60

    def test_empty_content_low_score(self):
        score = self._score("", [], "market_size")
        assert score <= 30

    def test_no_elements_penalty(self):
        content = "这是一段没有分析要素的文本，只有简单描述。这里没有任何专业分析内容。"
        score = self._score(content, [], "market_size")
        assert score < 50

    def test_competition_elements_scored(self):
        content = (
            "竞争格局方面，前五大企业市占率总计65%。"
            "其中龙头企业凭借技术壁垒保持领先。"
            "波特五力分析显示供应商议价能力较强。"
            "主要竞争对手的战略布局各有侧重。"
            "行业集中度呈上升趋势。市场壁垒较高。"
        )
        score = self._score(content, [], "competition")
        assert score >= 50

    def test_fallback_to_generic_when_type_unknown(self):
        content = (
            "核心判断：市场前景向好，预计未来三年保持增长。"
            "逻辑推导：需求持续增长推动行业扩张。"
            "数据支持：2023年销售额500亿元，同比增长15%。"
            "反证方面：但也需关注替代技术带来的潜在冲击。"
            "意义：这对投资决策具有重要参考价值。"
        )
        score = self._score(content, [], "unknown_section_type")
        assert score >= 40

    def test_issues_reduce_score(self):
        content = (
            "当前市场规模约为5000亿元。增速保持在15%以上。"
            "其中新能源占比30%。驱动因素包括政策支持。"
            "预计2025年将达8000亿元。"
        )
        issues = [
            {"type": "accuracy", "severity": "high", "message": "数据矛盾"},
            {"type": "completeness", "severity": "medium", "message": "缺少反证"},
        ]
        score_clean = self._score(content, [], "market_size")
        score_with_issues = self._score(content, issues, "market_size")
        assert score_with_issues < score_clean

    def test_section_type_auto_detected(self):
        content = (
            "当前市场规模约为5000亿元。增速保持在15%以上。"
            "其中新能源占比30%。驱动因素包括政策支持。"
        )
        score = self._score(content, [], "market_size")
        assert 0 <= score <= 100


class TestPerAgentStats:

    @pytest.mark.asyncio
    async def test_agent_stats_in_output(self):
        agent = QualityCheckAgent(agent_id="qc_agent", config={})
        sections = [
            {"title": "市场规模", "content": "规模5000亿，增速15%。",
             "agent_id": "agent_market_size"},
            {"title": "竞争格局", "content": "前五名市占率65%。",
             "agent_id": "agent_competition"},
        ]
        result = await agent.check_by_sections(sections)
        assert "agent_stats" in result
        assert isinstance(result["agent_stats"], dict)

    @pytest.mark.asyncio
    async def test_agent_stats_tracks_scores(self):
        agent = QualityCheckAgent(agent_id="qc_agent", config={})
        sections = [
            {"title": "市场规模", "content": "规模5000亿，增速15%。",
             "agent_id": "agent_market_size"},
            {"title": "竞争格局", "content": "前五名市占率65%。",
             "agent_id": "agent_competition"},
        ]
        result = await agent.check_by_sections(sections)
        stats = result["agent_stats"]
        assert "agent_market_size" in stats
        assert "agent_competition" in stats
        assert "score" in stats["agent_market_size"]
        assert "section" in stats["agent_market_size"]

    @pytest.mark.asyncio
    async def test_agent_stats_unknown_when_no_agent_id(self):
        agent = QualityCheckAgent(agent_id="qc_agent", config={})
        sections = [
            {"title": "市场规模", "content": "规模5000亿，增速15%。"},
        ]
        result = await agent.check_by_sections(sections)
        stats = result["agent_stats"]
        assert "unknown" in stats

    @pytest.mark.asyncio
    async def test_agent_stats_empty_for_no_sections(self):
        agent = QualityCheckAgent(agent_id="qc_agent", config={})
        result = await agent.check_by_sections([])
        assert result["agent_stats"] == {}
