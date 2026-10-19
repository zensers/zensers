"""
Session 持久化测试

测试 AgentSession 和 AgentSessionRegistry 的持久化能力：
1. Session 保存和加载
2. Registry 保存和加载
3. 崩溃恢复场景

设计文档: docs/SESSION_PERSISTENCE_DESIGN.md
"""
import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

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
def sample_session():
    """创建示例 Session"""
    return AgentSession(
        session_id=generate_session_id(prefix="agent"),
        agent_id="agent_test_001",
        parent_session_id="research_test_001",
        origin=SessionOrigin.SPAWNED,
        status=AgentSessionStatus.RUNNING,
        progress=0.65,
        task={"action": "research", "aspect": "市场规模"},
        context={"topic": "新能源汽车"},
        result={"partial_data": "some results"}
    )


@pytest.fixture
def sample_registry():
    """创建示例 Registry"""
    registry = AgentSessionRegistry(parent_session_id="research_registry_001")
    
    # 添加几个 Session
    for i in range(3):
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id=f"agent_{i}",
            parent_session_id="research_registry_001",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING if i == 0 else AgentSessionStatus.PENDING,
            progress=0.5 if i == 0 else 0.0,
            task={"action": "research"},
            context={"index": i}
        )
        registry.register(session)
    
    return registry


# === Test AgentSession Persistence ===

class TestAgentSessionPersistence:
    """测试 AgentSession 持久化"""
    
    def test_session_to_dict_includes_all_fields(self, sample_session):
        """测试 to_dict 包含所有字段"""
        data = sample_session.to_dict()
        
        assert data["session_id"] == sample_session.session_id
        assert data["agent_id"] == "agent_test_001"
        assert data["parent_session_id"] == "research_test_001"
        assert data["origin"] == "spawned"
        assert data["status"] == "running"
        assert data["progress"] == 0.65
        assert data["task"]["action"] == "research"
        assert data["context"]["topic"] == "新能源汽车"
        assert "created_at" in data
        assert "updated_at" in data
    
    def test_session_from_dict_reconstructs_session(self, sample_session):
        """测试 from_dict 可以重建 Session"""
        data = sample_session.to_dict()
        reconstructed = AgentSession.from_dict(data)
        
        assert reconstructed.session_id == sample_session.session_id
        assert reconstructed.agent_id == sample_session.agent_id
        assert reconstructed.parent_session_id == sample_session.parent_session_id
        assert reconstructed.origin == sample_session.origin
        assert reconstructed.status == sample_session.status
        assert reconstructed.progress == sample_session.progress
        assert reconstructed.task == sample_session.task
        assert reconstructed.context == sample_session.context
        assert reconstructed.result == sample_session.result
    
    def test_session_save_creates_file(self, sample_session, temp_storage):
        """测试 save 创建文件"""
        path = sample_session.save(temp_storage)
        
        assert path.exists()
        assert path.suffix == ".json"
        assert "agent_" in path.name
    
    def test_session_load_from_file(self, sample_session, temp_storage):
        """测试从文件加载 Session"""
        # 保存
        save_path = sample_session.save(temp_storage)
        
        # 加载
        loaded = AgentSession.load(save_path)
        
        assert loaded.session_id == sample_session.session_id
        assert loaded.agent_id == sample_session.agent_id
        assert loaded.status == sample_session.status
        assert loaded.progress == sample_session.progress
    
    def test_session_save_load_preserves_status(self, temp_storage):
        """测试保存和加载保留状态"""
        # 创建 RUNNING 状态的 Session
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_status_test",
            parent_session_id="research_test",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.75
        )
        
        # 保存
        path = session.save(temp_storage)
        
        # 加载
        loaded = AgentSession.load(path)
        
        assert loaded.status == AgentSessionStatus.RUNNING
        assert loaded.progress == 0.75
    
    def test_session_with_checkpoint(self, temp_storage):
        """测试带检查点的 Session"""
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_checkpoint",
            parent_session_id="research_test",
            origin=SessionOrigin.SPAWNED
        )
        
        # 创建检查点
        checkpoint_data = {
            "processed_items": 10,
            "current_step": "data_collection",
            "intermediate_result": {"data": "partial"}
        }
        session.create_checkpoint(checkpoint_data)
        
        # 保存并加载
        path = session.save(temp_storage)
        loaded = AgentSession.load(path)
        
        assert loaded.checkpoint_data == checkpoint_data
        assert loaded.last_checkpoint_at is not None
    
    def test_session_restore_from_checkpoint(self, temp_storage):
        """测试从检查点恢复"""
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_restore",
            parent_session_id="research_test",
            origin=SessionOrigin.SPAWNED
        )
        
        checkpoint = {"step": 3, "data": "saved"}
        session.create_checkpoint(checkpoint)
        
        # 保存并加载
        path = session.save(temp_storage)
        loaded = AgentSession.load(path)
        
        # 恢复检查点
        restored = loaded.restore_from_checkpoint()
        
        assert restored == checkpoint


