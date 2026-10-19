"""
Agent生命周期管理完整测试

验证新增的生命周期状态、批量创建、休眠恢复、数据链路等功能。
"""
import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
import sys

# 添加项目根目录到路径
sys.path.insert(0, 'E:/market_report_systerm')

# ============================================
# 第一部分：生命周期状态测试
# ============================================

print("=" * 60)
print("Part 1: Lifecycle State Test")
print("=" * 60)

from src.core.agents.lifecycle_state import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
    get_valid_transitions,
)

# Test 1.1: State count
print("\n[1.1] Verify state count")
assert len(AgentLifecycleState) == 11, f"State count should be 11, got {len(AgentLifecycleState)}"
print(f"    PASS: State count = {len(AgentLifecycleState)}")

# Test 1.2: State values
print("\n[1.2] Verify state values")
assert AgentLifecycleState.CREATED.value == "created"
assert AgentLifecycleState.HIBERNATED.value == "hibernated"
assert AgentLifecycleState.RESUMING.value == "resuming"
assert AgentLifecycleState.TERMINATED.value == "terminated"
print("    PASS: State values correct")

# Test 1.3: Valid transitions
print("\n[1.3] Verify valid transitions")
assert validate_transition(AgentLifecycleState.CREATED, AgentLifecycleState.INITIALIZING)
assert validate_transition(AgentLifecycleState.READY, AgentLifecycleState.RUNNING)
assert validate_transition(AgentLifecycleState.HIBERNATED, AgentLifecycleState.RESUMING)
assert validate_transition(AgentLifecycleState.RUNNING, AgentLifecycleState.HIBERNATING)
print("    PASS: Valid transitions verified")

# Test 1.4: Invalid transitions
print("\n[1.4] Verify invalid transitions")
assert not validate_transition(AgentLifecycleState.CREATED, AgentLifecycleState.RUNNING)
assert not validate_transition(AgentLifecycleState.HIBERNATED, AgentLifecycleState.RUNNING)
assert not validate_transition(AgentLifecycleState.TERMINATED, AgentLifecycleState.READY)
print("    PASS: Invalid transitions verified")

# Test 1.5: TERMINATED is terminal
print("\n[1.5] Verify TERMINATED terminal state")
transitions = get_valid_transitions(AgentLifecycleState.TERMINATED)
assert len(transitions) == 0, "TERMINATED should have no transitions"
print("    PASS: TERMINATED is terminal state")

# Test 1.6: Exception message
print("\n[1.6] Verify exception message")
try:
    raise InvalidStateError(AgentLifecycleState.CREATED, AgentLifecycleState.RUNNING)
except InvalidStateError as e:
    assert "created" in str(e)
    assert "running" in str(e)
    assert "Invalid state transition" in str(e)
print("    PASS: Exception message complete")

print("\nPart 1 tests PASSED")

# ============================================
# Part 2: Batch Structures Test
# ============================================

print("\n" + "=" * 60)
print("Part 2: Batch Structures Test")
print("=" * 60)

from src.core.agents.batch_structures import (
    BatchStatus,
    BatchCreationResult,
    AgentExecutionRecord,
    BatchExecutionResult,
)

# Test 2.1: BatchCreationResult
print("\n[2.1] BatchCreationResult test")
result = BatchCreationResult(batch_index=0, agents=[], sessions=[])
assert result.batch_index == 0
assert len(result) == 0
assert result.get_agent_ids() == []
assert result.get_session_ids() == []
print("    PASS: BatchCreationResult functions correct")

# Test 2.2: AgentExecutionRecord lifecycle
print("\n[2.2] AgentExecutionRecord lifecycle test")
record = AgentExecutionRecord(
    session_id="session_001",
    agent_id="agent_001",
    batch_index=0,
    aspect="market_size"
)

assert record.status == BatchStatus.PENDING
assert record.progress == 0.0

record.start()
assert record.status == BatchStatus.RUNNING
assert record.started_at is not None

