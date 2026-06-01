"""
Agent协调器

核心职责：
- 任务分发
- 进度追踪
- 心跳检测
- 超时处理
- 重试管理
- 取消管理
- 结果收集

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_COORDINATION_DESIGN.md
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .task_dispatcher import TaskDispatcher, TaskOptions, PreparedTask
from .progress_tracker import ProgressTracker, TaskProgress
from .heartbeat_monitor import HeartbeatMonitor, HeartbeatConfig
from .cancel_manager import get_cancel_manager, CancelReason

if TYPE_CHECKING:
    from src.core.agents.base import BaseAgent
    from src.core.agents.protocol import IAgent
    from src.core.agents.agent_session import AgentSessionRegistry, AgentSession, AgentSessionStatus
    from src.core.communication import MessageBus, SharedMemory
    from src.core.agents.result_collector import ResultCollector

# 运行时导入（用于 Session 状态更新）
from src.core.agents.agent_session import AgentSessionStatus

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorConfig:
    """协调器配置"""
    max_concurrent: int = 20             # 最大并发数（增加到20以支持更多Agent并行）
    default_timeout: float = 300.0       # 默认超时
    max_retries: int = 3                 # 最大重试次数
    heartbeat_interval: float = 5.0      # 心跳间隔
    heartbeat_timeout: float = 60.0      # 心跳超时（增加到60秒）
    progress_update_interval: float = 5.0  # 进度更新间隔


@dataclass
class ActiveTask:
    """
    活跃任务
    
    Attributes:
        task_id: 任务ID
        agent: Agent实例
        session: Agent会话
        options: 任务选项
        status: 任务状态
        started_at: 开始时间
        result: 执行结果
        error: 错误信息
        retry_count: 重试次数
    """
    task_id: str
    agent: "IAgent"
    session: Optional["AgentSession"]
    options: TaskOptions
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    
    # 内部状态
    _async_task: Optional[asyncio.Task] = field(default=None, repr=False)


class AgentCoordinator:
    """
    Agent协调器
    
    参考: oh-my-openagent BackgroundManager
    
    核心职责：
    - 任务分发
    - 进度追踪
    - 心跳检测
    - 超时处理
    - 重试管理
    - 取消管理
    - 结果收集
    
    使用示例:
        coordinator = AgentCoordinator(
            message_bus=message_bus,
            shared_memory=shared_memory,
            session_registry=registry,
            config=CoordinatorConfig()
        )
        
        await coordinator.setup()
        
        # 分发任务
        task_id = await coordinator.dispatch_task(
            agent=agent,
            task={"action": "analyze", "data": {...}},
            options=TaskOptions(timeout=60.0)
        )
        
        # 等待完成
        results = await coordinator.wait_for_completion([task_id])
        
        await coordinator.shutdown()
    """
    
    def __init__(
        self,
        message_bus: "MessageBus",
        shared_memory: "SharedMemory",
        session_registry: "AgentSessionRegistry",
        config: Optional[CoordinatorConfig] = None,
    ):
        self.message_bus = message_bus
        self.shared_memory = shared_memory
        self.session_registry = session_registry
        self.config = config or CoordinatorConfig()
        
        # 子组件
        self.task_dispatcher = TaskDispatcher()
        self.progress_tracker = ProgressTracker()
        self.heartbeat_monitor = HeartbeatMonitor(HeartbeatConfig(
            interval_seconds=self.config.heartbeat_interval,
            timeout_seconds=self.config.heartbeat_timeout,
        ))
        self.cancel_manager = get_cancel_manager()
        
        # 活跃任务
        self._active_tasks: Dict[str, ActiveTask] = {}
        
        # 锁
        self._lock = asyncio.Lock()
        
        # 状态
        self._setup_done = False
        self._shutdown = False
        
        # 统计
        self._total_dispatched = 0
        self._total_completed = 0
        self._total_failed = 0
    
    async def setup(self) -> None:
        """初始化协调器"""
        if self._setup_done:
            return
        
        # 启动心跳监控
        await self.heartbeat_monitor.start()
        
        # 订阅事件
        await self._subscribe_events()
        
        self._setup_done = True
        logger.info("AgentCoordinator setup complete")
    
    async def _subscribe_events(self) -> None:
        """订阅消息事件"""
        # 如果没有 message_bus，跳过订阅
        if not self.message_bus:
            logger.debug("No message_bus, skipping event subscription")
            return
        
        # 订阅进度更新
        await self.message_bus.subscribe(
            "agent.progress",
            self._handle_progress_event
        )
        
        # 订阅心跳
        await self.message_bus.subscribe(
            "agent.heartbeat",
            self._handle_heartbeat_event
        )
    
    async def _handle_progress_event(self, event: Any) -> None:
        """处理进度事件"""
        data = event.data if hasattr(event, 'data') else event
        task_id = data.get("task_id")
        progress = data.get("progress", 0.0)
        status = data.get("status", "")
        
        if task_id:
            self.progress_tracker.update(task_id, progress, status)
    
    async def _handle_heartbeat_event(self, event: Any) -> None:
        """处理心跳事件"""
        data = event.data if hasattr(event, 'data') else event
        task_id = data.get("task_id")
        
        if task_id:
            self.heartbeat_monitor.receive_heartbeat(task_id)
    
    async def dispatch_task(
        self,
        agent: "IAgent",
        task: Dict[str, Any],
        options: Optional[TaskOptions] = None,
        session: Optional["AgentSession"] = None,
    ) -> str:
        """
        分发任务给Agent
        
        Args:
            agent: Agent实例
            task: 任务数据
            options: 执行选项
            session: Agent会话（可选）
            
        Returns:
            任务ID
        """
        if self._shutdown:
            raise RuntimeError("Coordinator is shutdown")
        
        # 准备任务
        prepared = self.task_dispatcher.prepare_task(
            task=task,
            agent=agent,
            options=options,
        )
        
        if not prepared.is_valid():
            raise ValueError(f"Invalid task: {prepared.validation_errors}")
        
        # 创建活跃任务
        active_task = ActiveTask(
            task_id=prepared.task_id,
            agent=agent,
            session=session,
            options=prepared.options,
        )
        
        # 注册
        async with self._lock:
            self._active_tasks[prepared.task_id] = active_task
        
        # 开始进度追踪
        self.progress_tracker.start_tracking(
            task_id=prepared.task_id,
            status="dispatched",
        )
        
        # 开始心跳追踪（使用异步回调）
        self.heartbeat_monitor.start_tracking(
            task_id=prepared.task_id,
            timeout_callback=self._handle_task_timeout,
        )
        
        # 记录分发
        self.task_dispatcher.record_dispatch(prepared.task_id)
        self._total_dispatched += 1
        
        # 启动执行
        active_task._async_task = asyncio.create_task(
            self._execute_with_monitoring(active_task, prepared.task)
        )
        
        logger.info(f"Dispatched task {prepared.task_id} to agent {agent.agent_id}, action={task.get('action')}, topic={task.get('topic')}")
        
        return prepared.task_id
    
    async def _execute_with_monitoring(
        self,
        active_task: ActiveTask,
        task: Dict[str, Any],
    ) -> None:
        """
        带监控的任务执行（支持自动重试）
        
        Args:
            active_task: 活跃任务
            task: 任务数据
        """
        task_id = active_task.task_id
        max_retries = active_task.options.max_retries
        
        # 重试循环
        while True:
            heartbeat_task = None
            
            try:
                # 更新状态
                active_task.status = "running"
                if not active_task.started_at:
                    active_task.started_at = datetime.now()
                
                # 更新 Session 状态为 RUNNING
                self._update_session_status(
                    agent=active_task.agent,
                    status=AgentSessionStatus.RUNNING,
                )
                
                self.progress_tracker.update(
                    task_id=task_id,
                    progress=0.0,
                    status="running",
                )
                
                # 启动心跳发送任务（防止心跳超时）
                heartbeat_task = asyncio.create_task(
                    self._send_periodic_heartbeats(task_id)
                )
                
                # 执行任务（带超时）
                timeout = active_task.options.timeout or self.config.default_timeout
                
                try:
                    # 使用 agent.run() 而非 execute()，确保结果包含标准字段（success, agent_id等）
                    # run() 方法会进行状态管理和结果格式化
                    result = await asyncio.wait_for(
                        active_task.agent.run(task),
                        timeout=timeout
                    )
                    
                    # 确保结果包含必需字段（双重保险）
                    if result is None:
                        result = {"success": False, "error": "Agent returned None"}
                    elif not isinstance(result, dict):
                        result = {"success": True, "result": result}
                    
                    # 确保success字段存在
                    if "success" not in result:
                        result["success"] = True
                    
                    # 确保result字段存在（验证器要求）
                    if result.get("success") and "result" not in result:
                        result["result"] = result.get("output", result.get("data", {}))
                    
                    # 成功完成
                    active_task.status = "completed"
                    active_task.result = result
                    active_task.completed_at = datetime.now()
                    
                    # 更新 Session 状态
                    self._update_session_status(
                        agent=active_task.agent,
                        status=AgentSessionStatus.COMPLETED,
                        result=result,
                    )
                    
                    self.progress_tracker.complete(
                        task_id=task_id,
                        status="completed",
                        metadata={"result_type": type(result).__name__},
                    )
                    
                    self._total_completed += 1
                    logger.info(f"Task {task_id} completed successfully")
                    return  # 成功完成，退出循环
                    
                except asyncio.TimeoutError:
                    error_msg = f"Timeout after {timeout}s"
                    logger.warning(f"Task {task_id} {error_msg} (attempt {active_task.retry_count + 1}/{max_retries})")
                    
                    # 更新重试计数
                    active_task.retry_count += 1
                    
                    # 检查是否还有重试机会
                    if active_task.retry_count >= max_retries:
                        # 重试次数耗尽，记录最终失败
                        active_task.status = "failed"
                        active_task.error = error_msg
                        active_task.completed_at = datetime.now()
                        
                        self._update_session_status(
                            agent=active_task.agent,
                            status=AgentSessionStatus.FAILED,
                            error=error_msg,
                        )
                        
                        self.progress_tracker.fail(
                            task_id=task_id,
                            error=error_msg,
                        )
                        
                        self._total_failed += 1
                        logger.error(f"Task {task_id} exhausted all retries")
                        return  # 退出循环
                    else:
                        # 还有重试机会，继续循环
                        logger.info(f"Task {task_id} will retry (attempt {active_task.retry_count + 1}/{max_retries})")
                        # RY-FIX-1: reset agent state and update task for retry
                        if hasattr(active_task.agent, 'reset'):
                            await active_task.agent.reset()
                        task["retry_attempt"] = active_task.retry_count
                        
                except asyncio.CancelledError:
                    active_task.status = "cancelled"
                    active_task.error = "Task cancelled"
                    active_task.completed_at = datetime.now()
                    
                    # 更新 Session 状态
                    self._update_session_status(
                        agent=active_task.agent,
                        status=AgentSessionStatus.CANCELLED,
                        error="Task cancelled",
                    )
                    
                    self.progress_tracker.update(
                        task_id=task_id,
                        progress=active_task.result.get("progress", 0.0) if active_task.result else 0.0,
                        status="cancelled",
                    )
                    
                    logger.info(f"Task {task_id} cancelled")
                    return  # 取消不重试
                    
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Task {task_id} error: {error_msg} (attempt {active_task.retry_count + 1}/{max_retries})")
                
                # 更新重试计数
                active_task.retry_count += 1
                
                # 检查是否还有重试机会
                if active_task.retry_count >= max_retries:
                    # 重试次数耗尽，记录最终失败
                    active_task.status = "failed"
                    active_task.error = error_msg
                    active_task.completed_at = datetime.now()
                    
                    self._update_session_status(
                        agent=active_task.agent,
                        status=AgentSessionStatus.FAILED,
                        error=error_msg,
                    )
                    
                    self.progress_tracker.fail(
                        task_id=task_id,
                        error=error_msg,
                    )
                    
                    self._total_failed += 1
                    logger.error(f"Task {task_id} exhausted all retries after error")
                    return  # 退出循环
                else:
                    # 还有重试机会，继续循环
                    logger.info(f"Task {task_id} will retry after error (attempt {active_task.retry_count + 1}/{max_retries})")
                    # RY-FIX-1: reset agent state and update task for retry
                    if hasattr(active_task.agent, 'reset'):
                        await active_task.agent.reset()
                    task["retry_attempt"] = active_task.retry_count
                    
            finally:
                # 停止心跳发送
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                # 停止心跳追踪
                self.heartbeat_monitor.stop_tracking(task_id)
    
    async def _send_periodic_heartbeats(self, task_id: str) -> None:
        """
        定期发送心跳（防止长时间任务被误判为超时）
        
        Args:
            task_id: 任务ID
        """
        # 心跳间隔为超时时间的 60%
        interval = self.config.heartbeat_interval * 0.6
        
        while True:
            await asyncio.sleep(interval)
            
            # 直接调用 receive_heartbeat 更新心跳时间
            self.heartbeat_monitor.receive_heartbeat(task_id)
            logger.debug(f"Sent heartbeat for task {task_id}")
    
    async def _handle_task_error(
        self,
        active_task: ActiveTask,
        error: str,
    ) -> None:
        """
        处理任务错误（外部调用，如心跳超时）
        
        注意：此方法用于外部触发的错误处理（如心跳超时）。
        内部执行错误已在 _execute_with_monitoring 中处理，包含重试逻辑。
        
        Args:
            active_task: 活跃任务
            error: 错误信息
        """
        task_id = active_task.task_id
        
        # 如果任务仍在运行，标记为失败
        if active_task.status == "running":
            active_task.status = "failed"
            active_task.error = error
            active_task.completed_at = datetime.now()
            
            # 更新 Session 状态
            self._update_session_status(
                agent=active_task.agent,
                status=AgentSessionStatus.FAILED,
                error=error,
            )
            
            self.progress_tracker.fail(
                task_id=task_id,
                error=error,
            )
            
            self._total_failed += 1
            
            logger.error(f"Task {task_id} failed (external trigger): {error}")
    
    def _update_session_status(
        self,
        agent: "IAgent",
        status: AgentSessionStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        更新 Agent Session 状态
        
        Args:
            agent: Agent 实例
            status: 新状态
            result: 执行结果（可选）
            error: 错误信息（可选）
        """
        if not self.session_registry:
            return
        
        # 通过 agent_id 获取对应的 session
        session = self.session_registry.get_by_agent(agent.agent_id)
        if not session:
            logger.debug(f"No session found for agent {agent.agent_id}")
            return
        
        # 更新状态
        self.session_registry.update_status(
            session_id=session.session_id,
            status=status,
            result=result,
            error=error,
        )
        
        # 持久化到文件 - 使用正确的 storage_path（AgentSessionRegistry.save() 会自动拼接 /registries/）
        try:
            from pathlib import Path
            try:
                from src.config import settings
                storage_path = Path(getattr(settings.system.paths, 'data_dir', 'data'))
            except Exception:
                storage_path = Path("data")
            storage_path.mkdir(parents=True, exist_ok=True)
            self.session_registry.save(storage_path)
            logger.debug(f"Persisted session {session.session_id} status to {status.value}")
        except Exception as e:
            logger.warning(f"Failed to persist session: {e}")
        
        logger.debug(f"Updated session {session.session_id} status to {status.value}")
    
    async def _handle_task_timeout(self, task_id: str) -> None:
        """
        处理任务超时
        
        Args:
            task_id: 任务ID
        """
        async with self._lock:
            active_task = self._active_tasks.get(task_id)
            if not active_task:
                return
            
            # 设取消标志
            self.cancel_manager.cancel(task_id)
            logger.info(f"Task {task_id} timed out")
            
            # 取消异步任务并等待完成
            if active_task._async_task and not active_task._async_task.done():
                active_task._async_task.cancel()
                try:
                    await active_task._async_task
                except asyncio.CancelledError:
                    pass  # 预期中的取消
    
    async def wait_for_completion(
        self,
        task_ids: List[str],
        timeout: Optional[float] = None,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        等待任务完成
        
        Args:
            task_ids: 任务ID列表
            timeout: 超时时间（总超时，应用于所有任务）
            
        Returns:
            task_id -> 结果的映射（结果可能为None）
        """
        async def wait_one(task_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
            active_task = self._active_tasks.get(task_id)
            if not active_task:
                return (task_id, None)
            
            # 等待异步任务完成（无内部超时，由外层控制）
            if active_task._async_task:
                try:
                    await active_task._async_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.debug(f"Task {task_id} raised exception: {e}")
            
            # ER-FIX-1: return error info when result is None
            if active_task.result is not None:
                return (task_id, active_task.result)
            if active_task.error:
                return (task_id, {"success": False, "error": active_task.error,
                                  "agent_id": active_task.agent.agent_id})
            return (task_id, None)
        
        # 使用外层超时控制
        tasks = [asyncio.create_task(wait_one(tid)) for tid in task_ids]
        
        try:
            if timeout:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout
                )
            else:
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            # 超时时取消所有等待任务
            for t in tasks:
                t.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 清理超时任务的内部异步任务
            for tid in task_ids:
                active_task = self._active_tasks.get(tid)
                if active_task and active_task._async_task:
                    if not active_task._async_task.done():
                        active_task._async_task.cancel()
                        logger.warning(f"Cancelled internal task for {tid} due to timeout")
        
        # 构建结果
        final_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for tid, result in zip(task_ids, results):
            if isinstance(result, asyncio.TimeoutError):
                final_results[tid] = {"success": False, "error": "Timeout"}
            elif isinstance(result, BaseException):
                final_results[tid] = {"success": False, "error": str(result)}
            else:
                final_results[tid] = result[1] if result else None
        
        return final_results
    
    async def wait_for_any(
        self,
        task_ids: List[str],
        timeout: Optional[float] = None,
    ) -> Optional[tuple[str, Optional[Dict[str, Any]]]]:
        """
        等待任意任务完成
        
        Args:
            task_ids: 任务ID列表
            timeout: 超时时间
            
        Returns:
            (task_id, result) 元组，result可能为None
        """
        # 检查已完成的任务
        for task_id in task_ids:
            active_task = self._active_tasks.get(task_id)
            if active_task and active_task.status == "completed" and active_task.result:
                return (task_id, active_task.result)
        
        # 创建等待任务
        async def wait_one(task_id: str) -> Optional[tuple[str, Dict[str, Any]]]:
            active_task = self._active_tasks.get(task_id)
            if not active_task:
                return None
            
            if active_task._async_task:
                try:
                    await asyncio.wait_for(
                        active_task._async_task,
                        timeout=timeout or self.config.default_timeout
                    )
                except asyncio.TimeoutError:
                    return None
            
            if active_task.result:
                return (task_id, active_task.result)
            return None
        
        tasks = [asyncio.create_task(wait_one(tid)) for tid in task_ids]
        
        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的等待任务
            for task in pending:
                task.cancel()
            
            # 返回第一个完成的结果
            for task in done:
                result = task.result()
                if result:
                    return result
            
            return None
            
        except asyncio.TimeoutError:
            # 超时时取消所有等待任务
            for task in tasks:
                task.cancel()
            
            # 清理超时任务的内部异步任务
            for tid in task_ids:
                active_task = self._active_tasks.get(tid)
                if active_task and active_task._async_task:
                    if not active_task._async_task.done():
                        active_task._async_task.cancel()
                        logger.debug(f"Cancelled internal task for {tid} in wait_for_any")
            
            return None
            
        except Exception as e:
            logger.error(f"Error in wait_for_any: {e}")
            return None
    
    async def cancel_task(
        self,
        task_id: str,
        reason: CancelReason = CancelReason.USER_REQUEST,
        message: str = "",
    ) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID
            reason: 取消原因（保留参数签名兼容）
            message: 取消消息（保留参数签名兼容）

        Returns:
            是否成功取消
        """
        active_task = self._active_tasks.get(task_id)
        if not active_task:
            return False

        # 设取消标志
        self.cancel_manager.cancel(task_id)
        logger.info(f"Task {task_id} cancelled: {reason.value} - {message}")

        # 取消异步任务
        if active_task._async_task and not active_task._async_task.done():
            active_task._async_task.cancel()
        
        # 更新状态
        active_task.status = "cancelled"
        active_task.error = message or "Cancelled"
        active_task.completed_at = datetime.now()
        
        logger.info(f"Task {task_id} cancelled: {reason.value}")
        
        return True
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        active_task = self._active_tasks.get(task_id)
        return active_task.status if active_task else None
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务结果"""
        active_task = self._active_tasks.get(task_id)
        return active_task.result if active_task else None
    
    def get_active_tasks(self) -> List[str]:
        """获取所有活跃任务ID"""
        return list(self._active_tasks.keys())
    
    def get_running_tasks(self) -> List[str]:
        """获取所有运行中的任务ID"""
        return [
            tid for tid, task in self._active_tasks.items()
            if task.status == "running"
        ]
    
    def get_pending_tasks(self) -> List[str]:
        """获取所有待执行的任务ID"""
        return [
            tid for tid, task in self._active_tasks.items()
            if task.status == "pending"
        ]
    
    def get_completed_tasks(self) -> List[str]:
        """获取所有已完成的任务ID"""
        return [
            tid for tid, task in self._active_tasks.items()
            if task.status == "completed"
        ]
    
    def get_failed_tasks(self) -> List[str]:
        """获取所有失败的任务ID"""
        return [
            tid for tid, task in self._active_tasks.items()
            if task.status in ("failed", "cancelled")
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_tasks": len(self._active_tasks),
            "running": len(self.get_running_tasks()),
            "pending": len(self.get_pending_tasks()),
            "completed": len(self.get_completed_tasks()),
            "failed": len(self.get_failed_tasks()),
            "total_dispatched": self._total_dispatched,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "dispatcher": self.task_dispatcher.get_stats(),
            "progress": self.progress_tracker.get_stats(),
            "heartbeat": self.heartbeat_monitor.get_stats(),
            "cancel": {"total_cancelled": len(self.cancel_manager._cancelled)} if hasattr(self.cancel_manager, '_cancelled') else {},
        }
    
    async def shutdown(self) -> None:
        """关闭协调器"""
        if self._shutdown:
            return
        
        self._shutdown = True
        logger.info("Shutting down AgentCoordinator")
        
        # 停止心跳监控
        await self.heartbeat_monitor.stop()
        
        # 取消所有运行中的任务
        for task_id in self.get_running_tasks():
            await self.cancel_task(
                task_id=task_id,
                reason=CancelReason.SHUTDOWN,
                message="Coordinator shutdown",
            )
        
        # 等待所有任务完成
        running = self.get_running_tasks()
        if running:
            try:
                await asyncio.wait_for(
                    self.wait_for_completion(running),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for {len(running)} tasks to complete")
        
        # 清理
        self._active_tasks.clear()
        self.progress_tracker.clear()
        self.heartbeat_monitor.clear()
        
        logger.info("AgentCoordinator shutdown complete")