# === Test AgentSessionRegistry Persistence ===

class TestAgentSessionRegistryPersistence:
    """测试 AgentSessionRegistry 持久化"""
    
    def test_registry_to_dict(self, sample_registry):
        """测试 Registry to_dict"""
        data = sample_registry.to_dict()
        
        assert data["parent_session_id"] == "research_registry_001"
        assert "child_sessions" in data
        assert "saved_at" in data
        assert len(data["child_sessions"]) == 3
    
    def test_registry_save_creates_file(self, sample_registry, temp_storage):
        """测试 Registry save 创建文件"""
        path = sample_registry.save(temp_storage)
        
        assert path.exists()
        assert path.suffix == ".json"
        assert path.name == "research_registry_001.json"
    
    def test_registry_load_from_file(self, sample_registry, temp_storage):
        """测试从文件加载 Registry"""
        # 保存
        save_path = sample_registry.save(temp_storage)
        
        # 加载
        loaded = AgentSessionRegistry.load(save_path)
        
        assert loaded.parent_session_id == sample_registry.parent_session_id
        assert loaded.count() == 3
    
    def test_registry_save_load_preserves_sessions(self, sample_registry, temp_storage):
        """测试保存和加载保留所有 Session"""
        # 保存
        path = sample_registry.save(temp_storage)
        
        # 加载
        loaded = AgentSessionRegistry.load(path)
        
        # 验证所有 Session 都保留
        original_sessions = list(sample_registry.child_sessions.values())
        
        for orig in original_sessions:
            found = loaded.get_session(orig.session_id)
            assert found is not None
            assert found.agent_id == orig.agent_id
            assert found.status == orig.status
    
    def test_registry_save_load_preserves_status(self, temp_storage):
        """测试保存和加载保留 Session 状态"""
        registry = AgentSessionRegistry(parent_session_id="research_status_test")
        
        # 创建不同状态的 Session
        running_session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="running_agent",
            parent_session_id="research_status_test",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.6
        )
        
        completed_session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="completed_agent",
            parent_session_id="research_status_test",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.COMPLETED,
            progress=1.0,
            result={"data": "done"}
        )
        
        registry.register(running_session)
        registry.register(completed_session)
        
        # 保存并加载
        path = registry.save(temp_storage)
        loaded = AgentSessionRegistry.load(path)
        
        # 验证状态
        running = loaded.get_running()
        completed = loaded.get_completed()
        
        assert len(running) == 1
        assert len(completed) == 1
        assert running[0].progress == 0.6
        assert completed[0].result == {"data": "done"}


# === Test Crash Recovery Scenarios ===

