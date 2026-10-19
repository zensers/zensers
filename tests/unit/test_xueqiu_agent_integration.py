"""
XueqiuSkill GenericAgent 集成测试 — Phase 3

测试覆盖：
1. _infer_xueqiu_actions 对标准 A 股代码返回 quote + kline
2. _infer_xueqiu_actions 对非标准代码返回 search_and_quote
3. _infer_xueqiu_actions 对中文公司名返回 search_and_quote
4. _infer_xueqiu_actions 对竞争类 aspect 额外添加 hot_stocks
5. GenericAgent resolves non-A-share topics through the xueqiu manifest
6. The resolved topic is passed as the search query
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestInferXueqiuActions:
    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        from pathlib import Path
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        from src.skills.discovery import SkillDiscovery

        config = {
            "agent_id": "test_xueqiu_agent",
            "agent_type": "research",
            "name": "Test Xueqiu Agent",
            "skills": ["xueqiu"],
            "category": "research",
        }
        agent = GenericAgent(config)
        manifest = next(item for item in SkillDiscovery().discover_all(Path("src/skills")) if item.name == "xueqiu")
        skill = XueqiuSkill()
        skill._manifest = manifest
        return skill

    def test_a_share_code_returns_quote(self, agent):
        actions = agent.infer_actions("财务分析", "002594")
        assert "quote" in actions

    def test_a_share_code_with_financial_aspect_adds_kline(self, agent):
        actions = agent.infer_actions("估值分析", "SH600519")
        assert "quote" in actions
        assert "kline" in actions

    def test_non_standard_code_returns_search_and_quote(self, agent):
        actions = agent.infer_actions("估值分析", "00700")
        assert actions == ["search_and_quote"]

    def test_chinese_name_returns_search_and_quote(self, agent):
        actions = agent.infer_actions("估值分析", "腾讯控股")
        assert actions == ["search_and_quote"]

    def test_us_stock_returns_search_and_quote(self, agent):
        actions = agent.infer_actions("估值分析", "AAPL")
        assert actions == ["search_and_quote"]

    def test_competitive_aspect_adds_hot_stocks(self, agent):
        actions = agent.infer_actions("竞争格局", "SH600519")
        assert "hot_stocks" in actions

    def test_default_action_is_quote(self, agent):
        actions = agent.infer_actions("公司概况", "SH600519")
        assert "quote" in actions

    def test_no_financials_action(self, agent):
        actions = agent.infer_actions("财务分析", "SH600519")
        assert "financials" not in actions
        assert "company_info" not in actions


class TestXueqiuTopicFallback:
    def test_non_a_share_topic_uses_manifest_fallback(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path

        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {}
        agent._extract_stock_symbol = MagicMock(return_value="")
        agent._resolve_company_to_code = MagicMock(return_value="")
        registry = MagicMock()
        manifest = next(item for item in SkillDiscovery().discover_all(Path("src/skills")) if item.name == "xueqiu")
        skill = XueqiuSkill()
        registry.get_manifest.return_value = manifest
        registry.get.return_value = skill

        identifiers = agent._resolve_identifiers("xueqiu", "腾讯控股估值分析", "估值分析", registry)
        assert identifiers == ["腾讯控股估值分析"]
        actions = agent._infer_actions_from_manifest(manifest, skill, "估值分析", identifiers[0])
        assert actions == ["search_and_quote"]
        assert agent._build_execute_kwargs(manifest, actions[0], identifiers[0], "腾讯控股估值分析") == {
            "action": "search_and_quote", "query": "腾讯控股估值分析"
        }
