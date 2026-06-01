"""
Agent生命周期管理测试

测试新增的生命周期状态、休眠和恢复功能。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
"""
import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile

from src.core.agents.lifecycle_state import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
    get_valid_transitions,
)
from src.core.agents.batch_structures import (
    BatchCreationResult,
    BatchExecutionResult,
    AgentExecutionRecord,
    BatchStatus,
)
from src.core.agents.generic_agent import GenericAgent
from src.core.agents.factory import DynamicAgentFactory, AgentCapability
from src.core.agents.agent_session import AgentSession, AgentSessionStatus as SessionStatus
from src.core.agents.session_persistence import SessionPersistenceManager


class TestLifecycleState:
    """测试生命周期状态定义"""
    
    def test_state_count(self):
        """验证状态数量"""
        assert len(AgentLifecycleState) == 12
    
    def test_state_values(self):
        """验证状态值"""
        assert AgentLifecycleState.CREATED.value == "created"
        assert AgentLifecycleState.HIBERNATED.value == "hibernated"
        assert AgentLifecycleState.TERMINATED.value == "terminated"
    
    def test_valid_transition_created_to_initializing(self):
        """验证合法转换: CREATED → INITIALIZING"""
        assert validate_transition(
            AgentLifecycleState.CREATED,
            AgentLifecycleState.INITIALIZING
        )
    
    def test_invalid_transition_created_to_running(self):
        """验证非法转换: CREATED → RUNNING"""
        assert not validate_transition(
            AgentLifecycleState.CREATED,
            AgentLifecycleState.RUNNING
        )
    
    def test_valid_transition_hibernated_to_resuming(self):
        """验证合法转换: HIBERNATED → RESUMING"""
        assert validate_transition(
            AgentLifecycleState.HIBERNATED,
            AgentLifecycleState.RESUMING
        )
    
    def test_invalid_transition_hibernated_to_running(self):
        """验证非法转换: HIBERNATED → RUNNING"""
        assert not validate_transition(
            AgentLifecycleState.HIBERNATED,
            AgentLifecycleState.RUNNING
        )
    
    def test_terminated_has_no_transitions(self):
        """验证TERMINATED是终态"""
        transitions = get_valid_transitions(AgentLifecycleState.TERMINATED)
        assert len(transitions) == 0
    
    def test_invalid_state_error(self):
        """验证异常信息"""
        error = InvalidStateError(
            AgentLifecycleState.CREATED,
            AgentLifecycleState.RUNNING
        )
        assert "created" in str(error)
        assert "running" in str(error)
        assert "Invalid state transition" in str(error)


