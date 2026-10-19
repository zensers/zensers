"""
Agent Session 单元测试

测试 AgentSession 和 AgentSessionRegistry 数据结构
"""
import pytest
from datetime import datetime
from typing import Dict, Any, Optional

# 测试目标模块（待实现）
from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionStatus,
    AgentSessionRegistry,
    SessionOrigin,
)


class TestAgentSessionStatus:
    """测试 AgentSessionStatus 枚举"""
    
    def test_status_values(self):
        """测试状态枚举值"""
        assert AgentSessionStatus.PENDING.value == "pending"
        assert AgentSessionStatus.RUNNING.value == "running"
        assert AgentSessionStatus.COMPLETED.value == "completed"
        assert AgentSessionStatus.FAILED.value == "failed"
        assert AgentSessionStatus.CANCELLED.value == "cancelled"
    
    def test_status_count(self):
        """测试状态数量"""
        assert len(AgentSessionStatus) == 7


class TestSessionOrigin:
    """测试 SessionOrigin 枚举"""
    
    def test_origin_values(self):
        """测试来源枚举值"""
        assert SessionOrigin.PRIMARY.value == "primary"
        assert SessionOrigin.SPAWNED.value == "spawned"
        assert SessionOrigin.BACKGROUND.value == "background"
    
    def test_origin_count(self):
        """测试来源数量"""
        assert len(SessionOrigin) == 3


class TestAgentSession:
    """测试 AgentSession 数据类"""
    
    def test_create_minimal_session(self):
        """测试创建最小Session"""
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        
        assert session.session_id == "session_001"
        assert session.agent_id == "agent_001"
        assert session.parent_session_id is None
        assert session.origin == SessionOrigin.PRIMARY
        assert session.status == AgentSessionStatus.PENDING
        assert session.progress == 0.0
        assert session.result is None
    
    def test_create_full_session(self):
        """测试创建完整Session"""
        session = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            parent_session_id="parent_001",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.5,
            result={"data": "test"},
            task={"action": "research"},
            context={"topic": "AI"}
        )
        
        assert session.session_id == "session_002"
        assert session.agent_id == "agent_002"
        assert session.parent_session_id == "parent_001"
        assert session.origin == SessionOrigin.SPAWNED
        assert session.status == AgentSessionStatus.RUNNING
        assert session.progress == 0.5
        assert session.result == {"data": "test"}
        assert session.task == {"action": "research"}
        assert session.context == {"topic": "AI"}
    
    def test_session_has_timestamps(self):
        """测试Session有时间戳"""
        session = AgentSession(
            session_id="session_003",
            agent_id="agent_003"
        )
        
        assert session.created_at is not None
        assert isinstance(session.created_at, datetime)
        assert session.started_at is None
        assert session.completed_at is None
    
    def test_session_to_dict(self):
        """测试Session转换为字典"""
        session = AgentSession(
            session_id="session_004",
            agent_id="agent_004",
            parent_session_id="parent_001",
            status=AgentSessionStatus.COMPLETED,
            progress=1.0,
            result={"output": "success"}
        )
        
        data = session.to_dict()
        
        assert data["session_id"] == "session_004"
        assert data["agent_id"] == "agent_004"
        assert data["parent_session_id"] == "parent_001"
        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert data["result"] == {"output": "success"}
        assert "created_at" in data
    
    def test_session_from_dict(self):
        """测试从字典创建Session"""
        data = {
            "session_id": "session_005",
            "agent_id": "agent_005",
            "parent_session_id": "parent_001",
            "origin": "spawned",
            "status": "running",
            "progress": 0.7,
            "result": None,
            "created_at": "2026-04-10T10:00:00",
            "started_at": "2026-04-10T10:01:00",
            "completed_at": None,
            "task": {"action": "analyze"},
            "context": {"aspect": "competition"}
        }
        
        session = AgentSession.from_dict(data)
        
        assert session.session_id == "session_005"
        assert session.agent_id == "agent_005"
        assert session.parent_session_id == "parent_001"
        assert session.origin == SessionOrigin.SPAWNED
        assert session.status == AgentSessionStatus.RUNNING
        assert session.progress == 0.7
        assert session.task == {"action": "analyze"}


