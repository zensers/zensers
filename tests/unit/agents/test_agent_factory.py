"""
Agent工厂测试
=============

测试动态Agent创建和管理功能。
DynamicAgentFactory 和 GenericAgent 的基础功能测试。
详细测试见 test_factory_session.py

v2.1 更新：
- 使用IAgent Protocol替代BaseAgent进行isinstance检查
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from src.core.agents.factory import DynamicAgentFactory, AgentCapability, GenericAgent
from src.core.agents.protocol import IAgent
from src.core.agents.base import BaseAgent


class TestDynamicAgentFactory:
    """测试动态Agent工厂基础功能."""
    
    def test_initialization(self):
        """测试工厂初始化."""
        factory = DynamicAgentFactory()
        
        assert factory._skill_registry is not None
        assert factory._agents == {}
        assert factory._created_count == 0
        assert factory._session_registries == {}
    
    def test_create_agent(self):
        """测试创建Agent."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability(
            name="测试Agent",
            description="测试用Agent",
            required_skills=["search_skill"]
        )
        
        agent = factory.create_agent(
            agent_id="test_agent_001",
            capability=capability,
            context={"topic": "测试主题"}
        )
        
        assert agent.agent_id == "test_agent_001"
        # 使用IAgent Protocol进行检查（Mixin组合模式）
        assert isinstance(agent, IAgent)
        assert isinstance(agent, GenericAgent)
        assert factory._created_count == 1
    
    def test_create_multiple_agents(self):
        """测试创建多个Agent."""
        factory = DynamicAgentFactory()
        
        for i in range(3):
            capability = AgentCapability(
                name=f"Agent_{i}",
                description=f"Agent {i}",
                required_skills=["search_skill"]
            )
            factory.create_agent(f"agent_{i}", capability)
        
        assert factory._created_count == 3
        assert len(factory._agents) == 3
    
    def test_get_agent(self):
        """测试获取Agent."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability("Test", "Test Agent", ["search_skill"])
        factory.create_agent("test_agent", capability)
        
        agent = factory.get_agent("test_agent")
        assert agent is not None
        assert agent.agent_id == "test_agent"
    
    def test_get_agent_not_found(self):
        """测试获取不存在的Agent."""
        factory = DynamicAgentFactory()
        
        agent = factory.get_agent("nonexistent")
        assert agent is None
    
    def test_list_agents(self):
        """测试列出所有Agent."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability("Test1", "Test 1", ["search_skill"])
        factory.create_agent("agent_1", capability)
        
        capability2 = AgentCapability("Test2", "Test 2", ["file_skill"])
        factory.create_agent("agent_2", capability2)
        
        agents = factory.list_agents()
        assert len(agents) == 2
        assert "agent_1" in agents
        assert "agent_2" in agents
    
    def test_get_stats(self):
        """测试获取统计信息."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability("Test", "Test Agent", ["search_skill"])
        factory.create_agent("agent_1", capability)
        
        stats = factory.get_stats()
        
        assert stats["created_count"] == 1
        assert stats["active_agents"] == 1
        assert "agent_1" in stats["agent_ids"]
        assert stats["session_registries"] == 0
    
    def test_create_custom_agent(self):
        """测试创建自定义Agent."""
        factory = DynamicAgentFactory()
        
        agent = factory.create_custom_agent(
            agent_id="custom_agent",
            name="自定义Agent",
            description="完全自定义的Agent",
            skills=["skill1", "skill2"]
        )
        
        assert agent.agent_id == "custom_agent"
        assert factory._created_count == 1


class TestAgentCapability:
    """测试Agent能力定义."""
    
    def test_basic_capability(self):
        """测试基本能力定义."""
        capability = AgentCapability(
            name="测试能力",
            description="测试描述",
            required_skills=["skill1"]
        )
        
        assert capability.name == "测试能力"
        assert capability.description == "测试描述"
        assert capability.required_skills == ["skill1"]
        assert capability.optional_skills == []
    
    def test_capability_with_optional_skills(self):
        """测试带可选技能的能力."""
        capability = AgentCapability(
            name="测试能力",
            description="测试描述",
            required_skills=["skill1"],
            optional_skills=["skill2", "skill3"]
        )
        
        assert capability.required_skills == ["skill1"]
        assert capability.optional_skills == ["skill2", "skill3"]
    
    def test_capability_with_skill_params(self):
        """测试带技能参数的能力."""
        capability = AgentCapability(
            name="测试能力",
            description="测试描述",
            required_skills=["skill1"],
            skill_params={"skill1": {"param": "value"}}
        )
        
        assert capability.skill_params == {"skill1": {"param": "value"}}


class TestGenericAgent:
    """测试通用Agent."""
    
    @pytest.mark.asyncio
    async def test_execute_default_response(self):
        """测试执行任务默认响应."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability("Test", "Test Agent", [])
        agent = factory.create_agent("test_agent", capability)
        
        result = await agent.execute({"action": "unknown"})
        
        assert result["success"] is True
        assert "test_agent" in result["message"]
        assert "available_skills" in result
    
    def test_agent_config(self):
        """测试Agent配置."""
        factory = DynamicAgentFactory()
        
        capability = AgentCapability(
            name="ConfigTest",
            description="配置测试",
            required_skills=["skill1"],
            optional_skills=["skill2"]
        )
        
        agent = factory.create_agent("config_agent", capability, context={"key": "value"})
        
        assert agent.config["name"] == "ConfigTest"
        assert agent.config["required_skills"] == ["skill1"]
        assert agent.config["optional_skills"] == ["skill2"]
        assert agent.config["context"] == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])