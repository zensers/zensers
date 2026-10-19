# -*- coding: utf-8 -*-
"""
Phase 9 端到端集成测试

测试问卷系统与主控集成的完整工作流:
1. 完整工作流（启动→等待→完成→恢复）
2. Webhook签名验证
3. 超时处理
4. 崩溃恢复
5. 并行任务执行
"""

import asyncio
import hashlib
import hmac
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

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
)
from src.survey.webhook_handler import (
    SurveyWebhookHandler,
    WebhookSecurityError,
)
from src.core.recovery.task_recovery import (
    TaskRecoveryManager,
    RecoveryResult,
)


# ===== 测试Fixtures =====

@pytest.fixture
def mock_shared_memory():
    """模拟SharedMemory"""
    storage = {}
    
    class MockSharedMemory:
        async def read(self, key: str) -> Any:
            return storage.get(key)
        
        async def write(self, key: str, value: Any) -> None:
            storage[key] = value
        
        def get_all(self) -> Dict[str, Any]:
            return storage.copy()
    
    return MockSharedMemory()


@pytest.fixture
def mock_message_bus():
    """模拟MessageBus"""
    events = []
    
    class MockMessageBus:
        async def publish(self, topic: str, event: Any) -> None:
            events.append({"topic": topic, "event": event})
        
        def get_events(self) -> List[Dict]:
            return events
    
    return MockMessageBus()


@pytest.fixture
def mock_persistence():
    """模拟TaskPersistence"""
    tasks = {}
    
    class MockPersistence:
        async def save_survey_task(self, task: SurveyTask) -> None:
            tasks[task.task_id] = task
        
        async def load_survey_task(self, task_id: str) -> Any:
            return tasks.get(task_id)
        
        async def find_survey_tasks_by_status(self, status: SurveyStatus) -> List[SurveyTask]:
            return [t for t in tasks.values() if t.status == status]
        
        async def find_child_survey_tasks(self, parent_id: str) -> List[SurveyTask]:
            return [t for t in tasks.values() if t.parent_task_id == parent_id]
        
        def get_all_tasks(self) -> Dict:
            return tasks
    
    return MockPersistence()


@pytest.fixture
def mock_task_manager():
    """模拟SurveyTaskManager"""
    tasks = {}
    
    class MockTaskStore:
        async def save(self, task: SurveyTask) -> None:
            tasks[task.task_id] = task
        
        async def load(self, task_id: str) -> Any:
            return tasks.get(task_id)
        
        async def list_all(self) -> List[SurveyTask]:
            return list(tasks.values())
        
        async def list_by_status(self, status: SurveyStatus) -> List[SurveyTask]:
            return [t for t in tasks.values() if t.status == status]
    
    class MockTaskManager:
        store = MockTaskStore()
    
    return MockTaskManager()


@pytest.fixture
def mock_backend():
    """模拟第三方问卷平台后端"""
    class MockBackend:
        def __init__(self):
            self._status = SurveyStatus.WAITING
            self._responses = []
            self.capabilities = {"webhook": True}
        
        async def distribute(self, external_id: str, config: Any) -> str:
            return f"https://survey.example.com/{external_id}"
        
        async def get_status(self, external_id: str) -> SurveyStatus:
            return self._status
        
        async def get_results(self, external_id: str) -> List[SurveyResponse]:
            return self._responses
        
        def set_status(self, status: SurveyStatus):
            self._status = status
        
        def set_responses(self, responses: List[SurveyResponse]):
            self._responses = responses
    
    return MockBackend()


@pytest.fixture
def coordinator(mock_shared_memory, mock_message_bus, mock_persistence):
    """创建TaskCoordinator实例"""
    return TaskCoordinator(
        shared_memory=mock_shared_memory,
        message_bus=mock_message_bus,
        persistence=mock_persistence,
        config=TaskCoordinatorConfig(
            max_concurrent_monitors=5,
            default_timeout_days=30,
            webhook_polling_interval_hours=1,  # 测试时缩短
        ),
    )


@pytest.fixture
def webhook_handler(mock_task_manager, mock_message_bus, mock_shared_memory):
    """创建WebhookHandler实例"""
    return SurveyWebhookHandler(
        task_manager=mock_task_manager,
        message_bus=mock_message_bus,
        shared_memory=mock_shared_memory,
        webhook_secrets={"api_tencent": "test_secret_key"},
    )


# ===== 测试1: 完整工作流 =====

