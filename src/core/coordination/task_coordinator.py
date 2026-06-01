# -*- coding: utf-8 -*-
"""
TaskCoordinator - 任务协调器

Phase 9: 问卷系统与主控集成

核心职责:
1. 启动问卷任务（非阻塞）
2. 后台监控长期等待任务
3. 处理完成回调
4. 支持崩溃恢复

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/SURVEY_ORCHESTRATOR_INTEGRATION.md
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from src.survey.models import SurveyTask, SurveyStatus, SurveyResponse
from src.survey.backends.factory import BackendFactory

if TYPE_CHECKING:
    from src.core.communication import SharedMemory, MessageBus
    from src.core.task_persistence import TaskPersistenceManager

logger = logging.getLogger(__name__)


@dataclass
class TaskCoordinatorConfig:
    """TaskCoordinator配置"""
    max_concurrent_monitors: int = 10       # 最大并行监控任务数
    default_timeout_days: int = 30          # 默认超时天数
    default_polling_interval_hours: int = 24  # 默认轮询间隔
    webhook_polling_interval_hours: int = 24  # Webhook模式下的兜底轮询间隔（每天一次）
    cleanup_interval_seconds: float = 300   # 清理间隔（秒）
    task_ttl_seconds: float = 86400 * 60    # 已完成任务保留时间（60天）
    enable_auto_recovery: bool = True       # 启用自动恢复
    max_check_failures: int = 3             # 最大连续检查失败次数


@dataclass
class MonitorTask:
    """后台监控任务"""
    survey_task_id: str
    started_at: datetime
    last_check_at: Optional[datetime] = None
    check_count: int = 0
    check_failures: int = 0  # 连续检查失败次数
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _completion_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _registered: bool = field(default=False, repr=False)  # 是否已注册到_monitor_tasks


class TaskCoordinator:
    """
    任务协调器
    
    核心职责:
    1. 启动问卷任务（非阻塞，立即返回）
    2. 后台监控长期等待任务
    3. 处理问卷完成回调
    4. 支持崩溃恢复
    
    使用示例:
        coordinator = TaskCoordinator(
            shared_memory=shared_memory,
            message_bus=message_bus,
            persistence=persistence,
        )
        
        # 启动问卷任务（非阻塞）
        task_id = await coordinator.launch_survey_task(survey_task)
        
        # 系统恢复时
        results = await coordinator.resume_on_startup()
    """
    
    def __init__(
        self,
        shared_memory: Optional["SharedMemory"],
        message_bus: Optional["MessageBus"],
        persistence: Optional["TaskPersistenceManager"],
        config: Optional[TaskCoordinatorConfig] = None,
    ):
        self._shared_memory = shared_memory
        self._message_bus = message_bus
        self._persistence = persistence
        self._config = config or TaskCoordinatorConfig()
        
        # 监控任务存储
        self._monitor_tasks: Dict[str, MonitorTask] = {}
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_monitors)
        
        # 锁保护内部状态
        self._lock = asyncio.Lock()
        
        # 自动清理
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 统计信息
        self._stats = {
            "total_launched": 0,
            "total_completed": 0,
            "total_timeout": 0,
            "total_failed": 0,
        }
    
    async def start(self) -> None:
        """启动协调器"""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # 自动恢复
        if self._config.enable_auto_recovery:
            await self.resume_on_startup()
        
        logger.info("TaskCoordinator started with auto-recovery enabled")
    
    async def _cleanup_loop(self) -> None:
        """自动清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self._config.cleanup_interval_seconds)
                cleaned = self._cleanup_completed_tasks()
                if cleaned > 0:
                    logger.debug(f"Cleaned up {cleaned} completed monitor tasks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)
    
    # ===== 核心方法 =====
    
    async def launch_survey_task(
        self,
        survey_task: SurveyTask,
        on_completion: Optional[Callable[[SurveyTask, List[SurveyResponse]], Any]] = None,
    ) -> str:
        """
        启动问卷任务（非阻塞）
        
        流程:
        1. 保存任务到持久化存储
        2. 发送问卷到第三方平台
        3. 设置WAITING状态
        4. 创建后台监控任务
        5. 立即返回（不阻塞）
        
        Args:
            survey_task: 问卷任务对象
            on_completion: 完成时的回调函数
            
        Returns:
            survey_task.task_id
        """
        task_id = survey_task.task_id
        
        # 1. 设置预期完成时间
        if not survey_task.expected_completion_date:
            survey_task.expected_completion_date = datetime.now() + timedelta(
                days=survey_task.timeout_days or self._config.default_timeout_days
            )
        
        # 2. 设置轮询配置（不支持Webhook的后端）
        backend = BackendFactory.get_or_create(survey_task.backend_type)
        capabilities = backend.capabilities
        
        if not capabilities.get("webhook", False):
            survey_task.polling_enabled = True
            survey_task.polling_interval_hours = self._config.default_polling_interval_hours
            survey_task.next_polling_at = datetime.now() + timedelta(
                hours=survey_task.polling_interval_hours
            )
        
        # 3. 发送问卷到第三方平台
        try:
            if survey_task.external_id:
                # 已有外部ID，直接发放
                share_url = await backend.distribute(
                    survey_task.external_id,
                    survey_task.config,
                )
            else:
                # 需要先创建问卷（某些平台不支持API创建）
                # 这里简化处理，假设外部ID已存在
                share_url = await backend.distribute(
                    survey_task.external_id,
                    survey_task.config,
                )
            
            survey_task.share_url = share_url
            survey_task.started_at = datetime.now()
            
        except Exception as e:
            logger.error(f"Failed to distribute survey {task_id}: {e}")
            survey_task.status = SurveyStatus.FAILED
            survey_task.error_message = str(e)
            await self._save_task(survey_task)
            raise
        
        # 4. 设置WAITING状态并保存
        survey_task.status = SurveyStatus.WAITING
        await self._save_task(survey_task)
        
        # 5. 创建后台监控任务（先注册，再启动asyncio task，避免竞态条件）
        monitor = MonitorTask(
            survey_task_id=task_id,
            started_at=datetime.now(),
        )
        
        # 先注册到_monitor_tasks（必须在启动前注册，避免_monitor_survey_task找不到）
        async with self._lock:
            self._monitor_tasks[task_id] = monitor
            self._stats["total_launched"] += 1
            monitor._registered = True
        
        # 然后启动后台监控（此时monitor已注册）
        monitor._asyncio_task = asyncio.create_task(
            self._monitor_survey_task(survey_task, on_completion)
        )
        
        logger.info(f"Launched survey task {task_id} (status=WAITING, backend={survey_task.backend_type})")
        
        return task_id
    
    async def _monitor_survey_task(
        self,
        survey_task: SurveyTask,
        on_completion: Optional[Callable[[SurveyTask, List[SurveyResponse]], Any]] = None,
    ) -> None:
        """
        后台监控问卷任务
        
        支持:
        - Webhook回调（实时）
        - 定时轮询（兜底）
        - 超时检测
        """
        task_id = survey_task.task_id
        monitor = self._monitor_tasks.get(task_id)
        
        if not monitor:
            return
        
        try:
            async with self._semaphore:
                backend = BackendFactory.get_or_create(survey_task.backend_type)
                
                while self._running:
                    # 更新检查时间
                    monitor.last_check_at = datetime.now()
                    monitor.check_count += 1
                    
                    # 1. 检查超时
                    if survey_task.is_timeout():
                        await self._handle_timeout(survey_task)
                        break
                    
                    # 2. 检查第三方平台状态
                    try:
                        status = await backend.get_status(survey_task.external_id)
                        survey_task.status = status
                        
                        if status == SurveyStatus.COMPLETED:
                            # 任务完成，获取结果
                            responses = await backend.get_results(survey_task.external_id)
                            await self._handle_completion(
                                survey_task, responses, on_completion
                            )
                            break
                        
                        elif status == SurveyStatus.FAILED:
                            # 任务失败
                            survey_task.error_message = "Backend reported failure"
                            await self._handle_failure(survey_task)
                            break
                        
                        elif status in (SurveyStatus.ACTIVE, SurveyStatus.WAITING):
                            # 继续等待
                            logger.debug(
                                f"Survey {task_id} still waiting "
                                f"(check #{monitor.check_count})"
                            )
                            
                    except Exception as e:
                        logger.warning(f"Error checking survey {task_id} status: {e}")
                        # 增加失败计数
                        monitor.check_failures += 1
                        
                        # 检查是否超过最大失败次数
                        if monitor.check_failures >= self._config.max_check_failures:
                            logger.error(
                                f"Survey {task_id} exceeded max check failures "
                                f"({monitor.check_failures}), marking as failed"
                            )
                            survey_task.error_message = f"Max check failures ({monitor.check_failures})"
                            await self._handle_failure(survey_task)
                            break
                        # 继续等待，不中断监控
                    
                    # 3. 等待下次检查
                    if survey_task.polling_enabled:
                        wait_seconds = survey_task.polling_interval_hours * 3600
                    else:
                        # Webhook模式，大幅减少轮询频率（每天一次作为兜底）
                        wait_seconds = self._config.webhook_polling_interval_hours * 3600
                    
                    await asyncio.sleep(wait_seconds)
                    
        except asyncio.CancelledError:
            logger.info(f"Monitor for survey {task_id} cancelled")
            
        except Exception as e:
            logger.error(f"Monitor for survey {task_id} failed: {e}")
            await self._handle_failure(survey_task)
        
        finally:
            monitor._completion_event.set()
    
    async def _handle_completion(
        self,
        survey_task: SurveyTask,
        responses: List[SurveyResponse],
        on_completion: Optional[Callable[[SurveyTask, List[SurveyResponse]], Any]] = None,
    ) -> None:
        """
        处理问卷完成
        
        流程:
        1. 更新任务状态
        2. 存储结果到SharedMemory
        3. 发布完成事件到MessageBus
        4. 执行回调函数
        """
        task_id = survey_task.task_id
        
        # 1. 更新任务状态
        survey_task.status = SurveyStatus.COMPLETED
        survey_task.completed_at = datetime.now()
        survey_task.collected_count = len(responses)
        survey_task.valid_count = sum(1 for r in responses if r.is_valid)
        
        await self._save_task(survey_task)
        
        # 2. 存储结果到SharedMemory（带异常处理和降级）
        result_key = f"survey_result.{task_id}"
        result_data = {
            "task_id": task_id,
            "parent_task_id": survey_task.parent_task_id,
            "parent_phase": survey_task.parent_phase,
            "collected_count": len(responses),
            "valid_count": survey_task.valid_count,
            "completed_at": survey_task.completed_at.isoformat(),
            "responses": [r.to_dict() for r in responses[:100]],  # 最多存储100条
            "total_responses": len(responses),
        }
        
        if self._shared_memory:
            try:
                await self._shared_memory.write(result_key, result_data)
            except Exception as e:
                logger.error(f"Failed to store survey result to SharedMemory: {e}")
                # 降级：尝试保存到文件
                if survey_task.result_storage_path:
                    try:
                        import aiofiles
                        async with aiofiles.open(survey_task.result_storage_path, 'w', encoding='utf-8') as f:
                            await f.write(json.dumps(result_data, ensure_ascii=False, indent=2))
                        logger.info(f"Survey result saved to file: {survey_task.result_storage_path}")
                    except ImportError:
                        # aiofiles未安装，使用同步写入
                        import builtins
                        with builtins.open(survey_task.result_storage_path, 'w', encoding='utf-8') as f:
                            f.write(json.dumps(result_data, ensure_ascii=False, indent=2))
                        logger.info(f"Survey result saved to file (sync): {survey_task.result_storage_path}")
                    except Exception as file_e:
                        logger.error(f"Failed to save survey result to file: {file_e}")
        
        # 3. 发布完成事件到MessageBus
        if self._message_bus and survey_task.callback_topic:
            from src.core.communication import Event
            
            await self._message_bus.publish(
                survey_task.callback_topic,
                Event(
                    type="survey.completed",
                    data={
                        "task_id": task_id,
                        "parent_task_id": survey_task.parent_task_id,
                        "collected_count": len(responses),
                        "valid_count": survey_task.valid_count,
                    },
                    source="TaskCoordinator",
                )
            )
        
        # 4. 更新统计
        async with self._lock:
            self._stats["total_completed"] += 1
        
        # 5. 执行回调
        if on_completion:
            try:
                await on_completion(survey_task, responses)
            except Exception as e:
                logger.error(f"Completion callback failed for {task_id}: {e}")
        
        logger.info(
            f"Survey task {task_id} completed "
            f"(collected={len(responses)}, valid={survey_task.valid_count})"
        )
    
    async def _handle_timeout(self, survey_task: SurveyTask) -> None:
        """处理超时"""
        task_id = survey_task.task_id
        
        survey_task.status = SurveyStatus.TIMEOUT
        survey_task.completed_at = datetime.now()
        survey_task.error_message = f"Timeout after {survey_task.timeout_days} days"
        
        await self._save_task(survey_task)
        
        # 更新统计
        async with self._lock:
            self._stats["total_timeout"] += 1
        
        # 发布超时事件
        if self._message_bus and survey_task.callback_topic:
            from src.core.communication import Event
            
            await self._message_bus.publish(
                survey_task.callback_topic,
                Event(
                    type="survey.timeout",
                    data={
                        "task_id": task_id,
                        "parent_task_id": survey_task.parent_task_id,
                        "timeout_days": survey_task.timeout_days,
                    },
                    source="TaskCoordinator",
                )
            )
        
        logger.warning(f"Survey task {task_id} timed out after {survey_task.timeout_days} days")
    
    async def _handle_failure(self, survey_task: SurveyTask) -> None:
        """处理失败"""
        task_id = survey_task.task_id
        
        survey_task.status = SurveyStatus.FAILED
        survey_task.completed_at = datetime.now()
        
        await self._save_task(survey_task)
        
        # 更新统计
        async with self._lock:
            self._stats["total_failed"] += 1
        
        logger.error(f"Survey task {task_id} failed: {survey_task.error_message}")
    
    async def _save_task(self, survey_task: SurveyTask) -> None:
        """保存任务到持久化存储"""
        if self._persistence:
            # 使用统一的持久化接口
            await self._persistence.save_survey_task(survey_task)
        else:
            # 直接使用SurveyTaskManager
            from src.survey.task_manager import get_task_manager
            task_manager = get_task_manager()
            await task_manager.store.save(survey_task)
    
    # ===== 恢复机制 =====
    
    async def resume_monitoring(
        self,
        survey_task: SurveyTask,
        on_completion: Optional[Callable[[SurveyTask, List[SurveyResponse]], Any]] = None,
    ) -> None:
        """
        恢复监控问卷任务（公开方法）
        
        替代直接调用 _monitor_survey_task 私有方法。
        供 TaskRecoveryManager 等外部组件使用。
        
        Args:
            survey_task: 需要恢复监控的问卷任务
            on_completion: 完成时的回调函数
        """
        task_id = survey_task.task_id
        
        # 避免重复监控
        if task_id in self._monitor_tasks:
            existing = self._monitor_tasks[task_id]
            if existing._asyncio_task and not existing._asyncio_task.done():
                logger.debug(f"Survey {task_id} already being monitored, skipping")
                return
        
        monitor = MonitorTask(
            survey_task_id=task_id,
            started_at=datetime.now(),
        )
        
        # 先注册（必须在启动前）
        monitor._registered = True
        async with self._lock:
            self._monitor_tasks[task_id] = monitor
        
        # 然后启动监控
        monitor._asyncio_task = asyncio.create_task(
            self._monitor_survey_task(survey_task, on_completion)
        )
        
        logger.info(f"Resumed monitoring for survey task {task_id}")
    
    async def resume_on_startup(self) -> Dict[str, Any]:
        """
        系统启动时恢复所有任务
        
        Returns:
        {
            "resumed": [...],      # 成功恢复的监控任务
            "waiting": [...],      # 仍在等待的任务
            "completed": [...],    # 已完成但未处理的任务
            "timeout": [...],      # 已超时的任务
            "failed": [...],       # 恢复失败的任务
        }
        """
        results = {
            "resumed": [],
            "waiting": [],
            "completed": [],
            "timeout": [],
            "failed": [],
        }
        
        # 1. 加载所有WAITING状态的问卷任务
        if self._persistence:
            waiting_tasks = await self._persistence.find_survey_tasks_by_status(
                SurveyStatus.WAITING
            )
        else:
            from src.survey.task_manager import get_task_manager
            task_manager = get_task_manager()
            waiting_tasks = await task_manager.store.list_by_status(SurveyStatus.WAITING)
        
        logger.info(f"Found {len(waiting_tasks)} WAITING survey tasks to recover")
        
        for task in waiting_tasks:
            try:
                # 2. 检查是否已完成
                backend = BackendFactory.get_or_create(task.backend_type)
                status = await backend.get_status(task.external_id)
                
                if status == SurveyStatus.COMPLETED:
                    # 已完成，获取结果
                    responses = await backend.get_results(task.external_id)
                    await self._handle_completion(task, responses)
                    results["completed"].append(task.task_id)
                    
                elif task.is_timeout():
                    # 超时
                    await self._handle_timeout(task)
                    results["timeout"].append(task.task_id)
                    
                elif status == SurveyStatus.FAILED:
                    # 失败
                    await self._handle_failure(task)
                    results["failed"].append(task.task_id)
                    
                else:
                    # 仍在等待，恢复监控（先注册再启动）
                    monitor = MonitorTask(
                        survey_task_id=task.task_id,
                        started_at=datetime.now(),
                    )
                    monitor._registered = True
                    
                    async with self._lock:
                        self._monitor_tasks[task.task_id] = monitor
                    
                    # 注册后再启动
                    monitor._asyncio_task = asyncio.create_task(
                        self._monitor_survey_task(task)
                    )
                    results["waiting"].append(task.task_id)
                    
            except Exception as e:
                logger.error(f"Failed to recover survey task {task.task_id}: {e}")
                results["failed"].append(task.task_id)
        
        logger.info(
            f"Recovery complete: "
            f"completed={len(results['completed'])}, "
            f"waiting={len(results['waiting'])}, "
            f"timeout={len(results['timeout'])}, "
            f"failed={len(results['failed'])}"
        )
        
        return results
    
    # ===== 结果合并 =====
    
    async def merge_results(
        self,
        task_ids: List[str],
    ) -> Dict[str, Any]:
        """
        并行获取和合并多个任务的结果
        
        Args:
            task_ids: 任务ID列表
            
        Returns:
            合并后的结果字典
        """
        async def get_result(task_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
            if self._shared_memory:
                result = await self._shared_memory.read(f"survey_result.{task_id}")
                return (task_id, result)
            else:
                # 从持久化存储加载
                from src.survey.task_manager import get_task_manager
                task_manager = get_task_manager()
                task = await task_manager.store.load(task_id)
                if task and task.status == SurveyStatus.COMPLETED:
                    return (task_id, {
                        "task_id": task_id,
                        "parent_task_id": task.parent_task_id,
                        "collected_count": task.collected_count,
                        "valid_count": task.valid_count,
                    })
                return (task_id, None)
        
        # 并行获取所有结果
        tasks = [asyncio.create_task(get_result(tid)) for tid in task_ids]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        merged = {
            "total_tasks": len(task_ids),
            "successful": 0,
            "failed": 0,
            "results": {},
        }
        
        for result in results_list:
            if isinstance(result, BaseException):
                merged["failed"] += 1
            elif isinstance(result, tuple) and len(result) == 2:
                task_id, data = result  # type: ignore[misc]
                if data:
                    merged["successful"] += 1
                    merged["results"][task_id] = data
                else:
                    merged["failed"] += 1
            else:
                merged["failed"] += 1
        
        return merged
    
    # ===== 状态查询 =====
    
    def get_task_status(self, task_id: str) -> Optional[SurveyStatus]:
        """获取任务状态"""
        monitor = self._monitor_tasks.get(task_id)
        if monitor:
            # 监控中，返回WAITING
            return SurveyStatus.WAITING
        return None
    
    def get_running_tasks(self) -> List[str]:
        """获取所有运行中的监控任务ID"""
        return [
            tid for tid, monitor in self._monitor_tasks.items()
            if monitor._asyncio_task and not monitor._asyncio_task.done()
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "monitoring_tasks": len(self.get_running_tasks()),
            "max_concurrent": self._config.max_concurrent_monitors,
        }
    
    def _cleanup_completed_tasks(self, max_age_seconds: Optional[float] = None) -> int:
        """清理已完成的监控任务"""
        max_age = max_age_seconds or self._config.task_ttl_seconds
        now = datetime.now()
        
        to_remove = []
        for task_id, monitor in self._monitor_tasks.items():
            if monitor._completion_event.is_set():
                age = (now - monitor.started_at).total_seconds()
                if age > max_age:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._monitor_tasks[task_id]
        
        return len(to_remove)
    
    async def shutdown(self) -> None:
        """关闭协调器"""
        logger.info("Shutting down TaskCoordinator")
        
        self._running = False
        
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 取消所有监控任务
        running = self.get_running_tasks()
        for task_id in running:
            monitor = self._monitor_tasks.get(task_id)
            if monitor and monitor._asyncio_task:
                monitor._asyncio_task.cancel()
        
        # 等待所有任务完成
        if running:
            tasks_to_wait: List[asyncio.Task] = []
            for tid in running:
                task = self._monitor_tasks[tid]._asyncio_task
                if task is not None:
                    tasks_to_wait.append(task)
            if tasks_to_wait:
                await asyncio.gather(*tasks_to_wait, return_exceptions=True)
        
        self._monitor_tasks.clear()
        logger.info("TaskCoordinator shutdown complete")


# 全局单例
_coordinator: Optional[TaskCoordinator] = None


def get_coordinator() -> TaskCoordinator:
    """获取全局协调器"""
    global _coordinator
    if _coordinator is None:
        from src.core.communication import SharedMemory, MessageBus
        _coordinator = TaskCoordinator(
            shared_memory=SharedMemory(),
            message_bus=MessageBus(),
            persistence=None,
        )
    return _coordinator