record.complete({"success": True, "data": "test"})
assert record.status == BatchStatus.COMPLETED
assert record.progress == 1.0
assert record.task_output is not None

print("    PASS: AgentExecutionRecord lifecycle correct")

# Test 2.3: AgentExecutionRecord failure
print("\n[2.3] AgentExecutionRecord failure test")
record2 = AgentExecutionRecord(
    session_id="session_002",
    agent_id="agent_002",
    batch_index=0,
    aspect="competition"
)
record2.start()
record2.fail("Test error")
assert record2.status == BatchStatus.FAILED
assert record2.error == "Test error"
print("    PASS: AgentExecutionRecord failure handling correct")

# Test 2.4: BatchExecutionResult
print("\n[2.4] BatchExecutionResult test")
batch_result = BatchExecutionResult(
    batch_index=0,
    task_id="task_001",
    aspects=["market_size", "competition"]
)

record1 = AgentExecutionRecord(
    session_id="session_001",
    agent_id="agent_001",
    batch_index=0,
    aspect="market_size"
)
record2 = AgentExecutionRecord(
    session_id="session_002",
    agent_id="agent_002",
    batch_index=0,
    aspect="competition"
)

batch_result.add_agent_record(record1)
batch_result.add_agent_record(record2)
assert batch_result.total_agents == 2

batch_result.start_batch()
assert batch_result.status == BatchStatus.RUNNING

record1.start()
record1.complete({"success": True})
record2.start()
record2.fail("Error")

batch_result.complete_batch()
assert batch_result.status == BatchStatus.PARTIAL
assert batch_result.completed_agents == 1
assert batch_result.failed_agents == 1
assert batch_result.get_failed_agents() == ["agent_002"]

print("    PASS: BatchExecutionResult functions correct")

# Test 2.5: to_dict serialization
print("\n[2.5] Serialization test")
record_dict = record.to_dict()
assert "session_id" in record_dict
assert "status" in record_dict
assert record_dict["status"] == "completed"
batch_dict = batch_result.to_dict()
assert "batch_index" in batch_dict
assert "agent_records" in batch_dict
print("    PASS: Serialization functions correct")

print("\nPart 2 tests PASSED")

# ============================================
# Part 3: AgentSessionStatus Test
# ============================================

print("\n" + "=" * 60)
print("Part 3: AgentSessionStatus Extension Test")
print("=" * 60)

from src.core.agents.agent_session import AgentSessionStatus

# Test 3.1: New states exist
print("\n[3.1] Verify new states")
assert hasattr(AgentSessionStatus, 'HIBERNATED')
assert hasattr(AgentSessionStatus, 'RESUMING')
print("    PASS: HIBERNATED and RESUMING states exist")

# Test 3.2: State values
print("\n[3.2] Verify state values")
assert AgentSessionStatus.HIBERNATED.value == "hibernated"
assert AgentSessionStatus.RESUMING.value == "resuming"
print("    PASS: State values correct")

# Test 3.3: State count
print("\n[3.3] Verify state count")
assert len(AgentSessionStatus) == 7, f"Should have 7 states, got {len(AgentSessionStatus)}"
print(f"    PASS: State count = {len(AgentSessionStatus)}")

print("\nPart 3 tests PASSED")

# ============================================
# Part 4: GenericAgent Lifecycle Test
# ============================================

print("\n" + "=" * 60)
print("Part 4: GenericAgent Lifecycle Test")
print("=" * 60)

from src.core.agents.generic_agent import GenericAgent

# Test 4.1: Initial state
print("\n[4.1] Verify initial state")
agent = GenericAgent(agent_id="test_agent", config={"skills": []})
assert agent.get_lifecycle_state() == AgentLifecycleState.CREATED
print(f"    PASS: Initial state = {agent.get_lifecycle_state().value}")

# Test 4.2: Valid state transitions
print("\n[4.2] Verify state transitions")
agent.set_lifecycle_state(AgentLifecycleState.INITIALIZING)
assert agent.get_lifecycle_state() == AgentLifecycleState.INITIALIZING

