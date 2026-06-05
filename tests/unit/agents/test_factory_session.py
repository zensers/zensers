"""
DynamicAgentFactory Session 扩展测试

测试 create_agent_with_session() 方法，覆盖：
1. Agent 创建与 Session 绑定
2. Session 注册到 Registry
3. 通信能力注入（message_bus, shared_memory）
4. Session 状态追踪

设计文档: docs/AGENT_SESSION_MANAGEMENT.md Section 4.1
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, Any

from src.core.agents.factory import (
    DynamicAgentFactory,
    AgentCapability,
    GenericAgent,
    get_agent_factory,
)
from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionRegistry,
    AgentSessionStatus,
    SessionOrigin,
    generate_session_id,
)
from src.core.communication import MessageBus, Event, SharedMemory


# === Fixtures ===

@pytest.fixture
def message_bus():
    """创建 MessageBus 实例"""
    return MessageBus()


@pytest.fixture
def shared_memory():
    """创建 SharedMemory 实例"""
    return SharedMemory()


@pytest.fixture
def factory_with_comm(message_bus, shared_memory):
    """创建带通信能力的 Factory"""
    return DynamicAgentFactory(
        message_bus=message_bus,
        shared_memory=shared_memory
    )


@pytest.fixture
def basic_capability():
    """创建基本能力定义"""
    return AgentCapability(
        name="测试Agent",
        description="用于测试的Agent",
        required_skills=["search_skill"],
        optional_skills=["file_skill"]
    )


# === Test DynamicAgentFactory 初始化 ===

class TestFactoryInit:
    """测试 Factory 初始化"""
    
    def test_init_without_comm(self):
        """测试无通信能力初始化——默认创建MessageBus和SharedMemory"""
        factory = DynamicAgentFactory()
        
        assert factory._message_bus is not None
        assert factory._shared_memory is not None
        assert factory._session_registries == {}
    
    def test_init_with_message_bus(self, message_bus):
        """测试带 MessageBus 初始化"""
        factory = DynamicAgentFactory(message_bus=message_bus)
        
        assert factory._message_bus == message_bus
        assert factory._shared_memory is not None
    
    def test_init_with_full_comm(self, message_bus, shared_memory):
        """测试完整通信能力初始化"""
        factory = DynamicAgentFactory(
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        
        assert factory._message_bus == message_bus
        assert factory._shared_memory == shared_memory


# === Test create_agent_with_session ===

class TestCreateAgentWithSession:
    """测试 create_agent_with_session() 方法"""
    
    def test_creates_agent_and_session(self, factory_with_comm, basic_capability):
        """测试创建 Agent 和 Session"""
        parent_session_id = "research_test_001"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_test_001",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context={"topic": "测试主题"}
        )
        
        # 验证 Agent 创建成功
        assert agent is not None
        assert agent.agent_id == "agent_test_001"
        assert isinstance(agent, GenericAgent)
        
        # 验证 Session 创建成功
        assert session is not None
        assert isinstance(session, AgentSession)
        assert session.agent_id == "agent_test_001"
        assert session.parent_session_id == parent_session_id
        assert session.origin == SessionOrigin.SPAWNED
    
    def test_session_has_unique_id(self, factory_with_comm, basic_capability):
        """测试 Session 生成唯一 ID"""
        parent_session_id = "research_test_002"
        
        # 创建多个 Agent
        results = []
        for i in range(5):
            agent, session = factory_with_comm.create_agent_with_session(
                agent_id=f"agent_{i}",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
            results.append(session.session_id)
        
        # 所有 Session ID 应唯一
        assert len(results) == len(set(results))
    
    def test_session_registered_in_registry(self, factory_with_comm, basic_capability):
        """测试 Session 注册到 Registry"""
        parent_session_id = "research_test_003"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_test_003",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 验证 Registry 存在
        assert parent_session_id in factory_with_comm._session_registries
        
        registry = factory_with_comm._session_registries[parent_session_id]
        
        # 验证 Session 已注册
        assert registry.get_session(session.session_id) == session
    
    def test_comm_injected_to_agent(self, factory_with_comm, basic_capability):
        """测试通信能力注入到 Agent"""
        parent_session_id = "research_test_004"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_test_004",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 验证通信能力注入
        assert hasattr(agent, '_session')
        assert agent._session == session
        
        assert hasattr(agent, '_message_bus')
        assert agent._message_bus is factory_with_comm._message_bus
        
        assert hasattr(agent, '_shared_memory')
        assert agent._shared_memory is factory_with_comm._shared_memory
    
    def test_without_comm_still_works(self, basic_capability):
        """测试无通信能力时仍可创建"""
        factory = DynamicAgentFactory()  # 无 message_bus 和 shared_memory
        
        parent_session_id = "research_test_005"
        
        agent, session = factory.create_agent_with_session(
            agent_id="agent_test_005",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # Agent 和 Session 应创建成功
        assert agent is not None
        assert session is not None
        
        # 通信能力由factory默认提供
        assert agent._message_bus is not None
        assert agent._shared_memory is not None
    
    def test_context_passed_to_session(self, factory_with_comm, basic_capability):
        """测试 context 传递到 Session"""
        parent_session_id = "research_test_006"
        context = {
            "topic": "新能源汽车",
            "aspect": "市场规模",
            "priority": "high"
        }
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_test_006",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context=context
        )
        
        # 验证 context 传递
        assert session.context == context
    
    def test_task_in_session(self, factory_with_comm, basic_capability):
        """测试 task 信息在 Session 中"""
        parent_session_id = "research_test_007"
        context = {"aspect": "竞争格局"}
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_test_007",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context=context
        )
        
        # Session 应包含任务信息
        assert session.task is not None
        assert session.task.get("action") == "research"
        assert session.task.get("aspect") == "竞争格局"
    
    def test_duplicate_agent_id_raises_error(self, factory_with_comm, basic_capability):
        """测试重复 agent_id 抛出异常"""
        parent_session_id = "research_test_008"
        
        # 创建第一个 Agent
        factory_with_comm.create_agent_with_session(
            agent_id="agent_duplicate_001",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 尝试创建相同 agent_id 的 Agent
        with pytest.raises(ValueError) as exc_info:
            factory_with_comm.create_agent_with_session(
                agent_id="agent_duplicate_001",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
        
        assert "already exists" in str(exc_info.value)


# === Test Registry Management ===

class TestFactoryRegistryManagement:
    """测试 Factory 的 Registry 管理"""
    
    def test_get_registry(self, factory_with_comm, basic_capability):
        """测试获取 Registry"""
        parent_session_id = "research_test_008"
        
        # 先创建一个 Agent
        factory_with_comm.create_agent_with_session(
            agent_id="agent_test_008a",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 获取 Registry
        registry = factory_with_comm.get_registry(parent_session_id)
        
        assert registry is not None
        assert isinstance(registry, AgentSessionRegistry)
        assert registry.parent_session_id == parent_session_id
    
    def test_get_registry_not_exist(self, factory_with_comm):
        """测试获取不存在的 Registry"""
        registry = factory_with_comm.get_registry("nonexistent_session")
        
        assert registry is None
    
    def test_registry_persist_across_agents(self, factory_with_comm, basic_capability):
        """测试 Registry 在多个 Agent 间持久"""
        parent_session_id = "research_test_009"
        
        # 创建多个 Agent（相同 parent_session_id）
        session_ids = []
        for i in range(3):
            _, session = factory_with_comm.create_agent_with_session(
                agent_id=f"agent_009_{i}",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
            session_ids.append(session.session_id)
        
        # Registry 应包含所有 Session
        registry = factory_with_comm.get_registry(parent_session_id)
        assert registry.count() == 3
        
        # 验证所有 Session ID
        for sid in session_ids:
            assert registry.get_session(sid) is not None
    
    def test_different_parents_have_different_registries(self, factory_with_comm, basic_capability):
        """测试不同 parent 有不同 Registry"""
        parent_1 = "research_parent_1"
        parent_2 = "research_parent_2"
        
        # 为不同 parent 创建 Agent
        _, session_1 = factory_with_comm.create_agent_with_session(
            agent_id="agent_parent_1",
            capability=basic_capability,
            parent_session_id=parent_1
        )
        
        _, session_2 = factory_with_comm.create_agent_with_session(
            agent_id="agent_parent_2",
            capability=basic_capability,
            parent_session_id=parent_2
        )
        
        # Registry 应独立
        registry_1 = factory_with_comm.get_registry(parent_1)
        registry_2 = factory_with_comm.get_registry(parent_2)
        
        assert registry_1.count() == 1
        assert registry_2.count() == 1
        
        # Session 不应混入
        assert registry_1.get_session(session_2.session_id) is None
        assert registry_2.get_session(session_1.session_id) is None
    
    def test_clear_registry(self, factory_with_comm, basic_capability):
        """测试清理 Registry"""
        parent_session_id = "research_clear_001"
        
        # 创建 Agent
        factory_with_comm.create_agent_with_session(
            agent_id="agent_clear_1",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 验证 Registry 存在
        assert factory_with_comm.get_registry(parent_session_id) is not None
        
        # 清理 Registry
        result = factory_with_comm.clear_registry(parent_session_id)
        
        assert result is True
        assert factory_with_comm.get_registry(parent_session_id) is None
    
    def test_clear_registry_not_exist(self, factory_with_comm):
        """测试清理不存在的 Registry"""
        result = factory_with_comm.clear_registry("nonexistent_registry")
        assert result is False
    
    def test_clear_all_registries(self, factory_with_comm, basic_capability):
        """测试清理所有 Registry"""
        # 创建多个 Registry
        for i in range(3):
            factory_with_comm.create_agent_with_session(
                agent_id=f"agent_clear_all_{i}",
                capability=basic_capability,
                parent_session_id=f"parent_{i}"
            )
        
        assert len(factory_with_comm._session_registries) == 3
        
        # 清理所有
        count = factory_with_comm.clear_all_registries()
        
        assert count == 3
        assert len(factory_with_comm._session_registries) == 0


# === Test get_or_create_registry ===

class TestGetOrCreateRegistry:
    """测试 get_or_create_registry() 方法"""
    
    def test_create_new_registry(self, factory_with_comm):
        """测试创建新 Registry"""
        parent_session_id = "research_new_001"
        
        registry = factory_with_comm.get_or_create_registry(parent_session_id)
        
        assert registry is not None
        assert isinstance(registry, AgentSessionRegistry)
        assert registry.parent_session_id == parent_session_id
        assert registry.count() == 0
    
    def test_get_existing_registry(self, factory_with_comm, basic_capability):
        """测试获取已存在的 Registry"""
        parent_session_id = "research_existing_001"
        
        # 先创建一个 Agent（会创建 Registry）
        factory_with_comm.create_agent_with_session(
            agent_id="agent_existing",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 再次获取应返回同一 Registry
        registry_1 = factory_with_comm.get_registry(parent_session_id)
        registry_2 = factory_with_comm.get_or_create_registry(parent_session_id)
        
        # 应是同一实例
        assert registry_1 == registry_2
        assert registry_1.count() == 1  # 已有 Agent


# === Test Agent Statistics ===

class TestFactoryStats:
    """测试 Factory 统计信息"""
    
    def test_get_stats_with_sessions(self, factory_with_comm, basic_capability):
        """测试带 Session 的统计"""
        parent_session_id = "research_stats_001"
        
        # 创建多个 Agent
        for i in range(3):
            factory_with_comm.create_agent_with_session(
                agent_id=f"agent_stats_{i}",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
        
        stats = factory_with_comm.get_stats()
        
        assert stats["created_count"] == 3
        assert stats["active_agents"] == 3
        assert stats["session_registries"] == 1
        assert parent_session_id in stats["registry_ids"]
    
    def test_get_stats_multiple_parents(self, factory_with_comm, basic_capability):
        """测试多个 parent 的统计"""
        parents = ["parent_1", "parent_2", "parent_3"]
        
        for parent in parents:
            factory_with_comm.create_agent_with_session(
                agent_id=f"agent_{parent}",
                capability=basic_capability,
                parent_session_id=parent
            )
        
        stats = factory_with_comm.get_stats()
        
        assert stats["session_registries"] == 3
        assert len(stats["registry_ids"]) == 3


# === Test Global Factory ===

class TestGlobalFactory:
    """测试全局工厂"""
    
    def test_get_agent_factory_singleton(self):
        """测试全局工厂单例"""
        factory_1 = get_agent_factory()
        factory_2 = get_agent_factory()
        
        # 应是同一实例
        assert factory_1 == factory_2
    
    def test_global_factory_has_default_skill_registry(self):
        """测试全局工厂有默认 SkillRegistry"""
        factory = get_agent_factory()
        
        assert factory._skill_registry is not None


# === Integration Tests ===

class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_agent_can_use_comm(self, factory_with_comm, basic_capability):
        """测试 Agent 可以使用通信能力"""
        parent_session_id = "research_integration_001"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_integration",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context={"topic": "测试"}
        )
        
        # Agent 应能写入 SharedMemory
        assert agent._shared_memory is not None
        await agent._shared_memory.write("test_key", "test_value")
        value = await agent._shared_memory.read("test_key")
        assert value == "test_value"
    
    @pytest.mark.asyncio
    async def test_agent_session_status_flow(self, factory_with_comm, basic_capability):
        """测试 Session 状态流转"""
        parent_session_id = "research_integration_002"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_status",
            capability=basic_capability,
            parent_session_id=parent_session_id
        )
        
        # 初始状态应为 PENDING
        assert session.status == AgentSessionStatus.PENDING
        
        # 开始执行
        session.start()
        assert session.status == AgentSessionStatus.RUNNING
        assert session.started_at is not None
        
        # 完成执行
        session.complete({"result": "success"})
        assert session.status == AgentSessionStatus.COMPLETED
        assert session.result == {"result": "success"}
        assert session.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_registry_tracks_session_status(self, factory_with_comm, basic_capability):
        """测试 Registry 追踪 Session 状态"""
        parent_session_id = "research_integration_003"
        
        # 创建多个 Agent
        sessions = []
        for i in range(3):
            _, session = factory_with_comm.create_agent_with_session(
                agent_id=f"agent_{i}",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
            sessions.append(session)
        
        registry = factory_with_comm.get_registry(parent_session_id)
        
        # 更新第一个 Session 状态
        sessions[0].start()
        
        # Registry 应能查询状态
        running = registry.get_running()
        pending = registry.get_pending()
        
        assert len(running) == 1
        assert len(pending) == 2


# === Edge Cases ===

class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_capability(self, factory_with_comm):
        """测试空能力定义"""
        empty_capability = AgentCapability(
            name="空Agent",
            description="无技能",
            required_skills=[]
        )
        
        parent_session_id = "research_edge_001"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_empty",
            capability=empty_capability,
            parent_session_id=parent_session_id
        )
        
        # 应创建成功
        assert agent is not None
        assert session is not None
    
    def test_none_context(self, factory_with_comm, basic_capability):
        """测试 None context"""
        parent_session_id = "research_edge_002"
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_none",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context=None
        )
        
        # Session context 应为空字典
        assert session.context == {}
    
    def test_large_context(self, factory_with_comm, basic_capability):
        """测试大 context"""
        parent_session_id = "research_edge_003"
        
        # 创建大 context
        large_context = {
            "topic": "测试",
            "data": {i: f"value_{i}" for i in range(100)},
            "nested": {"level": {"deep": {"value": "nested"}}}
        }
        
        agent, session = factory_with_comm.create_agent_with_session(
            agent_id="agent_large",
            capability=basic_capability,
            parent_session_id=parent_session_id,
            context=large_context
        )
        
        # 应创建成功
        assert session.context == large_context
    
    def test_session_id_collision_handling(self, factory_with_comm, basic_capability):
        """测试 Session ID 碰撞处理（理论测试）"""
        parent_session_id = "research_edge_004"
        
        # 创建多个 Agent，理论上不应碰撞
        session_ids = set()
        for i in range(100):
            _, session = factory_with_comm.create_agent_with_session(
                agent_id=f"agent_collision_{i}",
                capability=basic_capability,
                parent_session_id=parent_session_id
            )
            session_ids.add(session.session_id)
        
        # 所有 ID 应唯一
        assert len(session_ids) == 100


# === Run Tests ===

if __name__ == "__main__":
    pytest.main([__file__, "-v"])