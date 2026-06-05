import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestCoordinatorNoRetry:
    """Coordinator 不重试：timeout/exception 直接返回 failure"""

    @pytest.fixture
    def coordinator(self):
        from src.core.orchestrator.execution.coordinator.agent_coordinator import (
            AgentCoordinator, CoordinatorConfig
        )
        c = AgentCoordinator.__new__(AgentCoordinator)
        c.config = CoordinatorConfig(max_retries=1, default_timeout=30)
        c.message_bus = MagicMock()
        c.shared_memory = MagicMock()
        c._session_registry = MagicMock()
        c.session_registry = c._session_registry
        c.progress_tracker = MagicMock()
        c._total_completed = 0
        c._total_failed = 0
        c._total_cancelled = 0
        c.heartbeat_monitor = MagicMock()
        return c

    @pytest.fixture
    def active_task(self):
        from src.core.orchestrator.execution.coordinator.agent_coordinator import ActiveTask
        task = ActiveTask.__new__(ActiveTask)
        task.task_id = "test_task_001"
        task.agent = MagicMock()
        task.agent.agent_id = "test_agent_001"
        task.agent._context = {"last_output": "partial content before timeout"}
        task.agent.run = AsyncMock()
        task.options = MagicMock()
        task.options.max_retries = 1
        task.options.timeout = 30
        task.retry_count = 0
        task.status = "pending"
        task.result = None
        task.error = None
        task.started_at = None
        task.completed_at = None
        return task

    @pytest.mark.asyncio
    async def test_timeout_returns_failure_immediately(self, coordinator, active_task):
        active_task.agent.run.side_effect = asyncio.TimeoutError()
        task = {"topic": "test"}
        await coordinator._execute_with_monitoring(active_task, task)
        assert active_task.status == "failed"
        assert "Timeout" in active_task.error
        assert hasattr(active_task, "failure_type")
        assert active_task.failure_type == "timeout"
        assert active_task.retry_count == 0

    @pytest.mark.asyncio
    async def test_exception_returns_failure_immediately(self, coordinator, active_task):
        active_task.agent.run.side_effect = ValueError("test error")
        task = {"topic": "test"}
        await coordinator._execute_with_monitoring(active_task, task)
        assert active_task.status == "failed"
        assert "test error" in active_task.error
        assert active_task.failure_type == "exception"
        assert active_task.retry_count == 0

    @pytest.mark.asyncio
    async def test_partial_output_captured_on_failure(self, coordinator, active_task):
        active_task.agent.run.side_effect = asyncio.TimeoutError()
        active_task.agent._context["last_output"] = "partial content before timeout"
        task = {"topic": "test"}
        await coordinator._execute_with_monitoring(active_task, task)
        assert active_task.partial_output == "partial content before timeout"

    @pytest.mark.asyncio
    async def test_success_path_unaffected(self, coordinator, active_task):
        active_task.agent.run.return_value = {
            "success": True, "content": "good content", "agent_id": "test_agent_001"
        }
        task = {"topic": "test"}
        await coordinator._execute_with_monitoring(active_task, task)
        assert active_task.status == "completed"
        assert active_task.retry_count == 0