class TestAgentSessionRegistry:
    """测试 AgentSessionRegistry 注册表"""
    
    def test_create_registry(self):
        """测试创建注册表"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        
        assert registry.parent_session_id == "parent_001"
        assert len(registry.child_sessions) == 0
    
    def test_register_session(self):
        """测试注册Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        
        registry.register(session)
        
        assert len(registry.child_sessions) == 1
        assert "session_001" in registry.child_sessions
        assert session.parent_session_id == "parent_001"
    
    def test_get_session(self):
        """测试获取Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        retrieved = registry.get_session("session_001")
        
        assert retrieved is not None
        assert retrieved.session_id == "session_001"
    
    def test_get_session_not_found(self):
        """测试获取不存在的Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        
        retrieved = registry.get_session("nonexistent")
        
        assert retrieved is None
    
    def test_get_by_agent(self):
        """测试根据Agent ID获取Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(session_id="session_001", agent_id="agent_001")
        session2 = AgentSession(session_id="session_002", agent_id="agent_002")
        registry.register(session1)
        registry.register(session2)
        
        retrieved = registry.get_by_agent("agent_002")
        
        assert retrieved is not None
        assert retrieved.agent_id == "agent_002"
        assert retrieved.session_id == "session_002"
    
    def test_update_status(self):
        """测试更新Session状态"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        registry.update_status(
            session_id="session_001",
            status=AgentSessionStatus.RUNNING,
            progress=0.5
        )
        
        updated = registry.get_session("session_001")
        assert updated.status == AgentSessionStatus.RUNNING
        assert updated.progress == 0.5
        assert updated.started_at is not None
    
    def test_update_status_with_result(self):
        """测试更新Session状态和结果"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        registry.update_status(
            session_id="session_001",
            status=AgentSessionStatus.COMPLETED,
            progress=1.0,
            result={"output": "success"}
        )
        
        updated = registry.get_session("session_001")
        assert updated.status == AgentSessionStatus.COMPLETED
        assert updated.progress == 1.0
        assert updated.result == {"output": "success"}
        assert updated.completed_at is not None
    
    def test_get_all_status(self):
        """测试获取所有Session状态"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            status=AgentSessionStatus.RUNNING,
            progress=0.5
        )
        session2 = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            status=AgentSessionStatus.COMPLETED,
            progress=1.0,
            result={"done": True}
        )
        registry.register(session1)
        registry.register(session2)
        
        status = registry.get_all_status()
        
        assert len(status) == 2
        assert status["session_001"]["status"] == "running"
        assert status["session_001"]["progress"] == 0.5
        assert status["session_002"]["status"] == "completed"
        assert status["session_002"]["has_result"] is True
    
    def test_get_pending(self):
        """测试获取待执行的Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            status=AgentSessionStatus.PENDING
        )
        session2 = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            status=AgentSessionStatus.RUNNING
        )
        session3 = AgentSession(
            session_id="session_003",
            agent_id="agent_003",
            status=AgentSessionStatus.PENDING
        )
        registry.register(session1)
        registry.register(session2)
        registry.register(session3)
        
        pending = registry.get_pending()
        
        assert len(pending) == 2
        assert all(s.status == AgentSessionStatus.PENDING for s in pending)
    
    def test_get_running(self):
        """测试获取执行中的Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            status=AgentSessionStatus.RUNNING
        )
        session2 = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            status=AgentSessionStatus.COMPLETED
        )
        session3 = AgentSession(
            session_id="session_003",
            agent_id="agent_003",
            status=AgentSessionStatus.RUNNING
        )
        registry.register(session1)
        registry.register(session2)
        registry.register(session3)
        
        running = registry.get_running()
        
        assert len(running) == 2
        assert all(s.status == AgentSessionStatus.RUNNING for s in running)
    
    def test_get_completed(self):
        """测试获取已完成的Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            status=AgentSessionStatus.COMPLETED
        )
        session2 = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            status=AgentSessionStatus.FAILED
        )
        session3 = AgentSession(
            session_id="session_003",
            agent_id="agent_003",
            status=AgentSessionStatus.COMPLETED
        )
        registry.register(session1)
        registry.register(session2)
        registry.register(session3)
        
        completed = registry.get_completed()
        
        assert len(completed) == 2
        assert all(s.status == AgentSessionStatus.COMPLETED for s in completed)
    
    def test_unregister_session(self):
        """测试注销Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        result = registry.unregister("session_001")
        
        assert result is True
        assert len(registry.child_sessions) == 0
    
    def test_unregister_not_found(self):
        """测试注销不存在的Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        
        result = registry.unregister("nonexistent")
        
        assert result is False
    
    def test_clear_all(self):
        """测试清空所有Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session1 = AgentSession(session_id="session_001", agent_id="agent_001")
        session2 = AgentSession(session_id="session_002", agent_id="agent_002")
        registry.register(session1)
        registry.register(session2)
        
        registry.clear()
        
        assert len(registry.child_sessions) == 0


class TestAgentSessionEdgeCases:
    """测试边缘情况"""
    
    def test_progress_bounds(self):
        """测试进度边界值"""
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            progress=0.0
        )
        assert session.progress == 0.0
        
        session = AgentSession(
            session_id="session_002",
            agent_id="agent_002",
            progress=1.0
        )
        assert session.progress == 1.0
    
    def test_status_transition(self):
        """测试状态转换"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        # PENDING -> RUNNING
        registry.update_status("session_001", AgentSessionStatus.RUNNING)
        assert registry.get_session("session_001").status == AgentSessionStatus.RUNNING
        
        # RUNNING -> COMPLETED
        registry.update_status("session_001", AgentSessionStatus.COMPLETED, result={"done": True})
        assert registry.get_session("session_001").status == AgentSessionStatus.COMPLETED
    
    def test_multiple_sessions_same_parent(self):
        """测试同一父Session下的多个子Session"""
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        
        for i in range(5):
            session = AgentSession(
                session_id=f"session_{i:03d}",
                agent_id=f"agent_{i:03d}"
            )
            registry.register(session)
        
        assert len(registry.child_sessions) == 5
    
    def test_session_with_large_result(self):
        """测试包含大量结果的Session"""
        large_result = {"data": list(range(10000))}
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001",
            result=large_result
        )
        
        assert len(session.result["data"]) == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])