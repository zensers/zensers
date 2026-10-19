# -*- coding: utf-8 -*-
"""
Tests for Phase 9: 问卷系统与主控集成

测试覆盖:
1. SurveyTask 扩展字段
2. TaskCoordinator 核心功能
3. SurveyWebhookHandler 事件处理
4. TaskRecoveryManager 恢复机制
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.survey.models import (
    SurveyTask,
    SurveyStatus,
    DistributionConfig,
    SurveyResponse,
    Answer,
)
from src.core.coordination.task_coordinator import (
    TaskCoordinator,
    TaskCoordinatorConfig,
    MonitorTask,
)
from src.survey.webhook_handler import SurveyWebhookHandler


# ===== SurveyTask 扩展字段测试 =====

class TestSurveyTaskExtensions:
    """SurveyTask 扩展字段测试"""
    
    def test_survey_status_waiting(self):
        """测试 WAITING 状态"""
        assert SurveyStatus.WAITING.value == "waiting"
        assert SurveyStatus.TIMEOUT.value == "timeout"
    
    def test_survey_task_parent_task_id(self):
        """测试 parent_task_id 字段"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            parent_task_id="research_001",
            parent_phase="DATA_COLLECTION",
        )
        
        assert task.parent_task_id == "research_001"
        assert task.parent_phase == "DATA_COLLECTION"
    
    def test_survey_task_timeout_config(self):
        """测试超时配置"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            timeout_days=30,
            timeout_action="notify",
        )
        
        assert task.timeout_days == 30
        assert task.timeout_action == "notify"
    
    def test_survey_task_polling_config(self):
        """测试轮询配置"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            polling_enabled=True,
            polling_interval_hours=12,
        )
        
        assert task.polling_enabled is True
        assert task.polling_interval_hours == 12
    
    def test_survey_task_is_waiting(self):
        """测试 is_waiting 方法"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
        )
        
        assert task.is_waiting() is True
        
        task.status = SurveyStatus.ACTIVE
        assert task.is_waiting() is False
    
    def test_survey_task_is_timeout(self):
        """测试 is_timeout 方法"""
        # 未设置预期完成时间
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
        )
        assert task.is_timeout() is False
        
        # 设置过去的预期完成时间
        task.expected_completion_date = datetime.now() - timedelta(days=1)
        assert task.is_timeout() is True
        
        # 设置未来的预期完成时间
        task.expected_completion_date = datetime.now() + timedelta(days=1)
        assert task.is_timeout() is False
    
    def test_survey_task_calculate_next_polling_time(self):
        """测试计算下次轮询时间"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            polling_interval_hours=24,
        )
        
        next_time = task.calculate_next_polling_time()
        expected = datetime.now() + timedelta(hours=24)
        
        # 允许1分钟误差
        diff = abs((next_time - expected).total_seconds())
        assert diff < 60
    
    def test_survey_task_to_dict_with_new_fields(self):
        """测试序列化包含新字段"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            parent_task_id="research_001",
            parent_phase="DATA_COLLECTION",
            timeout_days=30,
            polling_enabled=True,
            polling_interval_hours=12,
        )
        
        data = task.to_dict()
        
        assert data["parent_task_id"] == "research_001"
        assert data["parent_phase"] == "DATA_COLLECTION"
        assert data["timeout_days"] == 30
        assert data["polling_enabled"] is True
        assert data["polling_interval_hours"] == 12
    
    def test_survey_task_from_dict_with_new_fields(self):
        """测试反序列化包含新字段"""
        data = {
            "task_id": "survey_001",
            "survey_id": "survey_abc",
            "backend_type": "api_tencent",
            "status": "waiting",
            "config": {"target_count": 100, "quota": None, "incentive": None, "deadline": None, "channels": [], "sampling_spec": None},
            "target_count": 100,
            "parent_task_id": "research_001",
            "parent_phase": "DATA_COLLECTION",
            "timeout_days": 30,
            "polling_enabled": True,
            "polling_interval_hours": 12,
            "created_at": datetime.now().isoformat(),
        }
        
        task = SurveyTask.from_dict(data)
        
        assert task.parent_task_id == "research_001"
        assert task.parent_phase == "DATA_COLLECTION"
        assert task.timeout_days == 30
        assert task.polling_enabled is True
        assert task.polling_interval_hours == 12


# ===== TaskCoordinator 测试 =====

class TestTaskCoordinator:
    """TaskCoordinator 测试"""
    
    @pytest.fixture
    def mock_shared_memory(self):
        """模拟 SharedMemory"""
        memory = AsyncMock()
        memory.write = AsyncMock()
        memory.read = AsyncMock(return_value=None)
        return memory
    
    @pytest.fixture
    def mock_message_bus(self):
        """模拟 MessageBus"""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus
    
    @pytest.fixture
    def mock_persistence(self):
        """模拟 Persistence"""
        persistence = AsyncMock()
        persistence.save_survey_task = AsyncMock()
        persistence.find_survey_tasks_by_status = AsyncMock(return_value=[])
        return persistence
    
    @pytest.fixture
    def coordinator(self, mock_shared_memory, mock_message_bus, mock_persistence):
        """创建 TaskCoordinator 实例"""
        return TaskCoordinator(
            shared_memory=mock_shared_memory,
            message_bus=mock_message_bus,
            persistence=mock_persistence,
            config=TaskCoordinatorConfig(),
        )
    
    @pytest.mark.asyncio
    async def test_coordinator_initialization(self, coordinator):
        """测试协调器初始化"""
        assert coordinator._running is False
        assert len(coordinator._monitor_tasks) == 0
        assert coordinator._stats["total_launched"] == 0
    
    @pytest.mark.asyncio
    async def test_coordinator_start(self, coordinator):
        """测试协调器启动"""
        await coordinator.start()
        
        assert coordinator._running is True
        assert coordinator._cleanup_task is not None
        
        # 清理
        await coordinator.shutdown()
    
    @pytest.mark.asyncio
    async def test_coordinator_shutdown(self, coordinator):
        """测试协调器关闭"""
        await coordinator.start()
        await coordinator.shutdown()
        
        assert coordinator._running is False
    
    @pytest.mark.asyncio
    async def test_get_stats(self, coordinator):
        """测试获取统计信息"""
        stats = coordinator.get_stats()
        
        assert "total_launched" in stats
        assert "total_completed" in stats
        assert "monitoring_tasks" in stats
    
    @pytest.mark.asyncio
    async def test_merge_results(self, coordinator, mock_shared_memory):
        """测试合并结果"""
        mock_shared_memory.read = AsyncMock(side_effect=[
            {"task_id": "survey_001", "collected_count": 100},
            {"task_id": "survey_002", "collected_count": 200},
        ])
        
        result = await coordinator.merge_results(["survey_001", "survey_002"])
        
        assert result["total_tasks"] == 2
        assert result["successful"] == 2


# ===== SurveyWebhookHandler 测试 =====

class TestSurveyWebhookHandler:
    """SurveyWebhookHandler 测试"""
    
    @pytest.fixture
    def mock_task_manager(self):
        """模拟 TaskManager"""
        manager = AsyncMock()
        manager.store = AsyncMock()
        manager.store.list_all = AsyncMock(return_value=[])
        manager.store.save = AsyncMock()
        return manager
    
    @pytest.fixture
    def mock_message_bus(self):
        """模拟 MessageBus"""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus
    
    @pytest.fixture
    def mock_shared_memory(self):
        """模拟 SharedMemory"""
        memory = AsyncMock()
        memory.write = AsyncMock()
        return memory
    
    @pytest.fixture
    def handler(self, mock_task_manager, mock_message_bus, mock_shared_memory):
        """创建 WebhookHandler 实例"""
        return SurveyWebhookHandler(
            task_manager=mock_task_manager,
            message_bus=mock_message_bus,
            shared_memory=mock_shared_memory,
        )
    
    @pytest.mark.asyncio
    async def test_handle_unknown_action(self, handler):
        """测试处理未知事件"""
        result = await handler.handle_webhook(
            "api_tencent",
            {"action": "unknown", "payload": {}},
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_handle_answer_create_no_task(self, handler, mock_task_manager):
        """测试处理 answer.create 但找不到任务"""
        mock_task_manager.store.list_all = AsyncMock(return_value=[])
        
        result = await handler.handle_webhook(
            "api_tencent",
            {
                "action": "answer.create",
                "payload": {"survey_id": "external_123"},
            },
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_stats(self, handler):
        """测试获取统计信息"""
        stats = handler.get_stats()
        
        assert "total_webhooks" in stats
        assert "supported_actions" in stats
        assert "answer.create" in stats["supported_actions"]


# ===== TaskRecoveryManager 测试 =====

class TestTaskRecoveryManager:
    """TaskRecoveryManager 测试"""
    
    @pytest.fixture
    def mock_persistence(self):
        """模拟 Persistence"""
        persistence = AsyncMock()
        persistence.load_task = AsyncMock(return_value=None)
        persistence.find_child_survey_tasks = AsyncMock(return_value=[])
        return persistence
    
    @pytest.fixture
    def mock_shared_memory(self):
        """模拟 SharedMemory"""
        memory = AsyncMock()
        memory.read = AsyncMock(return_value=None)
        return memory
    
    @pytest.fixture
    def mock_coordinator(self):
        """模拟 TaskCoordinator"""
        coordinator = AsyncMock()
        coordinator._monitor_survey_task = AsyncMock()
        return coordinator
    
    @pytest.fixture
    def recovery_manager(self, mock_persistence, mock_shared_memory, mock_coordinator):
        """创建 TaskRecoveryManager 实例"""
        from src.core.recovery.task_recovery import TaskRecoveryManager
        return TaskRecoveryManager(
            persistence=mock_persistence,
            shared_memory=mock_shared_memory,
            task_coordinator=mock_coordinator,
        )
    
    @pytest.mark.asyncio
    async def test_recover_task_not_found(self, recovery_manager, mock_persistence):
        """测试恢复不存在的任务"""
        mock_persistence.load_task = AsyncMock(return_value=None)
        
        result = await recovery_manager.recover_and_merge("research_001")
        
        assert result.success is False
        assert "not found" in result.error
    
    @pytest.mark.asyncio
    async def test_get_stats(self, recovery_manager):
        """测试获取统计信息"""
        stats = recovery_manager.get_stats()
        
        assert "total_recoveries" in stats
        assert "successful_recoveries" in stats
        assert "success_rate" in stats


# ===== 集成测试 =====

class TestSurveyIntegration:
    """问卷系统集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建问卷任务
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="ai_simulation",  # 使用AI模拟，不需要外部API
            status=SurveyStatus.PENDING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            parent_task_id="research_001",
            parent_phase="DATA_COLLECTION",
            timeout_days=30,
        )
        
        # 2. 验证任务状态
        assert task.status == SurveyStatus.PENDING
        assert task.parent_task_id == "research_001"
        
        # 3. 模拟启动
        task.status = SurveyStatus.WAITING
        task.expected_completion_date = datetime.now() + timedelta(days=30)
        
        assert task.is_waiting() is True
        assert task.is_timeout() is False
        
        # 4. 模拟完成
        task.status = SurveyStatus.COMPLETED
        task.collected_count = 100
        task.valid_count = 95
        
        assert task.status == SurveyStatus.COMPLETED
        assert task.collected_count == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])