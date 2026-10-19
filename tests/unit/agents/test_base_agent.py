"""
Agent 基类测试
TDD: 先写测试，再实现
"""
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any


class TestAgentState:
    """测试 Agent 状态管理"""
    
    def test_state_creation(self):
        """测试创建状态"""
        from src.core.agents.base import AgentState
        
        state = AgentState(
            agent_id="test-agent",
            status="idle",
            data={"key": "value"}
        )
        
        assert state.agent_id == "test-agent"
        assert state.status == "idle"
        assert state.data["key"] == "value"
        assert state.created_at is not None
    
    def test_state_to_dict(self):
        """测试状态转字典"""
        from src.core.agents.base import AgentState
        
        state = AgentState(agent_id="test", status="running")
        data = state.to_dict()
        
        assert data["agent_id"] == "test"
        assert data["status"] == "running"
        assert "created_at" in data


class TestBaseAgent:
    """测试 Agent 基类"""
    
    @pytest.fixture
    def agent(self):
        """创建测试 Agent"""
        from src.core.agents.base import BaseAgent
        
        class TestAgent(BaseAgent):
            async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
                return {"result": "success", "task": task}
        
        return TestAgent(agent_id="test-agent", agent_type="test")
    
    def test_agent_init(self, agent):
        """测试 Agent 初始化"""
        assert agent.agent_id == "test-agent"
        assert agent.agent_type == "test"
        assert agent.status == "idle"
    
    @pytest.mark.asyncio
    async def test_agent_lifecycle(self, agent):
        """测试 Agent 生命周期"""
        # 初始状态
        assert agent.status == "idle"
        
        # 执行任务
        result = await agent.execute({"input": "test"})
        
        # 验证结果
        assert result["result"] == "success"
    
    def test_state_persistence(self, agent):
        """测试状态持久化"""
        state = agent.get_state()
        
        assert state.agent_id == "test-agent"
        assert state.status == "idle"
    
    def test_update_state(self, agent):
        """测试更新状态"""
        agent.update_state(status="running", data={"progress": 50})
        
        state = agent.get_state()
        assert state.status == "running"
        assert state.data["progress"] == 50


class TestAgentFactory:
    """测试 Agent 工厂"""
    
    def test_register_agent(self):
        """测试注册 Agent 类型"""
        from src.core.agents.base import BaseAgent, AgentFactory
        
        class CustomAgent(BaseAgent):
            async def execute(self, task):
                return {"custom": True}
        
        factory = AgentFactory()
        factory.register("custom", CustomAgent)
        
        assert "custom" in factory._registry
    
    def test_create_agent(self):
        """测试创建 Agent 实例"""
        from src.core.agents.base import BaseAgent, AgentFactory
        
        class CustomAgent(BaseAgent):
            async def execute(self, task):
                return {"custom": True}
        
        factory = AgentFactory()
        factory.register("custom", CustomAgent)
        
        agent = factory.create("custom", agent_id="custom-001")
        
        assert agent.agent_id == "custom-001"
        assert agent.agent_type == "custom"
    
    def test_create_unregistered(self):
        """测试创建未注册的 Agent"""
        from src.core.agents.base import AgentFactory
        
        factory = AgentFactory()
        
        with pytest.raises(ValueError):
            factory.create("unknown", agent_id="test")