class TestBatchStructures:
    """测试批次数据结构"""
    
    def test_batch_creation_result(self):
        """测试BatchCreationResult"""
        result = BatchCreationResult(
            batch_index=0,
            agents=[],
            sessions=[],
        )
        
        assert result.batch_index == 0
        assert len(result) == 0
        assert result.get_agent_ids() == []
        assert result.get_session_ids() == []
    
    def test_agent_execution_record(self):
        """测试AgentExecutionRecord"""
        record = AgentExecutionRecord(
            session_id="session_001",
            agent_id="agent_001",
            batch_index=0,
            aspect="市场规模",
        )
        
        assert record.status == BatchStatus.PENDING
        assert record.progress == 0.0
        
        # 开始执行
        record.start()
        assert record.status == BatchStatus.RUNNING
        assert record.started_at is not None
        
        # 完成
        record.complete({"success": True, "data": "test"})
        assert record.status == BatchStatus.COMPLETED
        assert record.progress == 1.0
        assert record.task_output is not None
    
    def test_agent_execution_record_fail(self):
        """测试AgentExecutionRecord失败"""
        record = AgentExecutionRecord(
            session_id="session_001",
            agent_id="agent_001",
            batch_index=0,
            aspect="市场规模",
        )
        
        record.start()
        record.fail("Test error")
        
        assert record.status == BatchStatus.FAILED
        assert record.error == "Test error"
    
    def test_batch_execution_result(self):
        """测试BatchExecutionResult"""
        result = BatchExecutionResult(
            batch_index=0,
            task_id="task_001",
            aspects=["市场规模", "竞争格局"],
        )
        
        # 添加Agent记录
        record1 = AgentExecutionRecord(
            session_id="session_001",
            agent_id="agent_001",
            batch_index=0,
            aspect="市场规模",
        )
        result.add_agent_record(record1)
        
        assert result.total_agents == 1
        
        # 开始批次
        result.start_batch()
        assert result.status == BatchStatus.RUNNING
        
        # 完成批次
        record1.start()
        record1.complete({"success": True})
        result.complete_batch()
        
        assert result.completed_agents == 1
        assert result.failed_agents == 0
        assert result.status == BatchStatus.COMPLETED
    
    def test_batch_execution_result_partial(self):
        """测试部分完成的批次"""
        result = BatchExecutionResult(
            batch_index=0,
            task_id="task_001",
            aspects=["市场规模", "竞争格局"],
        )
        
        # 添加两个Agent记录
        record1 = AgentExecutionRecord(
            session_id="session_001",
            agent_id="agent_001",
            batch_index=0,
            aspect="市场规模",
        )
        record2 = AgentExecutionRecord(
            session_id="session_002",
            agent_id="agent_002",
            batch_index=0,
            aspect="竞争格局",
        )
        
        result.add_agent_record(record1)
        result.add_agent_record(record2)
        
        # 一个成功，一个失败
        record1.start()
        record1.complete({"success": True})
        record2.start()
        record2.fail("Error")
        
        result.complete_batch()
        
        assert result.status == BatchStatus.PARTIAL
        assert result.completed_agents == 1
        assert result.failed_agents == 1
        assert result.get_failed_agents() == ["agent_002"]


class TestGenericAgentLifecycle:
    """测试GenericAgent生命周期方法"""
    
    def test_agent_initial_state(self):
        """测试Agent初始状态为CREATED"""
        agent = GenericAgent(
            agent_id="test_agent",
            config={"skill_registry": None, "skills": []}
        )
        
        assert agent.get_lifecycle_state() == AgentLifecycleState.CREATED
    
    def test_agent_set_lifecycle_state_valid(self):
        """测试合法状态转换"""
        agent = GenericAgent(
            agent_id="test_agent",
            config={"skill_registry": None, "skills": []}
        )
        
        # CREATED → INITIALIZING
        agent.set_lifecycle_state(AgentLifecycleState.INITIALIZING)
        assert agent.get_lifecycle_state() == AgentLifecycleState.INITIALIZING
        
        # INITIALIZING → READY
        agent.set_lifecycle_state(AgentLifecycleState.READY)
        assert agent.get_lifecycle_state() == AgentLifecycleState.READY
    
    def test_agent_set_lifecycle_state_invalid(self):
        """测试非法状态转换抛出异常"""
        agent = GenericAgent(
            agent_id="test_agent",
            config={"skill_registry": None, "skills": []}
        )
        
        # CREATED → RUNNING (非法)
        with pytest.raises(InvalidStateError):
            agent.set_lifecycle_state(AgentLifecycleState.RUNNING)


