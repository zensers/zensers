"""
后台执行器

参考: oh-my-openagent BackgroundManager

特性：
- 后台任务启动
- 异步结果通知
- 任务追踪
- 超时控制
- 取消支持

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable

logger = logging.getLogger(__name__)


class BackgroundTaskStatus(Enum):
    """后台任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class BackgroundTask:
    """
    后台任务
    
    Attributes:
        id: 任务ID
        execute_func: 执行函数
        parent_session_id: 父Session ID
        status: 任务状态
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
        result: 执行结果
        error: 错误信息
        timeout: 超时时间
    """
    id: str
    execute_func: Callable[[], Awaitable[Dict[str, Any]]]
    parent_session_id: str
    status: BackgroundTaskStatus = BackgroundTaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timeout: Optional[float] = None
    
    # 内部状态
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _completion_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


@dataclass
class BackgroundExecutorConfig:
    """后台执行器配置"""
    max_concurrent_tasks: int = 10       # 最大并发任务数
    default_timeout: float = 300.0       # 默认超时时间
    cleanup_interval: float = 60.0       # 清理间隔
    task_ttl: float = 3600.0             # 已完成任务保留时间


class BackgroundExecutor:
    """
    后台执行器
    
    参考: oh-my-openagent BackgroundManager
    
    特性：
    - 后台任务启动
    - 异步结果通知
    - 任务追踪
    - 超时控制
    - 取消支持
    
    使用示例:
        executor = BackgroundExecutor(BackgroundExecutorConfig())
        
        # 启动后台任务
        task_id = await executor.launch(
            execute_func=lambda: agent.execute(task),
            parent_session_id="research_001"
        )
        
        # 等待结果
        result = await executor.wait_for_result(task_id, timeout=60.0)
        
        # 或者检查状态
        status = executor.get_task_status(task_id)
    """
    
    def __init__(self, config: BackgroundExecutorConfig):
        self.config = config
        
        # 任务存储
        self._tasks: Dict[str, BackgroundTask] = {}
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(config.max_concurrent_tasks)
        
        # 锁保护内部状态
        self._lock = asyncio.Lock()
        
        # 自动清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 统计信息
        self._total_launched = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._total_timeout = 0
    
    async def start(self) -> None:
        """启动后台执行器和自动清理"""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("BackgroundExecutor started with auto-cleanup")
    
    async def _cleanup_loop(self) -> None:
        """自动清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                cleaned = self.cleanup_completed()
                if cleaned > 0:
                    logger.debug(f"Auto-cleaned {cleaned} completed tasks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(10.0)  # 出错后等待一段时间再重试
    
    async def launch(
        self,
        execute_func: Callable[[], Awaitable[Dict[str, Any]]],
        parent_session_id: str,
        timeout: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        启动后台任务
        
        Args:
            execute_func: 异步执行函数
            parent_session_id: 父Session ID
            timeout: 超时时间（秒），None使用默认值
            task_id: 自定义任务ID，None自动生成
            
        Returns:
            任务ID
        """
        # 生成任务ID
        task_id = task_id or f"bg_{uuid.uuid4().hex[:8]}"
        
        # 创建任务对象
        bg_task = BackgroundTask(
            id=task_id,
            execute_func=execute_func,
            parent_session_id=parent_session_id,
            timeout=timeout or self.config.default_timeout,
        )
        
        # 注册任务
        async with self._lock:
            self._tasks[task_id] = bg_task
            self._total_launched += 1
        
        # 启动执行
        bg_task._task = asyncio.create_task(
            self._run_task(bg_task)
        )
        
        logger.debug(f"Launched background task {task_id}")
        return task_id
    
    async def _run_task(self, bg_task: BackgroundTask) -> None:
        """
        运行后台任务
        
        Args:
            bg_task: 后台任务对象
        """
        try:
            # 等待获取执行槽位
            async with self._semaphore:
                # 更新状态
                bg_task.status = BackgroundTaskStatus.RUNNING
                bg_task.started_at = datetime.now()
                
                logger.debug(f"Background task {bg_task.id} started")
                
                try:
                    # 带超时执行
                    if bg_task.timeout:
                        result = await asyncio.wait_for(
                            bg_task.execute_func(),
                            timeout=bg_task.timeout
                        )
                    else:
                        result = await bg_task.execute_func()
                    
                    # 成功完成
                    bg_task.status = BackgroundTaskStatus.COMPLETED
                    bg_task.result = result
                    self._total_completed += 1
                    
                    logger.debug(f"Background task {bg_task.id} completed")
                    
                except asyncio.TimeoutError:
                    # 超时
                    bg_task.status = BackgroundTaskStatus.TIMEOUT
                    bg_task.error = f"Timeout after {bg_task.timeout}s"
                    self._total_timeout += 1
                    
                    logger.warning(f"Background task {bg_task.id} timed out")
                    
                except asyncio.CancelledError:
                    # 取消
                    bg_task.status = BackgroundTaskStatus.CANCELLED
                    bg_task.error = "Task cancelled"
                    self._total_cancelled += 1
                    
                    logger.info(f"Background task {bg_task.id} cancelled")
                    raise
                    
                except Exception as e:
                    # 失败
                    bg_task.status = BackgroundTaskStatus.FAILED
                    bg_task.error = str(e)
                    self._total_failed += 1
                    
                    logger.error(f"Background task {bg_task.id} failed: {e}")
                    
        finally:
            # 记录完成时间
            bg_task.completed_at = datetime.now()
            
            # 触发完成事件
            bg_task._completion_event.set()
    
    async def wait_for_result(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        等待后台任务结果
        
        Args:
            task_id: 任务ID
            timeout: 等待超时时间
            
        Returns:
            任务结果，不存在或超时返回None
        """
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            logger.warning(f"Task {task_id} not found")
            return None
        
        # 等待完成
        try:
            if timeout:
                await asyncio.wait_for(
                    bg_task._completion_event.wait(),
                    timeout=timeout
                )
            else:
                await bg_task._completion_event.wait()
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for task {task_id}")
            return None
        
        # 返回结果
        return bg_task.result
    
    async def wait_for_all(
        self,
        task_ids: List[str],
        timeout: Optional[float] = None
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        等待所有任务完成
        
        Args:
            task_ids: 任务ID列表
            timeout: 总超时时间
            
        Returns:
            任务ID -> 结果的映射
        """
        async def wait_one(tid: str) -> tuple[str, Optional[Dict[str, Any]]]:
            result = await self.wait_for_result(tid, timeout=timeout)
            return (tid, result)
        
        tasks = [asyncio.create_task(wait_one(tid)) for tid in task_ids]
        
        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
            
            # 收集结果
            results = {}
            for task in done:
                tid, result = task.result()
                results[tid] = result
            
            # 标记超时的任务
            for tid in task_ids:
                if tid not in results:
                    results[tid] = None
            
            return results
            
        except Exception as e:
            logger.error(f"Error waiting for tasks: {e}")
            return {tid: None for tid in task_ids}
    
    def get_task_status(self, task_id: str) -> Optional[BackgroundTaskStatus]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态，不存在返回None
        """
        bg_task = self._tasks.get(task_id)
        return bg_task.status if bg_task else None
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """
        获取任务对象
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，不存在返回None
        """
        return self._tasks.get(task_id)
    
    def is_completed(self, task_id: str) -> bool:
        """
        检查任务是否完成
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否完成（包括成功、失败、取消、超时）
        """
        status = self.get_task_status(task_id)
        return status in (
            BackgroundTaskStatus.COMPLETED,
            BackgroundTaskStatus.FAILED,
            BackgroundTaskStatus.CANCELLED,
            BackgroundTaskStatus.TIMEOUT,
        )
    
    async def cancel(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return False
        
        if bg_task._task and not bg_task._task.done():
            bg_task._task.cancel()
            
            # 等待任务结束
            try:
                await bg_task._task
            except asyncio.CancelledError:
                pass
            
            return True
        
        return False
    
    async def cancel_all(self) -> int:
        """
        取消所有运行中的任务
        
        Returns:
            取消的任务数量
        """
        cancelled = 0
        
        for task_id, bg_task in list(self._tasks.items()):
            if bg_task._task and not bg_task._task.done():
                bg_task._task.cancel()
                cancelled += 1
        
        return cancelled
    
    def get_running_tasks(self) -> List[str]:
        """获取所有运行中的任务ID"""
        return [
            tid for tid, task in self._tasks.items()
            if task.status == BackgroundTaskStatus.RUNNING
        ]
    
    def get_pending_tasks(self) -> List[str]:
        """获取所有待执行的任务ID"""
        return [
            tid for tid, task in self._tasks.items()
            if task.status == BackgroundTaskStatus.PENDING
        ]
    
    def get_completed_tasks(self) -> List[str]:
        """获取所有已完成的任务ID"""
        return [
            tid for tid, task in self._tasks.items()
            if task.status == BackgroundTaskStatus.COMPLETED
        ]
    
    def get_failed_tasks(self) -> List[str]:
        """获取所有失败的任务ID"""
        return [
            tid for tid, task in self._tasks.items()
            if task.status in (
                BackgroundTaskStatus.FAILED,
                BackgroundTaskStatus.TIMEOUT,
                BackgroundTaskStatus.CANCELLED,
            )
        ]
    
    def cleanup_completed(self, max_age_seconds: Optional[float] = None) -> int:
        """
        清理已完成的任务
        
        Args:
            max_age_seconds: 最大保留时间，None使用配置值
            
        Returns:
            清理的任务数量
        """
        max_age = max_age_seconds or self.config.task_ttl
        now = datetime.now()
        
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.completed_at:
                age = (now - task.completed_at).total_seconds()
                if age > max_age:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._tasks[task_id]
        
        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} completed tasks")
        
        return len(to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_tasks": len(self._tasks),
            "pending": len(self.get_pending_tasks()),
            "running": len(self.get_running_tasks()),
            "completed": len(self.get_completed_tasks()),
            "failed": len(self.get_failed_tasks()),
            "total_launched": self._total_launched,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_cancelled": self._total_cancelled,
            "total_timeout": self._total_timeout,
        }
    
    async def shutdown(self, timeout: float = 10.0) -> None:
        """
        关闭执行器
        
        Args:
            timeout: 等待任务完成的超时时间
        """
        logger.info("Shutting down background executor")
        
        # 停止清理循环
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        # 取消所有运行中的任务
        await self.cancel_all()
        
        # 等待所有任务完成
        running = self.get_running_tasks()
        if running:
            try:
                await asyncio.wait_for(
                    self.wait_for_all(running),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for {len(running)} tasks to complete")
        
        # 清理
        self._tasks.clear()
        
        logger.info("Background executor shutdown complete")
