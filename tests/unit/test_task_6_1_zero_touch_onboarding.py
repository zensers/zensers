"""
Task 6.1: Zero-touch skill onboarding test

Verify that adding a new Skill requires ONLY creating SKILL.md + skill.py —
no changes to strategies.py, generic_agent.py, orchestrator.py, or skill_keywords.py.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def temp_skill_dir(tmp_path):
    skill_dir = tmp_path / "test_data_source"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: test_data_source
description: "Test data source"
version: "1.0"
categories:
  - financial-analysis
  - data-collection
priority: structured_db
keywords:
  - test data
  - test datasource
capabilities:
  - fetch
action_rules:
  - pattern: ".*"
    actions: [fetch]
action_param_map:
  fetch: {query: query}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
data_source_keywords:
  - test
data_types:
  financial:
    - revenue
    - net_income
aspect_coverage:
  - Test Analysis
---
""", encoding="utf-8")
    (skill_dir / "skill.py").write_text("""
from src.skills.base import Skill
from typing import Any, Dict

class TestDataSourceSkill(Skill):
    @property
    def name(self): return "test_data_source"
    @property
    def description(self): return "Test data source"
    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "fetch")
        if action == "fetch":
            return {
                "success": True,
                "data": {"revenue": 100.5, "net_income": 20.3, "employees": 5000},
                "content": "Test Corp: revenue 100.5B, net income 20.3B, 5000 employees",
                "source": "test_data_source",
            }
        return {"success": False, "error": "unknown action"}
""", encoding="utf-8")
    return tmp_path


class TestZeroTouchOnboarding:
    @pytest.mark.asyncio
    async def test_skill_discovered_and_registered(self, temp_skill_dir):
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(temp_skill_dir)
        skill = registry.get("test_data_source")
        assert skill is not None, "Skill should be auto-registered"

    @pytest.mark.asyncio
    async def test_skill_executes(self, temp_skill_dir):
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(temp_skill_dir)
        skill = registry.get("test_data_source")
        result = await skill.execute(action="fetch", query="test")
        assert result["success"] is True
        assert result["data"]["revenue"] == 100.5

    def test_manifest_strategy_builder_routes_new_skill(self, temp_skill_dir):
        from src.skills.registry import SkillRegistry
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry = SkillRegistry()
        registry.init_from_discovery(temp_skill_dir)
        builder = ManifestStrategyBuilder(registry.all_manifests())

        priority_map = builder.build_skill_priority_map()
        assert "test_data_source" in priority_map
        assert priority_map["test_data_source"] == "structured_db"

        aspect_map = builder.build_aspect_skill_map()
        assert "test_data_source" in aspect_map.get("Test Analysis", [])

        ds_map = builder.build_data_source_skill_map()
        assert "test_data_source" in ds_map.get("test", [])

        action_map = builder.build_action_to_skill_map()
        assert action_map.get("fetch") == "test_data_source"

    def test_discover_skills_finds_new_skill(self, temp_skill_dir):
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(temp_skill_dir)
        result = registry.discover_skills("test data", auto_load=False)
        assert "test_data_source" in result

    @pytest.mark.asyncio
    async def test_process_skill_output_handles_new_skill(self, temp_skill_dir):
        from src.skills.registry import SkillRegistry
        from src.core.agents.generic_agent import GenericAgent
        registry = SkillRegistry()
        registry.init_from_discovery(temp_skill_dir)
        skill = registry.get("test_data_source")

        agent = GenericAgent(agent_id="test", agent_type="dynamic", config={})
        agent._skill_registry = registry

        result = await agent._process_skill_output(
            skill, "test_data_source", "Test Corp", "Test Analysis", registry,
        )
        assert len(result.get("data_points", [])) > 0
        dp = result["data_points"][0]
        assert "content" in dp
        assert "100.5" in dp["content"] or "Test Corp" in dp["content"]

        metrics = result.get("canonical_metrics", {})
        assert "revenue" in metrics
        assert metrics["revenue"] == 100.5

    def test_no_code_changes_needed(self, temp_skill_dir):
        """Verify that strategies.py, generic_agent.py, orchestrator.py don't reference test_data_source."""
        import inspect
        from src.core.decomposition import strategies
        from src.core.agents import generic_agent
        from src.core.orchestrator import orchestrator

        for mod in [strategies, generic_agent, orchestrator]:
            source = inspect.getsource(mod)
            assert "test_data_source" not in source, \
                f"{mod.__name__} should not reference test_data_source"
