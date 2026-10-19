"""
Real business scenario test: LLM-based data summarization in the skill pipeline.

Tests that _llm_summarize_data works correctly with real LLM calls,
and that the full _process_skill_output pipeline produces correct output
when L3 (LLM summarization) is triggered.
"""
import os
os.chdir("E:/market_report_systerm")
from dotenv import load_dotenv
load_dotenv(".env")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path


def _create_real_registry():
    from src.skills.registry import SkillRegistry
    from src.skills.discovery import SkillDiscovery
    registry = SkillRegistry()
    discovery = SkillDiscovery()
    manifests = discovery.discover_all(Path("src/skills"))
    registry._manifests = {m.name: m for m in manifests}
    registries = discovery.build_registries(manifests)
    registry._registries = registries
    registry._factories = {}
    registry._skills = {}
    return registry, manifests


class TestLLMSummarizeDataReal:
    """Test _llm_summarize_data with real LLM calls."""

    @pytest.mark.asyncio
    async def test_llm_summarize_stock_data(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_llm", agent_type="dynamic", config={})

        data = {
            "income_statement": [
                {"REPORT_DATE": "2024-03-31", "NET_PROFIT": 1500000000, "OPERATE_INCOME": 5000000000},
                {"REPORT_DATE": "2023-12-31", "NET_PROFIT": 1400000000, "OPERATE_INCOME": 4800000000},
            ],
        }
        summary = await agent._llm_summarize_data(
            data, "stock_data", "financials", "贵州茅台"
        )
        assert summary, "LLM should produce a non-empty summary"
        assert len(summary) < 1000, "Summary should be concise"

    @pytest.mark.asyncio
    async def test_llm_summarize_xueqiu_data(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_llm", agent_type="dynamic", config={})

        data = {
            "records": [
                {"name": "贵州茅台", "symbol": "SH600519", "current": 1800.5, "percent": 1.5, "market_capital": "2.2万亿"},
            ]
        }
        summary = await agent._llm_summarize_data(
            data, "xueqiu", "quote", "贵州茅台"
        )
        assert summary, "LLM should produce a non-empty summary for xueqiu data"


class TestProcessSkillOutputWithLLM:
    """Test the full _process_skill_output pipeline when L3 (LLM) is triggered."""

    @pytest.mark.asyncio
    async def test_web_search_skill_data_goes_through_llm(self):
        """When a web_search skill returns data without format_data,
        L3 LLM summarization should be triggered."""
        from src.core.agents.generic_agent import GenericAgent
        registry, manifests = _create_real_registry()

        class MockWebSkill:
            name = "mock_web_skill"
            async def execute(self, **kwargs):
                return {
                    "success": True,
                    "data": {"market_info": "白酒行业2024年规模达6000亿，同比增长8%。龙头茅台市占率3%。"},
                    "content": "",
                }

        skill = MockWebSkill()
        mock_manifest = MagicMock()
        mock_manifest.priority = "web_search"
        mock_manifest.action_rules = []
        mock_manifest.action_param_map = {}
        mock_manifest.capabilities = ["fetch"]

        original_get_manifest = registry.get_manifest
        def patched_get_manifest(name):
            if name == "mock_web_skill":
                return mock_manifest
            return original_get_manifest(name)
        registry.get_manifest = patched_get_manifest

        agent = GenericAgent(agent_id="test_llm_pipeline", agent_type="dynamic", config={})
        agent._skill_registry = registry

        result = await agent._process_skill_output(
            skill, "mock_web_skill", "白酒行业", "行业分析", registry,
        )

        assert len(result.get("data_points", [])) > 0, "should produce data_points"
        dp = result["data_points"][0]
        assert dp["quality_score"] == 50, "web_search tier should have quality_score=50"
        assert dp["credibility"] == "search_result"
        assert len(dp.get("content", "")) > 0, "content should not be empty"


class TestOrchestratorEndToEnd:
    """Test that the Orchestrator can initialize and create agents with real skill system."""

    def test_orchestrator_skill_system_initialized(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orchestrator = ResearchOrchestrator(use_intelligent_routing=True)

        assert orchestrator._skill_registry is not None
        assert len(orchestrator._skill_registry._manifests) > 0

        stock_manifest = orchestrator._skill_registry.get_manifest("stock_data")
        assert stock_manifest is not None
        assert stock_manifest.priority == "structured_db"

        search_manifest = orchestrator._skill_registry.get_manifest("search_skill")
        assert search_manifest is not None
        assert search_manifest.priority == "web_search"

        xueqiu_manifest = orchestrator._skill_registry.get_manifest("xueqiu")
        assert xueqiu_manifest is not None

    def test_data_collection_skills_for_topic(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.decomposition.strategies import _manifest_strategy

        orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
        assert _manifest_strategy is not None

        skills = _manifest_strategy.get_data_collection_skills("财务分析", "贵州茅台")
        assert len(skills) > 0
        assert "stock_data" in skills, f"stock_data should be in skills, got {skills}"

    def test_discover_skills_from_orchestrator_registry(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orchestrator = ResearchOrchestrator(use_intelligent_routing=True)

        result = orchestrator._skill_registry.discover_skills("stock financial", auto_load=False)
        assert "stock_data" in result

        result = orchestrator._skill_registry.discover_skills("web search", auto_load=False)
        assert any("search" in r for r in result)