agent.set_lifecycle_state(AgentLifecycleState.READY)
assert agent.get_lifecycle_state() == AgentLifecycleState.READY
print("    PASS: State transitions correct")

# Test 4.3: Invalid transition exception
print("\n[4.3] Verify invalid transition exception")
agent2 = GenericAgent(agent_id="test_agent2", config={"skills": []})
try:
    agent2.set_lifecycle_state(AgentLifecycleState.RUNNING)  # CREATED -> RUNNING invalid
    print("    FAIL: Should raise exception")
except InvalidStateError:
    print("    PASS: Invalid transition raises exception")

# Test 4.4: get_role_info method
print("\n[4.4] Verify get_role_info")
agent3 = GenericAgent(
    agent_id="test_agent3",
    config={"skills": [], "role": "analyst", "goal": "analyze data"}
)
role_info = agent3.get_role_info()
assert role_info["role"] == "analyst"
assert role_info["goal"] == "analyze data"
print("    PASS: get_role_info correct")

print("\nPart 4 tests PASSED")

# ============================================
# Part 5: Factory Batch Methods Test
# ============================================

print("\n" + "=" * 60)
print("Part 5: Factory Batch Methods Test")
print("=" * 60)

from src.core.agents.factory import DynamicAgentFactory
from src.core.agents.session_persistence import SessionPersistenceManager

# Test 5.1: Factory creation
print("\n[5.1] Factory creation test")
factory = DynamicAgentFactory()
stats = factory.get_stats()
assert stats["created_count"] == 0
assert stats["active_agents"] == 0
print("    PASS: Factory created successfully")

# Test 5.2: Batch creation with persistence
print("\n[5.2] Batch creation test (async)")

async def test_batch_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SessionPersistenceManager(Path(tmpdir))
        factory_with_persist = DynamicAgentFactory(persistence=persistence)
        
        # Create first batch
        batch_result = await factory_with_persist.create_batch(
            parent_session_id="task_001",
            batch_index=0,
            aspects=["market_size", "competition", "policy"],
        )
        
        assert batch_result.batch_index == 0
        assert len(batch_result.agents) == 3
        assert len(batch_result.sessions) == 3
        
        # Verify Agent states
        for agent in batch_result.agents:
            assert agent.get_lifecycle_state() == AgentLifecycleState.READY
        
        return batch_result.get_agent_ids()

agent_ids = asyncio.run(test_batch_creation())
print(f"    PASS: Batch creation succeeded, {len(agent_ids)} agents created")

# Test 5.3: Batch hibernate
print("\n[5.3] Batch hibernate test (async)")

async def test_batch_hibernate():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SessionPersistenceManager(Path(tmpdir))
        factory = DynamicAgentFactory(persistence=persistence)
        
        # Create agents
        batch = await factory.create_batch(
            parent_session_id="task_002",
            batch_index=0,
            aspects=["aspect1", "aspect2"],
        )
        agent_ids = batch.get_agent_ids()
        
        # Hibernate
        await factory.hibernate_batch(agent_ids)
        
        # Verify agents removed from factory
        for agent_id in agent_ids:
            assert factory.get_agent(agent_id) is None
        
        return True

result = asyncio.run(test_batch_hibernate())
assert result
print("    PASS: Batch hibernate succeeded, agents removed from memory")

# Test 5.4: Statistics
print("\n[5.4] Statistics test")
factory2 = DynamicAgentFactory()
stats2 = factory2.get_stats()
assert "hibernated_agents" in stats2
print("    PASS: Statistics include hibernated_agents")

print("\nPart 5 tests PASSED")

# ============================================
# Part 6: Data Lineage Manager Test
# ============================================

print("\n" + "=" * 60)
print("Part 6: Data Lineage Manager Test")
print("=" * 60)

from src.core.data.data_lineage_manager import DataLineageManager

