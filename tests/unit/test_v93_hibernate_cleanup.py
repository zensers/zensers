"""
v9.3-A8: hibernate 持久化清理

验证:
  1. SessionPersistenceManager 新增 delete_session(session_id) 方法
  2. delete_session 删除 sessions/agents/{id}.json 和 results/{id}/ 目录
  3. factory.clear_registry() 在清理内存后调用 persistence delete
  4. 无 persistence 时跳过 (向后兼容)
  5. 传正确的 session_id (从 agent._session.session_id 取)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
import tempfile
import json


class TestSessionPersistenceDelete:
    """验证 SessionPersistenceManager 新增删除方法"""

    def test_has_delete_session_method(self):
        """SessionPersistenceManager 应有 delete_session 方法"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        mgr = SessionPersistenceManager.__new__(SessionPersistenceManager)
        assert hasattr(mgr, "delete_session"), "Should have delete_session method"
        assert callable(mgr.delete_session), "delete_session should be callable"

    def test_delete_session_removes_session_file(self):
        """delete_session 应删除 sessions/agents/{id}.json"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mgr = SessionPersistenceManager(storage_path=tmp_path)

            # SessionPersistenceManager.sessions_dir = storage_path / "sessions" / "agents"
            session_id = "test_session_001"
            session_file = mgr.sessions_dir / f"{session_id}.json"
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text('{"test": true}')

            assert session_file.exists(), \
                "Session file should exist before delete"

            result = mgr.delete_session(session_id)
            assert result is True, \
                "delete_session should return True on success"
            assert not session_file.exists(), \
                "Session file should be removed after delete"

    def test_delete_session_removes_result_file(self):
        """delete_session 应删除 results/{id}_result.json 单文件"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mgr = SessionPersistenceManager(storage_path=tmp_path)

            session_id = "test_session_file_result"
            # 实际存储: self.results_dir / "{session_id}_result.json"
            result_file = mgr.results_dir / f"{session_id}_result.json"
            result_file.parent.mkdir(parents=True, exist_ok=True)
            result_file.write_text('{"result": true}')

            assert result_file.exists(), \
                "Result file should exist before delete"

            mgr.delete_session(session_id)
            assert not result_file.exists(), \
                "Result file should be removed after delete"

    def test_delete_session_cleans_legacy_results_dir(self):
        """delete_session 应兼容清理旧版目录格式 results/{id}/"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mgr = SessionPersistenceManager(storage_path=tmp_path)

            session_id = "test_legacy_dir"
            # 旧版存储: self.results_dir / "{session_id}/" 目录
            legacy_dir = mgr.results_dir / session_id
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / "data.json").write_text('{"legacy": true}')

            assert legacy_dir.exists(), \
                "Legacy results dir should exist before delete"

            mgr.delete_session(session_id)
            assert not legacy_dir.exists(), \
                "Legacy results dir should be removed after delete"

    def test_delete_session_nonexistent(self):
        """删除不存在的 session 应返回 False"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionPersistenceManager(storage_path=Path(tmpdir))
            result = mgr.delete_session("nonexistent_session")
            assert result is False, \
                "Should return False for nonexistent session"

    def test_delete_session_partial_cleanup(self):
        """session 文件 + result 文件 + 旧版目录的部分清理场景"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mgr = SessionPersistenceManager(storage_path=tmp_path)

            session_id = "partial_cleanup"
            # 只有 session 文件
            session_file = mgr.sessions_dir / f"{session_id}.json"
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text('{"data": true}')

            # 保留 result 文件不存在（部分场景）
            result = mgr.delete_session(session_id)
            assert result is True, \
                "Should return True even when only session file exists"
            assert not session_file.exists(), \
                "Session file should still be removed"

    def test_delete_session_only_result_file(self):
        """只有 result 文件时也应清理"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mgr = SessionPersistenceManager(storage_path=tmp_path)

            session_id = "result_only"
            result_file = mgr.results_dir / f"{session_id}_result.json"
            result_file.parent.mkdir(parents=True, exist_ok=True)
            result_file.write_text('{"result": true}')

            result = mgr.delete_session(session_id)
            assert result is True
            assert not result_file.exists()

    def test_sessions_dir_path_correct(self):
        """sessions_dir 应为 storage_path / sessions / agents"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.core.agents.session_persistence import SessionPersistenceManager
            mgr = SessionPersistenceManager(storage_path=Path(tmpdir))
            expected = Path(tmpdir) / "sessions" / "agents"
            assert mgr.sessions_dir == expected, \
                f"sessions_dir should be {expected}, got {mgr.sessions_dir}"


class TestClearRegistryPersistenceCleanup:
    """验证 factory.clear_registry 调用 persistence delete"""

    def _make_factory(self, with_persistence=True):
        """创建带可选 persistence 的 factory"""
        from src.core.agents.factory import DynamicAgentFactory

        factory = DynamicAgentFactory.__new__(DynamicAgentFactory)
        factory._agents = {}
        factory._session_registries = {}
        factory._skill_registry = MagicMock()
        factory._created_count = 0

        if with_persistence:
            factory._persistence = MagicMock()
            factory._persistence.delete_session = MagicMock(return_value=True)
        else:
            factory._persistence = None

        return factory

    def test_clear_registry_calls_persistence_delete(self):
        """clear_registry 在清理内存后应调用 persistence.delete_session"""
        factory = self._make_factory(with_persistence=True)

        from src.core.agents.agent_session import AgentSessionRegistry
        parent_id = "test_parent_001"

        registry = AgentSessionRegistry(parent_session_id=parent_id)
        factory._session_registries[parent_id] = registry

        # 模拟 agent 带 _session
        agent = MagicMock()
        session = MagicMock()
        session.parent_session_id = parent_id
        session.session_id = "agent_session_001"
        agent._session = session
        agent.agent_id = "agent_001"
        factory._agents["agent_001"] = agent

        factory.clear_registry(parent_id)

        # 验证 delete_session 被调用（使用 session_id，而非 agent_id）
        factory._persistence.delete_session.assert_called()
        args = factory._persistence.delete_session.call_args
        assert args is not None

    def test_clear_registry_passes_session_id(self):
        """clear_registry 应将 session_id 传给 delete_session"""
        factory = self._make_factory(with_persistence=True)

        from src.core.agents.agent_session import AgentSessionRegistry
        parent_id = "test_parent_002"

        registry = AgentSessionRegistry(parent_session_id=parent_id)
        factory._session_registries[parent_id] = registry

        agent = MagicMock()
        session = MagicMock()
        session.parent_session_id = parent_id
        session.session_id = "correct_session_id"
        agent._session = session
        agent.agent_id = "agent_002"
        factory._agents["agent_002"] = agent

        factory.clear_registry(parent_id)

        # 应使用 session.session_id 而非 agent_id
        call_args = factory._persistence.delete_session.call_args
        assert call_args[0][0] == "correct_session_id", \
            f"Expected 'correct_session_id', got {call_args[0][0]}"

    def test_clear_registry_no_persistence_skip(self):
        """无 persistence 时 clear_registry 不应报错"""
        factory = self._make_factory(with_persistence=False)

        from src.core.agents.agent_session import AgentSessionRegistry
        parent_id = "test_parent_003"
        registry = AgentSessionRegistry(parent_session_id=parent_id)
        factory._session_registries[parent_id] = registry

        result = factory.clear_registry(parent_id)
        assert result is True

    def test_persistence_has_delete_session_method(self):
        """验证 SessionPersistenceManager 有 delete 接口"""
        from src.core.agents.session_persistence import SessionPersistenceManager

        assert hasattr(SessionPersistenceManager, "delete_session"), \
            "SessionPersistenceManager must have delete_session"
        assert hasattr(SessionPersistenceManager, "cleanup_completed_session"), \
            "Existing cleanup method must be preserved"


if __name__ == "__main__":
    pytest.main([__file__])