class TestFactoryBatchMethods:
    """测试Factory批量方法"""
    
    @pytest.fixture
    def factory(self):
        """创建测试工厂"""
        return DynamicAgentFactory()
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.mark.asyncio
    async def test_create_batch(self, factory, temp_storage):
        """测试创建批次"""
        # 设置持久化
        persistence = SessionPersistenceManager(temp_storage)
        factory._persistence = persistence
        
        # 创建批次
        aspects = ["市场规模", "竞争格局", "政策环境"]
        batch_result = await factory.create_batch(
            parent_session_id="task_001",
            batch_index=0,
            aspects=aspects,
        )
        
        assert batch_result.batch_index == 0
        assert len(batch_result.agents) == 3
        assert len(batch_result.sessions) == 3
        
        # 验证Agent状态
        for agent in batch_result.agents:
            assert agent.get_lifecycle_state() == AgentLifecycleState.READY
    
    @pytest.mark.asyncio
    async def test_create_batch_with_previous(self, factory, temp_storage):
        """测试创建批次时休眠上一批"""
        # 设置持久化
        persistence = SessionPersistenceManager(temp_storage)
        factory._persistence = persistence
        
        # 创建第一批
        batch0 = await factory.create_batch(
            parent_session_id="task_001",
            batch_index=0,
            aspects=["市场规模", "竞争格局"],
        )
        
        # 记录第一批Agent ID
        batch0_ids = batch0.get_agent_ids()
        
        # 创建第二批（会休眠第一批）
        batch1 = await factory.create_batch(
            parent_session_id="task_001",
            batch_index=1,
            aspects=["政策环境", "技术趋势"],
            previous_batch_agents=batch0_ids,
        )
        
        # 验证第一批Agent已从工厂移除
        for agent_id in batch0_ids:
            assert factory.get_agent(agent_id) is None
    
    @pytest.mark.asyncio
    async def test_hibernate_batch(self, factory, temp_storage):
        """测试批量休眠"""
        # 设置持久化
        persistence = SessionPersistenceManager(temp_storage)
        factory._persistence = persistence
        
        # 创建批次
        batch_result = await factory.create_batch(
            parent_session_id="task_001",
            batch_index=0,
            aspects=["市场规模", "竞争格局"],
        )
        
        agent_ids = batch_result.get_agent_ids()
        
        # 休眠
        await factory.hibernate_batch(agent_ids)
        
        # 验证Agent已移除
        for agent_id in agent_ids:
            assert factory.get_agent(agent_id) is None


class TestDataLineageManager:
    """测试数据链路管理器"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def manager(self, temp_storage):
        """创建数据链路管理器"""
        from src.core.data.data_lineage_manager import DataLineageManager
        return DataLineageManager(temp_storage)
    
    def test_record_creation(self, manager):
        """测试记录数据创建"""
        data_id = manager.record_creation(
            agent_id="agent_001",
            session_id="session_001",
            batch_index=0,
            data_type="raw",
            content={"value": 100},
        )
        
        assert data_id.startswith("raw_")
        assert manager.get_agent_outputs("agent_001") == [data_id]
    
    def test_record_transmission(self, manager):
        """测试记录数据传递"""
        data_id = manager.record_creation(
            agent_id="agent_001",
            session_id="session_001",
            batch_index=0,
            data_type="raw",
            content={"value": 100},
        )
        
        manager.record_transmission(
            data_id=data_id,
            from_agent_id="agent_001",
            to_agent_id="agent_002",
        )
        
        lineage = manager.get_lineage(data_id)
        assert len(lineage) == 2  # 创建记录 + 传递记录
    
    def test_get_batch_data(self, manager):
        """测试获取批次数据"""
        # 创建两个批次的数据
        manager.record_creation(
            agent_id="agent_001",
            session_id="session_001",
            batch_index=0,
            data_type="raw",
            content={"value": 100},
        )
        manager.record_creation(
            agent_id="agent_002",
            session_id="session_002",
            batch_index=1,
            data_type="raw",
            content={"value": 200},
        )
        
        batch0_data = manager.get_batch_data(0)
        batch1_data = manager.get_batch_data(1)
        
        assert len(batch0_data) == 1
        assert len(batch1_data) == 1
    
    def test_get_stats(self, manager):
        """测试统计信息"""
        manager.record_creation(
            agent_id="agent_001",
            session_id="session_001",
            batch_index=0,
            data_type="raw",
            content={"value": 100},
        )
        manager.record_creation(
            agent_id="agent_002",
            session_id="session_002",
            batch_index=0,
            data_type="analysis",
            content={"conclusion": "test"},
        )
        
        stats = manager.get_stats()
        
        assert stats["total_data_records"] == 2
        assert stats["data_types"]["raw"] == 1
        assert stats["data_types"]["analysis"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])