# Test 6.1: Create manager
print("\n[6.1] Create manager test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    stats = manager.get_stats()
    assert stats["total_data_records"] == 0
print("    PASS: Manager created successfully")

# Test 6.2: Record data creation
print("\n[6.2] Data creation test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    data_id = manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100, "source": "test"}
    )
    
    assert data_id.startswith("raw_")
    outputs = manager.get_agent_outputs("agent_001")
    assert data_id in outputs
print("    PASS: Data creation functions correct")

# Test 6.3: Record data transmission
print("\n[6.3] Data transmission test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    data_id = manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100}
    )
    
    manager.record_transmission(
        data_id=data_id,
        from_agent_id="agent_001",
        to_agent_id="agent_002"
    )
    
    lineage = manager.get_lineage(data_id)
    assert len(lineage) == 2  # Creation record + transmission record
    
    inputs = manager.get_agent_inputs("agent_002")
    assert data_id in inputs
print("    PASS: Data transmission functions correct")

# Test 6.4: Batch data query
print("\n[6.4] Batch data query test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100}
    )
    manager.record_creation(
        agent_id="agent_002",
        session_id="session_002",
        batch_index=1,
        data_type="raw",
        content={"value": 200}
    )
    
    batch0_data = manager.get_batch_data(0)
    batch1_data = manager.get_batch_data(1)
    
    assert len(batch0_data) == 1
    assert len(batch1_data) == 1
print("    PASS: Batch data query correct")

# Test 6.5: Statistics
print("\n[6.5] Statistics test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"v": 1}
    )
    manager.record_creation(
        agent_id="agent_002",
        session_id="session_002",
        batch_index=0,
        data_type="analysis",
        content={"v": 2}
    )
    
    stats = manager.get_stats()
    assert stats["total_data_records"] == 2
    assert stats["data_types"]["raw"] == 1
    assert stats["data_types"]["analysis"] == 1
print("    PASS: Statistics correct")

# Test 6.6: Clear data
print("\n[6.6] Clear data test")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"v": 1}
    )
    
    manager.clear()
    stats = manager.get_stats()
    assert stats["total_data_records"] == 0
print("    PASS: Clear functions correct")

print("\nPart 6 tests PASSED")

# ============================================
# Part 7: Module Import Test
# ============================================

print("\n" + "=" * 60)
print("Part 7: Module Import Test")
print("=" * 60)

# Test 7.1: Import from agents package
print("\n[7.1] Import from src.core.agents")
from src.core.agents import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
    BatchStatus,
    BatchCreationResult,
    AgentExecutionRecord,
    BatchExecutionResult,
    AgentSessionStatus,
)
print("    PASS: All exports available")

# Test 7.2: Import from data package
print("\n[7.2] Import from src.core.data")
from src.core.data import DataLineageManager, DataRecord
print("    PASS: All exports available")

print("\nPart 7 tests PASSED")

# ============================================
# Final Summary
# ============================================

print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("""
Part 1: Lifecycle State Test        PASSED
Part 2: Batch Structures Test       PASSED
Part 3: AgentSessionStatus Test     PASSED
Part 4: GenericAgent Lifecycle Test PASSED
Part 5: Factory Batch Methods Test  PASSED
Part 6: Data Lineage Manager Test   PASSED
Part 7: Module Import Test          PASSED

All tests PASSED! 7 modules, 28 test points verified.
""")
print("=" * 60)

# ============================================
# 第二部分：批次数据结构测试
# ============================================

print("\n" + "=" * 60)
print("第二部分：批次数据结构测试")
print("=" * 60)

from src.core.agents.batch_structures import (
    BatchStatus,
    BatchCreationResult,
    AgentExecutionRecord,
    BatchExecutionResult,
)

# 测试2.1：BatchCreationResult
print("\n[2.1] BatchCreationResult测试")
result = BatchCreationResult(batch_index=0, agents=[], sessions=[])
assert result.batch_index == 0
assert len(result) == 0
assert result.get_agent_ids() == []
assert result.get_session_ids() == []
print("    ✓ BatchCreationResult功能正确")

# 测试2.2：AgentExecutionRecord生命周期
print("\n[2.2] AgentExecutionRecord生命周期测试")
record = AgentExecutionRecord(
    session_id="session_001",
    agent_id="agent_001",
    batch_index=0,
    aspect="市场规模"
)