class TestEngineIdentifyFailedAgents:
    """Engine 区分 infra 和 quality 失败"""

    def _make_engine(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        e = ExecutionEngine.__new__(ExecutionEngine)
        e.config = MagicMock()
        e.config.max_retries = 3
        e.message_bus = MagicMock()
        e._shared_memory = MagicMock()
        e._coordinator = MagicMock()
        return e

    def test_identify_infra_failure(self):
        engine = self._make_engine()
        batch_results = [
            {"success": False, "agent_id": "agent_1", "error": "Timeout", "failure_type": "timeout"},
            {"success": True, "agent_id": "agent_2", "content": "good"},
        ]
        mock_agents = [MagicMock(), MagicMock()]
        mock_agents[0].agent_id = "agent_1"
        mock_agents[1].agent_id = "agent_2"
        failed = engine._identify_failed_agents(batch_results, MagicMock(), mock_agents)
        assert len(failed) == 1
        assert failed[0]["type"] == "infrastructure"
        assert failed[0]["reason"] == "timeout"

    def test_identify_quality_failure(self):
        from src.core.quality.checkers import QualityResult
        engine = self._make_engine()
        mock_checker = MagicMock()
        mock_checker.check.return_value = QualityResult(
            checker_type="test", score=30.0, threshold=50.0, passed=False,
            issues=["数据不足", "缺少分析"],
        )
        batch_results = [
            {"success": True, "agent_id": "agent_1", "content": "weak content"},
        ]
        mock_agents = [MagicMock()]
        mock_agents[0].agent_id = "agent_1"
        failed = engine._identify_failed_agents(batch_results, mock_checker, mock_agents)
        assert len(failed) == 1
        assert failed[0]["type"] == "quality"
        assert failed[0]["score"] == 30.0

    def test_mixed_failures_both_detected(self):
        from src.core.quality.checkers import QualityResult
        engine = self._make_engine()
        mock_checker = MagicMock()
        # First call (agent_2) -> fail, second call (agent_3) -> pass
        mock_checker.check.side_effect = [
            QualityResult(
                checker_type="test", score=20.0, threshold=50.0, passed=False,
                issues=["质量不足"],
            ),
            QualityResult(
                checker_type="test", score=80.0, threshold=50.0, passed=True,
                issues=[],
            ),
        ]
        batch_results = [
            {"success": False, "agent_id": "agent_1", "error": "Timeout", "failure_type": "timeout"},
            {"success": True, "agent_id": "agent_2", "content": "weak"},
            {"success": True, "agent_id": "agent_3", "content": "good quality content"},
        ]
        mock_agents = [MagicMock(), MagicMock(), MagicMock()]
        for i, aid in enumerate(["agent_1", "agent_2", "agent_3"]):
            mock_agents[i].agent_id = aid
        failed = engine._identify_failed_agents(batch_results, mock_checker, mock_agents)
        assert len(failed) == 2
        failed_ids = [f["agent"].agent_id for f in failed]
        assert "agent_1" in failed_ids
        assert "agent_2" in failed_ids
        assert "agent_3" not in failed_ids


class TestEngineInjectFeedback:
    """Engine 根据失败类型注入正确的 feedback"""

    def test_infra_feedback_injects_retry_reason(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        e = ExecutionEngine.__new__(ExecutionEngine)
        mock_agent = MagicMock()
        mock_agent._context = {}
        e._inject_retry_feedback([{
            "type": "infrastructure",
            "reason": "timeout",
            "error": "Timeout after 30s",
            "agent": mock_agent,
        }], retry_count=1)
        assert mock_agent._context["retry_attempt"] == 1
        assert mock_agent._context["retry_reason"] == "timeout"
        assert mock_agent._context["previous_error"] == "Timeout after 30s"
        assert mock_agent._context["quality_feedback"]["score"] == 0

    def test_quality_feedback_injects_score_and_issues(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        e = ExecutionEngine.__new__(ExecutionEngine)
        mock_agent = MagicMock()
        mock_agent._context = {}
        e._inject_retry_feedback([{
            "type": "quality",
            "score": 35.0,
            "issues": ["数据不足", "缺少分析"],
            "agent": mock_agent,
        }], retry_count=1)
        assert mock_agent._context["retry_attempt"] == 1
        assert mock_agent._context["quality_feedback"]["score"] == 35.0
        assert len(mock_agent._context["quality_feedback"]["issues"]) == 2


class TestEngineMergeResults:
    """重试结果替换原始 batch 中对应位置"""

    def test_merge_retry_results_replaces_matching_agent(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        e = ExecutionEngine.__new__(ExecutionEngine)
        batch_results = [
            {"agent_id": "agent_1", "success": True, "content": "original"},
            {"agent_id": "agent_2", "success": False, "error": "failed"},
            {"agent_id": "agent_3", "success": True, "content": "good"},
        ]
        retry_results = [
            {"agent_id": "agent_2", "success": True, "content": "retried content"},
        ]
        merged = e._merge_retry_results(batch_results, retry_results)
        assert len(merged) == 3
        assert merged[1]["content"] == "retried content"
        assert merged[0]["content"] == "original"
        assert merged[2]["success"] is True

    def test_merge_preserves_unaffected_results(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        e = ExecutionEngine.__new__(ExecutionEngine)
        batch_results = [
            {"agent_id": "agent_1", "success": True},
            {"agent_id": "agent_2", "success": True},
        ]
        retry_results = []
        merged = e._merge_retry_results(batch_results, retry_results)
        assert merged == batch_results