class TestCrashRecoveryScenarios:
    """测试崩溃恢复场景"""
    
    def test_find_interrupted_sessions(self, temp_storage):
        """测试查找中断的 Session"""
        # 创建多个 Registry
        # 1. 完成的任务
        completed_registry = AgentSessionRegistry(parent_session_id="research_completed")
        completed_session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="completed_agent",
            parent_session_id="research_completed",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.COMPLETED
        )
        completed_registry.register(completed_session)
        completed_registry.save(temp_storage)
        
        # 2. 中断的任务 (有 RUNNING Session)
        interrupted_registry = AgentSessionRegistry(parent_session_id="research_interrupted")
        running_session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="running_agent",
            parent_session_id="research_interrupted",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.5
        )
        interrupted_registry.register(running_session)
        interrupted_registry.save(temp_storage)
        
        # 查找中断的 Session
        interrupted = AgentSessionRegistry.find_interrupted(temp_storage)
        
        assert len(interrupted) == 1
        assert interrupted[0].parent_session_id == "research_interrupted"
    
    def test_recovery_info(self, sample_registry, temp_storage):
        """测试恢复信息"""
        # 修改一个 Session 为 COMPLETED
        sessions = list(sample_registry.child_sessions.values())
        sessions[1].status = AgentSessionStatus.COMPLETED
        sessions[1].progress = 1.0
        
        sample_registry.save(temp_storage)
        
        # 加载并获取恢复信息
        loaded = AgentSessionRegistry.load(
            temp_storage / "registries" / "research_registry_001.json"
        )
        
        # 计算恢复信息
        running = loaded.get_running()
        pending = loaded.get_pending()
        completed = loaded.get_completed()
        
        # 验证
        assert len(completed) == 1
        assert len(running) + len(pending) == 2
    
    def test_partial_progress_recovery(self, temp_storage):
        """测试部分进度恢复"""
        # 创建有进度的 Session
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_progress",
            parent_session_id="research_progress",
            origin=SessionOrigin.SPAWNED,
            status=AgentSessionStatus.RUNNING,
            progress=0.75,
            checkpoint_data={
                "processed": 75,
                "total": 100,
                "current_item": "item_75"
            }
        )
        
        # 保存
        session.save(temp_storage)
        
        # 模拟重启：加载
        registries_dir = temp_storage / "sessions" / "agents"
        loaded_path = list(registries_dir.glob("*.json"))[0]
        loaded = AgentSession.load(loaded_path)
        
        # 验证进度和检查点
        assert loaded.progress == 0.75
        assert loaded.checkpoint_data["processed"] == 75
        assert loaded.checkpoint_data["current_item"] == "item_75"


# === Test Edge Cases ===

class TestPersistenceEdgeCases:
    """持久化边界测试"""
    
    def test_save_with_large_result(self, temp_storage):
        """测试保存大结果"""
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_large",
            parent_session_id="research_large",
            origin=SessionOrigin.SPAWNED,
            result={"data": list(range(1000))}
        )
        
        # 应该成功保存
        path = session.save(temp_storage)
        assert path.exists()
        
        # 应该成功加载
        loaded = AgentSession.load(path)
        assert len(loaded.result["data"]) == 1000
    
    def test_save_with_unicode(self, temp_storage):
        """测试保存 Unicode 内容"""
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id="agent_unicode",
            parent_session_id="research_unicode",
            origin=SessionOrigin.SPAWNED,
            context={"topic": "新能源汽车市场规模分析"},
            task={"description": "竞争格局研究"}
        )
        
        path = session.save(temp_storage)
        loaded = AgentSession.load(path)
        
        assert loaded.context["topic"] == "新能源汽车市场规模分析"
        assert loaded.task["description"] == "竞争格局研究"
    
    def test_load_nonexistent_file(self, temp_storage):
        """测试加载不存在的文件"""
        path = temp_storage / "nonexistent.json"
        
        # 应该抛出异常或返回 None
        with pytest.raises(FileNotFoundError):
            AgentSession.load(path)
    
    def test_concurrent_save_load(self, temp_storage):
        """测试并发保存和加载"""
        import asyncio
        
        async def save_session(i):
            session = AgentSession(
                session_id=f"agent_concurrent_{i}",
                agent_id=f"agent_{i}",
                parent_session_id="research_concurrent",
                origin=SessionOrigin.SPAWNED
            )
            session.save(temp_storage)
            return session.session_id
        
        async def run_concurrent():
            tasks = [save_session(i) for i in range(5)]
            return await asyncio.gather(*tasks)
        
        # 运行并发保存
        ids = asyncio.run(run_concurrent())
        
        # 验证所有文件都保存成功
        saved_files = list((temp_storage / "sessions" / "agents").glob("*.json"))
        assert len(saved_files) == 5


# === Run Tests ===

if __name__ == "__main__":
    pytest.main([__file__, "-v"])