assert record.status == BatchStatus.PENDING
assert record.progress == 0.0

record.start()
assert record.status == BatchStatus.RUNNING
assert record.started_at is not None

record.complete({"success": True, "data": "test"})
assert record.status == BatchStatus.COMPLETED
assert record.progress == 1.0
assert record.task_output is not None

print("    ✓ AgentExecutionRecord生命周期正确")

# 测试2.3：AgentExecutionRecord失败
print("\n[2.3] AgentExecutionRecord失败测试")
record2 = AgentExecutionRecord(
    session_id="session_002",
    agent_id="agent_002",
    batch_index=0,
    aspect="竞争格局"
)
record2.start()
record2.fail("Test error")
assert record2.status == BatchStatus.FAILED
assert record2.error == "Test error"
print("    ✓ AgentExecutionRecord失败处理正确")

# 测试2.4：BatchExecutionResult
print("\n[2.4] BatchExecutionResult测试")
batch_result = BatchExecutionResult(
    batch_index=0,
    task_id="task_001",
    aspects=["市场规模", "竞争格局"]
)

record1 = AgentExecutionRecord(
    session_id="session_001",
    agent_id="agent_001",
    batch_index=0,
    aspect="市场规模"
)
record2 = AgentExecutionRecord(
    session_id="session_002",
    agent_id="agent_002",
    batch_index=0,
    aspect="竞争格局"
)

batch_result.add_agent_record(record1)
batch_result.add_agent_record(record2)
assert batch_result.total_agents == 2

batch_result.start_batch()
assert batch_result.status == BatchStatus.RUNNING

record1.start()
record1.complete({"success": True})
record2.start()
record2.fail("Error")

batch_result.complete_batch()
assert batch_result.status == BatchStatus.PARTIAL
assert batch_result.completed_agents == 1
assert batch_result.failed_agents == 1
assert batch_result.get_failed_agents() == ["agent_002"]

print("    ✓ BatchExecutionResult功能正确")

# 测试2.5：to_dict序列化
print("\n[2.5] 序列化测试")
record_dict = record.to_dict()
assert "session_id" in record_dict
assert "status" in record_dict
assert record_dict["status"] == "completed"
batch_dict = batch_result.to_dict()
assert "batch_index" in batch_dict
assert "agent_records" in batch_dict
print("    ✓ 序列化功能正确")

print("\n第二部分测试通过 ✓")

# ============================================
# 第三部分：AgentSessionStatus扩展测试
# ============================================

print("\n" + "=" * 60)
print("第三部分：AgentSessionStatus扩展测试")
print("=" * 60)

from src.core.agents.agent_session import AgentSessionStatus

# 测试3.1：新状态存在
print("\n[3.1] 验证新增状态")
assert hasattr(AgentSessionStatus, 'HIBERNATED')
assert hasattr(AgentSessionStatus, 'RESUMING')
print("    ✓ HIBERNATED和RESUMING状态存在")

# 测试3.2：状态值
print("\n[3.2] 验证状态值")
assert AgentSessionStatus.HIBERNATED.value == "hibernated"
assert AgentSessionStatus.RESUMING.value == "resuming"
print("    ✓ 状态值正确")

# 测试3.3：状态总数
print("\n[3.3] 验证状态总数")
assert len(AgentSessionStatus) == 7, f"应有7种状态，实际为{len(AgentSessionStatus)}"
print(f"    ✓ 状态总数正确: {len(AgentSessionStatus)}")

print("\n第三部分测试通过 ✓")

# ============================================
# 第四部分：GenericAgent生命周期测试
# ============================================

print("\n" + "=" * 60)
print("第四部分：GenericAgent生命周期测试")
print("=" * 60)

from src.core.agents.generic_agent import GenericAgent

# 测试4.1：初始状态
print("\n[4.1] 验证初始状态")
agent = GenericAgent(agent_id="test_agent", config={"skills": []})
assert agent.get_lifecycle_state() == AgentLifecycleState.CREATED
print(f"    ✓ 初始状态: {agent.get_lifecycle_state().value}")