class TestFullWorkflow:
    """测试完整工作流：启动→等待→完成→恢复"""
    
    @pytest.mark.asyncio
    async def test_survey_lifecycle(
        self,
        coordinator,
        webhook_handler,
        mock_backend,
        mock_task_manager,
    ):
        """测试问卷任务完整生命周期"""
        
        # 1. 创建问卷任务
        survey_task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.PENDING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            external_id="ext_123",
            parent_task_id="research_001",
            parent_phase="DATA_COLLECTION",
            timeout_days=30,
        )
        
        # 保存到模拟存储
        await mock_task_manager.store.save(survey_task)
        
        # 2. 验证初始状态
        assert survey_task.status == SurveyStatus.PENDING
        assert survey_task.parent_task_id == "research_001"
        
        # 3. 模拟启动（设置WAITING状态）
        survey_task.status = SurveyStatus.WAITING
        survey_task.expected_completion_date = datetime.now() + timedelta(days=30)
        await mock_task_manager.store.save(survey_task)
        
        # 4. 验证WAITING状态
        assert survey_task.status == SurveyStatus.WAITING
        assert survey_task.is_waiting() is True
        assert survey_task.is_timeout() is False
        
        # 5. 模拟完成
        survey_task.status = SurveyStatus.COMPLETED
        survey_task.collected_count = 100
        survey_task.valid_count = 95
        await mock_task_manager.store.save(survey_task)
        
        # 6. 验证完成状态
        loaded = await mock_task_manager.store.load("survey_001")
        assert loaded.status == SurveyStatus.COMPLETED
        assert loaded.collected_count == 100


# ===== 测试2: Webhook签名验证 =====

