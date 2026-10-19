"""Current research-agent contract tests.

The former ``src.agents.research.ResearchAgent`` abstraction was replaced by
the dynamic ``GenericAgent`` + ``AgentCapability`` path.  Keep this test
module as the migration point so the old research-agent coverage is not
silently removed while the implementation is retired.
"""

import pytest

from src.core.agents.factory import AgentCapability, DynamicAgentFactory, GenericAgent


def _make_research_agent() -> GenericAgent:
    factory = DynamicAgentFactory()
    capability = AgentCapability(
        name="研究分析Agent",
        description="执行研究任务并返回可审计结果",
        required_skills=[],
        role="research analyst",
        goal="analyze a research aspect",
    )
    return factory.create_agent(
        "research_contract_001",
        capability,
        context={"topic": "中国智能手机行业"},
    )


def test_research_capability_uses_current_generic_agent_contract():
    agent = _make_research_agent()

    assert isinstance(agent, GenericAgent)
    assert agent.agent_id == "research_contract_001"
    assert agent.config["role"] == "research analyst"
    assert agent.config["goal"] == "analyze a research aspect"
    assert agent.config["context"]["topic"] == "中国智能手机行业"


@pytest.mark.asyncio
async def test_research_agent_default_execution_is_structured():
    agent = _make_research_agent()

    result = await agent.run({"action": "unknown"})

    assert result["success"] is True
    assert result["agent_id"] == agent.agent_id
    assert "available_skills" in result