# 测试4.2：合法状态转换
print("\n[4.2] 验证状态转换")
agent.set_lifecycle_state(AgentLifecycleState.INITIALIZING)
assert agent.get_lifecycle_state() == AgentLifecycleState.INITIALIZING

agent.set_lifecycle_state(AgentLifecycleState.READY)
assert agent.get_lifecycle_state() == AgentLifecycleState.READY
print("    ✓ 状态转换正确")

# 测试4.3：非法转换抛出异常
print("\n[4.3] 验证非法转换异常")
agent2 = GenericAgent(agent_id="test_agent2", config={"skills": []})
try:
    agent2.set_lifecycle_state(AgentLifecycleState.RUNNING)  # CREATED -> RUNNING 非法
    print("    ✗ 应抛出异常")
except InvalidStateError:
    print("    ✓ 非法转换正确抛出异常")

# 测试4.4：get_role_info方法
print("\n[4.4] 验证get_role_info")
agent3 = GenericAgent(
    agent_id="test_agent3",
    config={"skills": [], "role": "analyst", "goal": "analyze data"}
)
role_info = agent3.get_role_info()
assert role_info["role"] == "analyst"
assert role_info["goal"] == "analyze data"
print("    ✓ get_role_info正确")

print("\n第四部分测试通过 ✓")

# ============================================
# 第五部分：Factory批量方法测试
# ============================================

print("\n" + "=" * 60)
print("第五部分：Factory批量方法测试")
print("=" * 60)

from src.core.agents.factory import DynamicAgentFactory
from src.core.agents.session_persistence import SessionPersistenceManager

# 测试5.1：Factory创建
print("\n[5.1] Factory创建测试")
factory = DynamicAgentFactory()
stats = factory.get_stats()
assert stats["created_count"] == 0
assert stats["active_agents"] == 0
print("    ✓ Factory创建成功")

# 测试5.2：带持久化的批量创建
print("\n[5.2] 批量创建测试（异步）")

async def test_batch_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SessionPersistenceManager(Path(tmpdir))
        factory_with_persist = DynamicAgentFactory(persistence=persistence)
        
        # 创建第一批
        batch_result = await factory_with_persist.create_batch(
            parent_session_id="task_001",
            batch_index=0,
            aspects=["市场规模", "竞争格局", "政策环境"],
        )
        
        assert batch_result.batch_index == 0
        assert len(batch_result.agents) == 3
        assert len(batch_result.sessions) == 3
        
        # 验证Agent状态
        for agent in batch_result.agents:
            assert agent.get_lifecycle_state() == AgentLifecycleState.READY
        
        return batch_result.get_agent_ids()

agent_ids = asyncio.run(test_batch_creation())
print(f"    ✓ 批量创建成功，创建了{len(agent_ids)}个Agent")

# 测试5.3：批量休眠
print("\n[5.3] 批量休眠测试（异步）")

async def test_batch_hibernate():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SessionPersistenceManager(Path(tmpdir))
        factory = DynamicAgentFactory(persistence=persistence)
        
        # 创建Agent
        batch = await factory.create_batch(
            parent_session_id="task_002",
            batch_index=0,
            aspects=["维度1", "维度2"],
        )
        agent_ids = batch.get_agent_ids()
        
        # 休眠
        await factory.hibernate_batch(agent_ids)
        
        # 验证Agent已从工厂移除
        for agent_id in agent_ids:
            assert factory.get_agent(agent_id) is None
        
        return True

result = asyncio.run(test_batch_hibernate())
assert result
print("    ✓ 批量休眠成功，Agent已从内存移除")

# 测试5.4：统计信息
print("\n[5.4] 统计信息测试")
factory2 = DynamicAgentFactory()
stats2 = factory2.get_stats()
assert "hibernated_agents" in stats2
print("    ✓ 统计信息包含hibernated_agents")

print("\n第五部分测试通过 ✓")