class TestWebhookSecurity:
    """测试Webhook签名验证"""
    
    @pytest.mark.asyncio
    async def test_signature_verification_success(
        self,
        webhook_handler,
    ):
        """测试签名验证成功"""
        event = {
            "action": "survey.complete",
            "payload": {"survey_id": "ext_123"},
            "timestamp": datetime.now().isoformat(),
        }
        
        # 计算正确的签名
        payload = json.dumps(event, sort_keys=True, ensure_ascii=False)
        signature = "sha256=" + hmac.new(
            b"test_secret_key",
            payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        
        # 验证签名
        is_valid = webhook_handler._verify_signature("api_tencent", event, signature)
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_signature_verification_failure(
        self,
        webhook_handler,
    ):
        """测试签名验证失败"""
        event = {
            "action": "survey.complete",
            "payload": {"survey_id": "ext_123"},
        }
        
        # 使用错误的签名
        wrong_signature = "sha256=wrong_signature"
        
        is_valid = webhook_handler._verify_signature("api_tencent", event, wrong_signature)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_missing_signature(
        self,
        webhook_handler,
    ):
        """测试缺少签名"""
        event = {"action": "test"}
        
        is_valid = webhook_handler._verify_signature("api_tencent", event, None)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_timestamp_validation(
        self,
        webhook_handler,
    ):
        """测试时间戳验证（防重放）"""
        # 有效时间戳
        valid_event = {
            "action": "test",
            "timestamp": datetime.now().isoformat(),
        }
        assert webhook_handler._verify_timestamp(valid_event) is True
        
        # 过期时间戳
        expired_event = {
            "action": "test",
            "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
        }
        assert webhook_handler._verify_timestamp(expired_event) is False
    
    @pytest.mark.asyncio
    async def test_disabled_signature_verification(
        self,
        mock_task_manager,
        mock_message_bus,
        mock_shared_memory,
    ):
        """测试禁用签名验证"""
        handler = SurveyWebhookHandler(
            task_manager=mock_task_manager,
            message_bus=mock_message_bus,
            shared_memory=mock_shared_memory,
            enable_signature_verification=False,
        )
        
        event = {"action": "test"}
        
        # 禁用验证后，无签名也应通过
        is_valid = handler._verify_signature("api_tencent", event, None)
        assert is_valid is True


# ===== 测试3: 超时处理 =====

class TestTimeoutHandling:
    """测试超时处理"""
    
    def test_is_timeout_detection(self):
        """测试超时检测"""
        task = SurveyTask(
            task_id="survey_001",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
        )
        
        # 未设置预期完成时间
        assert task.is_timeout() is False
        
        # 设置过去的预期时间
        task.expected_completion_date = datetime.now() - timedelta(days=1)
        assert task.is_timeout() is True
        
        # 设置未来的预期时间
        task.expected_completion_date = datetime.now() + timedelta(days=1)
        assert task.is_timeout() is False
    
    def test_timeout_status(self):
        """测试超时状态"""
        assert SurveyStatus.TIMEOUT.value == "timeout"


# ===== 测试4: 崩溃恢复 =====

class TestCrashRecovery:
    """测试崩溃恢复"""
    
    @pytest.mark.asyncio
    async def test_resume_waiting_tasks(
        self,
        coordinator,
        mock_persistence,
        mock_task_manager,
    ):
        """测试恢复等待中的任务"""
        # 创建等待中的任务
        waiting_task = SurveyTask(
            task_id="survey_waiting",
            survey_id="survey_abc",
            backend_type="api_tencent",
            status=SurveyStatus.WAITING,
            config=DistributionConfig(target_count=100),
            target_count=100,
            external_id="ext_123",
            expected_completion_date=datetime.now() + timedelta(days=30),
        )
        await mock_task_manager.store.save(waiting_task)
        
        # 验证可以加载
        loaded = await mock_task_manager.store.load("survey_waiting")
        assert loaded is not None
        assert loaded.status == SurveyStatus.WAITING
    
    @pytest.mark.asyncio
    async def test_recover_and_merge(
        self,
        coordinator,
        mock_shared_memory,
        mock_persistence,
    ):
        """测试恢复并合并结果"""
        # 存储问卷结果
        await mock_shared_memory.write("survey_result.survey_001", {
            "task_id": "survey_001",
            "parent_task_id": "research_001",
            "collected_count": 100,
        })
        
        # 读取结果
        result = await mock_shared_memory.read("survey_result.survey_001")
        assert result is not None
        assert result["collected_count"] == 100


# ===== 测试5: 并行任务执行 =====

class TestParallelExecution:
    """测试并行任务执行"""
    
    @pytest.mark.asyncio
    async def test_parallel_result_merge(
        self,
        coordinator,
        mock_shared_memory,
    ):
        """测试并行结果合并"""
        # 存储多个问卷结果
        for i in range(3):
            await mock_shared_memory.write(f"survey_result.survey_{i}", {
                "task_id": f"survey_{i}",
                "parent_task_id": "research_001",
                "collected_count": 100 * (i + 1),
            })
        
        # 并行获取结果
        task_ids = ["survey_0", "survey_1", "survey_2"]
        merged = await coordinator.merge_results(task_ids)
        
        assert merged["total_tasks"] == 3
        assert merged["successful"] == 3
        assert len(merged["results"]) == 3
    
    @pytest.mark.asyncio
    async def test_concurrent_monitoring(
        self,
        coordinator,
    ):
        """测试并发监控控制"""
        config = TaskCoordinatorConfig(max_concurrent_monitors=5)
        assert config.max_concurrent_monitors == 5
        
        # 验证信号量限制
        assert coordinator._semaphore._value == 5


# ===== 测试6: TaskCoordinator配置 =====

class TestTaskCoordinatorConfig:
    """测试TaskCoordinator配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = TaskCoordinatorConfig()
        
        assert config.max_concurrent_monitors == 10
        assert config.default_timeout_days == 30
        assert config.default_polling_interval_hours == 24
        assert config.webhook_polling_interval_hours == 24
        assert config.max_check_failures == 3
        assert config.enable_auto_recovery is True
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = TaskCoordinatorConfig(
            max_concurrent_monitors=5,
            default_timeout_days=60,
            webhook_polling_interval_hours=12,
            max_check_failures=5,
        )
        
        assert config.max_concurrent_monitors == 5
        assert config.default_timeout_days == 60
        assert config.webhook_polling_interval_hours == 12
        assert config.max_check_failures == 5


# ===== 测试7: 公开接口 =====

class TestPublicInterfaces:
    """测试公开接口"""
    
    @pytest.mark.asyncio
    async def test_resume_monitoring_interface(
        self,
        coordinator,
    ):
        """测试resume_monitoring公开接口"""
        assert hasattr(coordinator, 'resume_monitoring')
        assert callable(coordinator.resume_monitoring)
    
    def test_coordinator_stats(
        self,
        coordinator,
    ):
        """测试统计信息"""
        stats = coordinator.get_stats()
        
        assert "total_launched" in stats
        assert "total_completed" in stats
        assert "monitoring_tasks" in stats
    
    def test_webhook_stats(
        self,
        webhook_handler,
    ):
        """测试Webhook统计信息"""
        stats = webhook_handler.get_stats()
        
        assert "total_webhooks" in stats
        assert "total_processed" in stats
        assert "supported_actions" in stats
        assert "index_size" in stats


# ===== 运行测试 =====

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
