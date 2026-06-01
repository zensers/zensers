"""
交互式恢复模块测试

测试 InteractiveRecovery 的核心功能。
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from src.core.agents.interactive_recovery import (
    InteractiveRecovery,
    RecoveryCandidate,
    cmd_resume,
)
from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionRegistry,
    AgentSessionStatus,
    SessionOrigin,
    generate_session_id,
)


# === Fixtures ===

@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def recovery(temp_storage):
    """创建 InteractiveRecovery 实例"""
    return InteractiveRecovery(temp_storage)


@pytest.fixture
def interrupted_registry(temp_storage):
    """创建中断的 Registry"""
    registry = AgentSessionRegistry(parent_session_id="research_interrupted_001")
    
    # 完成的 Agent
    completed = AgentSession(
        session_id=generate_session_id(prefix="agent"),
        agent_id="completed_agent",
        parent_session_id="research_interrupted_001",
        origin=SessionOrigin.SPAWNED,
        status=AgentSessionStatus.COMPLETED,
        progress=1.0,
        context={"topic": "测试主题"}
    )
    registry.register(completed)
    
    # 运行中的 Agent
    running = AgentSession(
        session_id=generate_session_id(prefix="agent"),
        agent_id="running_agent",
        parent_session_id="research_interrupted_001",
        origin=SessionOrigin.SPAWNED,
        status=AgentSessionStatus.RUNNING,
        progress=0.5,
        context={"topic": "测试主题"}
    )
    registry.register(running)
    
    # 待执行的 Agent
    pending = AgentSession(
        session_id=generate_session_id(prefix="agent"),
        agent_id="pending_agent",
        parent_session_id="research_interrupted_001",
        origin=SessionOrigin.SPAWNED,
        status=AgentSessionStatus.PENDING,
        progress=0.0,
        context={"topic": "测试主题"}
    )
    registry.register(pending)
    
    # 保存
    registry.save(temp_storage)
    
    return registry


# === Tests ===

class TestRecoveryCandidate:
    """测试 RecoveryCandidate"""
    
    def test_create_candidate(self):
        """测试创建候选项"""
        candidate = RecoveryCandidate(
            session_id="research_test_001",
            topic="测试主题",
            status="中断",
            total_agents=3,
            running_agents=1,
            pending_agents=1,
            completed_agents=1,
            progress=0.5,
        )
        
        assert candidate.session_id == "research_test_001"
        assert candidate.topic == "测试主题"
        assert candidate.total_agents == 3
    
    def test_progress_bar(self):
        """测试进度条生成"""
        candidate = RecoveryCandidate(
            session_id="test",
            topic="test",
            status="中断",
            total_agents=1,
            running_agents=0,
            pending_agents=0,
            completed_agents=0,
            progress=0.5,
        )
        
        bar = candidate._progress_bar(0.5)
        assert "█" in bar
        assert "░" in bar
    
    def test_to_display_string(self):
        """测试显示字符串"""
        candidate = RecoveryCandidate(
            session_id="research_test_001",
            topic="测试主题",
            status="中断",
            total_agents=3,
            running_agents=1,
            pending_agents=1,
            completed_agents=1,
            progress=0.33,
        )
        
        display = candidate.to_display_string(1)
        
        assert "research_test_001" in display
        assert "测试主题" in display
        assert "33%" in display


class TestInteractiveRecovery:
    """测试 InteractiveRecovery"""
    
    def test_scan_empty_storage(self, recovery):
        """测试扫描空存储"""
        candidates = recovery.scan_interrupted_tasks()
        
        assert candidates == []
    
    def test_scan_interrupted_tasks(self, recovery, interrupted_registry):
        """测试扫描中断的任务"""
        candidates = recovery.scan_interrupted_tasks()
        
        assert len(candidates) == 1
        assert candidates[0].session_id == "research_interrupted_001"
        assert candidates[0].total_agents == 3
        assert candidates[0].running_agents == 1
        assert candidates[0].pending_agents == 1
        assert candidates[0].completed_agents == 1
    
    def test_display_candidates(self, recovery, interrupted_registry):
        """测试显示候选项"""
        recovery.scan_interrupted_tasks()
        display = recovery.display_candidates()
        
        assert "research_interrupted_001" in display
        assert "测试主题" in display
        assert "1 个可恢复的任务" in display
    
    def test_get_candidate(self, recovery, interrupted_registry):
        """测试获取候选项"""
        recovery.scan_interrupted_tasks()
        
        candidate = recovery.get_candidate(1)
        assert candidate is not None
        assert candidate.session_id == "research_interrupted_001"
        
        # 无效索引
        assert recovery.get_candidate(0) is None
        assert recovery.get_candidate(99) is None
    
    def test_get_task_details(self, recovery, interrupted_registry):
        """测试获取任务详情"""
        details = recovery.get_task_details("research_interrupted_001")
        
        assert details["session_id"] == "research_interrupted_001"
        assert details["total_agents"] == 3
        assert len(details["completed_agents"]) == 1
        assert len(details["running_agents"]) == 1
        assert len(details["pending_agents"]) == 1
    
    def test_display_task_details(self, recovery, interrupted_registry):
        """测试显示任务详情"""
        display = recovery.display_task_details("research_interrupted_001")
        
        assert "research_interrupted_001" in display
        assert "已完成" in display
        assert "运行中" in display
        assert "待执行" in display
        assert "[c] 继续执行" in display


class TestMultipleInterruptedTasks:
    """测试多个中断任务"""
    
    def test_scan_multiple_tasks(self, temp_storage):
        """测试扫描多个中断任务"""
        # 创建第一个中断任务
        registry1 = AgentSessionRegistry(parent_session_id="research_task_001")
        registry1.register(AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_001",
            parent_session_id="research_task_001",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.3,
            context={"topic": "任务一"}
        ))
        registry1.save(temp_storage)
        
        # 创建第二个中断任务
        registry2 = AgentSessionRegistry(parent_session_id="research_task_002")
        registry2.register(AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_002",
            parent_session_id="research_task_002",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.PENDING,
            progress=0.0,
            context={"topic": "任务二"}
        ))
        registry2.save(temp_storage)
        
        # 扫描
        recovery = InteractiveRecovery(temp_storage)
        candidates = recovery.scan_interrupted_tasks()
        
        assert len(candidates) == 2
    
    def test_ignore_completed_tasks(self, temp_storage):
        """测试忽略已完成的任务"""
        # 创建已完成的任务
        registry = AgentSessionRegistry(parent_session_id="research_completed_001")
        registry.register(AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="completed",
            parent_session_id="research_completed_001",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.COMPLETED,
            progress=1.0,
            context={"topic": "已完成任务"}
        ))
        registry.save(temp_storage)
        
        # 扫描
        recovery = InteractiveRecovery(temp_storage)
        candidates = recovery.scan_interrupted_tasks()
        
        # 应该为空，因为没有 RUNNING 或 PENDING 状态
        assert len(candidates) == 0


# === Run Tests ===

if __name__ == "__main__":
    pytest.main([__file__, "-v"])