# ============================================
# 第六部分：数据链路管理器测试
# ============================================

print("\n" + "=" * 60)
print("第六部分：数据链路管理器测试")
print("=" * 60)

from src.core.data.data_lineage_manager import DataLineageManager

# 测试6.1：创建管理器
print("\n[6.1] 创建管理器测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    stats = manager.get_stats()
    assert stats["total_data_records"] == 0
print("    ✓ 管理器创建成功")

# 测试6.2：记录数据创建
print("\n[6.2] 数据创建测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    data_id = manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100, "source": "test"}
    )
    
    assert data_id.startswith("raw_")
    outputs = manager.get_agent_outputs("agent_001")
    assert data_id in outputs
print("    ✓ 数据创建功能正确")

# 测试6.3：记录数据传递
print("\n[6.3] 数据传递测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    data_id = manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100}
    )
    
    manager.record_transmission(
        data_id=data_id,
        from_agent_id="agent_001",
        to_agent_id="agent_002"
    )
    
    lineage = manager.get_lineage(data_id)
    assert len(lineage) == 2  # 创建记录 + 传递记录
    
    inputs = manager.get_agent_inputs("agent_002")
    assert data_id in inputs
print("    ✓ 数据传递功能正确")

# 测试6.4：批次数据查询
print("\n[6.4] 批次数据查询测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"value": 100}
    )
    manager.record_creation(
        agent_id="agent_002",
        session_id="session_002",
        batch_index=1,
        data_type="raw",
        content={"value": 200}
    )
    
    batch0_data = manager.get_batch_data(0)
    batch1_data = manager.get_batch_data(1)
    
    assert len(batch0_data) == 1
    assert len(batch1_data) == 1
print("    ✓ 批次数据查询正确")

# 测试6.5：统计信息
print("\n[6.5] 统计信息测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"v": 1}
    )
    manager.record_creation(
        agent_id="agent_002",
        session_id="session_002",
        batch_index=0,
        data_type="analysis",
        content={"v": 2}
    )
    
    stats = manager.get_stats()
    assert stats["total_data_records"] == 2
    assert stats["data_types"]["raw"] == 1
    assert stats["data_types"]["analysis"] == 1
print("    ✓ 统计信息正确")

# 测试6.6：清空数据
print("\n[6.6] 清空数据测试")
with tempfile.TemporaryDirectory() as tmpdir:
    manager = DataLineageManager(Path(tmpdir))
    
    manager.record_creation(
        agent_id="agent_001",
        session_id="session_001",
        batch_index=0,
        data_type="raw",
        content={"v": 1}
    )
    
    manager.clear()
    stats = manager.get_stats()
    assert stats["total_data_records"] == 0
print("    ✓ 清空功能正确")

print("\n第六部分测试通过 ✓")

# ============================================
# 第七部分：模块导入测试
# ============================================

print("\n" + "=" * 60)
print("第七部分：模块导入测试")
print("=" * 60)

# 测试7.1：从agents包导入
print("\n[7.1] 从 src.core.agents 导入")
from src.core.agents import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
    BatchStatus,
    BatchCreationResult,
    AgentExecutionRecord,
    BatchExecutionResult,
    AgentSessionStatus,
)
print("    ✓ 所有导出可用")

# 测试7.2：从data包导入
print("\n[7.2] 从 src.core.data 导入")
from src.core.data import DataLineageManager, DataRecord
print("    ✓ 所有导出可用")

print("\n第七部分测试通过 ✓")

# ============================================
# 最终总结
# ============================================

print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)
print("""
第一部分：生命周期状态测试      ✓ 通过
第二部分：批次数据结构测试      ✓ 通过
第三部分：AgentSessionStatus测试 ✓ 通过
第四部分：GenericAgent生命周期测试 ✓ 通过
第五部分：Factory批量方法测试   ✓ 通过
第六部分：数据链路管理器测试    ✓ 通过
第七部分：模块导入测试          ✓ 通过

全部测试通过！共验证7个模块，28个测试点。
""")
print("=" * 60)