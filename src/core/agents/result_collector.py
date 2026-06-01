"""
ResultCollector - 结果收集器

提供事件驱动的Agent结果收集机制。
主控Agent通过此机制收集子Agent的结果。

特性:
1. 订阅 agent.completed 事件
2. 支持异步等待单个/全部Agent完成
3. 支持超时控制
4. 线程安全

设计文档: docs/AGENT_SESSION_MANAGEMENT.md
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
import logging

from ..communication import MessageBus, Event, SharedMemory


logger = logging.getLogger(__name__)


@dataclass
class ResultCollector:
    """
    结果收集器
    
    主控Agent通过此机制收集子Agent的结果。
    基于MessageBus的发布/订阅模式实现事件驱动收集。
    
    Attributes:
        parent_session_id: 主控Session ID
        message_bus: MessageBus实例
        shared_memory: SharedMemory实例（可选）
        
    Usage:
        collector = ResultCollector(
            parent_session_id="research_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 等待单个Agent
        result = await collector.wait_for_agent("agent_001", timeout=30.0)
        
        # 等待所有Agent
        results = await collector.wait_for_all(["agent_001", "agent_002"], timeout=60.0)
    """
    parent_session_id: str
    message_bus: MessageBus
    shared_memory: Optional[SharedMemory] = None
    
    # 内部状态
    _results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _completion_events: Dict[str, asyncio.Event] = field(default_factory=dict)
    _progress_handlers: Dict[str, Callable] = field(default_factory=dict)
    
    async def setup(self) -> None:
        """
        设置事件监听
        
        订阅以下事件:
        - session.{parent_session_id}.agent.completed - Agent完成
        - session.{parent_session_id}.agent.progress - Agent进度更新
        - session.{parent_session_id}.agent.failed - Agent失败
        """
        # 订阅完成事件
        await self.message_bus.subscribe(
            f"session.{self.parent_session_id}.agent.completed",
            self._handle_agent_completed
        )
        
        # 订阅进度事件
        await self.message_bus.subscribe(
            f"session.{self.parent_session_id}.agent.progress",
            self._handle_agent_progress
        )
        
        # 订阅失败事件
        await self.message_bus.subscribe(
            f"session.{self.parent_session_id}.agent.failed",
            self._handle_agent_failed
        )
        
        logger.debug(f"ResultCollector setup for session {self.parent_session_id}")
    
    async def _handle_agent_completed(self, event: Event) -> None:
        """
        处理Agent完成事件
        
        Args:
            event: 完成事件，包含session_id, agent_id, result
        """
        data = event.data
        session_id = data.get("session_id")
        
        if not session_id:
            logger.warning("Received completed event without session_id")
            return
        
        # 存储结果
        self._results[session_id] = {
            "session_id": session_id,
            "agent_id": data.get("agent_id"),
            "result": data.get("result"),
            "completed_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        logger.debug(f"Agent {session_id} completed")
        
        # 触发完成事件
        if session_id in self._completion_events:
            self._completion_events[session_id].set()
    
    async def _handle_agent_progress(self, event: Event) -> None:
        """
        处理Agent进度事件
        
        Args:
            event: 进度事件，包含session_id, progress
        """
        data = event.data
        session_id = data.get("session_id")
        progress = data.get("progress", 0.0)
        
        if session_id and session_id in self._progress_handlers:
            handler = self._progress_handlers[session_id]
            if asyncio.iscoroutinefunction(handler):
                await handler(progress)
            else:
                handler(progress)
    
    async def _handle_agent_failed(self, event: Event) -> None:
        """
        处理Agent失败事件
        
        Args:
            event: 失败事件，包含session_id, error
        """
        data = event.data
        session_id = data.get("session_id")
        
        if not session_id:
            return
        
        # 存储失败信息
        self._results[session_id] = {
            "session_id": session_id,
            "agent_id": data.get("agent_id"),
            "error": data.get("error"),
            "failed_at": datetime.now().isoformat(),
            "status": "failed"
        }
        
        logger.warning(f"Agent {session_id} failed: {data.get('error')}")
        
        # 触发完成事件（失败也算完成）
        if session_id in self._completion_events:
            self._completion_events[session_id].set()
    
    async def wait_for_agent(
        self,
        session_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        等待特定Agent完成
        
        Args:
            session_id: Agent Session ID
            timeout: 超时时间（秒），None表示不超时
            
        Returns:
            Agent结果，超时返回None
        """
        # 如果已有结果，立即返回
        if session_id in self._results:
            return self._results[session_id]
        
        # 创建等待事件
        if session_id not in self._completion_events:
            self._completion_events[session_id] = asyncio.Event()
        
        event = self._completion_events[session_id]
        
        try:
            if timeout is not None:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()
            
            return self._results.get(session_id)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for agent {session_id}")
            return None
    
    async def wait_for_all(
        self,
        session_ids: List[str],
        timeout: Optional[float] = None
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        等待所有Agent完成
        
        Args:
            session_ids: Agent Session ID列表
            timeout: 超时时间（秒），None表示不超时
            
        Returns:
            所有Agent结果（超时的为None）
        """
        tasks = [
            self.wait_for_agent(sid, timeout=timeout)
            for sid in session_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 构建结果字典，处理异常和None
        final_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for sid, result in zip(session_ids, results):
            if isinstance(result, BaseException):
                # 异常情况，返回None
                final_results[sid] = None
            else:
                # 正常情况，result 是 Optional[Dict[str, Any]]
                final_results[sid] = result
        
        return final_results
    
    async def wait_for_any(
        self,
        session_ids: List[str],
        timeout: Optional[float] = None
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        等待任意一个Agent完成
        
        Args:
            session_ids: Agent Session ID列表
            timeout: 超时时间（秒）
            
        Returns:
            (session_id, result) 元组，全部超时返回None
        """
        # 先检查是否已有完成的结果
        for sid in session_ids:
            if sid in self._results:
                return (sid, self._results[sid])
        
        # 创建所有等待任务
        async def wait_for_one(sid: str) -> Optional[tuple[str, Dict[str, Any]]]:
            result = await self.wait_for_agent(sid, timeout=timeout)
            return (sid, result) if result else None
        
        tasks = [asyncio.create_task(wait_for_one(sid)) for sid in session_ids]
        
        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
            
            # 返回第一个完成的结果
            for task in done:
                result = task.result()
                if result:
                    return result
            
            return None
        except Exception as e:
            logger.error(f"Error in wait_for_any: {e}")
            return None
    
    def get_results(self) -> Dict[str, Dict[str, Any]]:
        """
        获取已收集的所有结果
        
        Returns:
            Session ID -> 结果的映射
        """
        return self._results.copy()
    
    def get_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取特定Agent的结果
        
        Args:
            session_id: Session ID
            
        Returns:
            结果，不存在返回None
        """
        return self._results.get(session_id)
    
    def has_result(self, session_id: str) -> bool:
        """
        检查是否已收集特定Agent的结果
        
        Args:
            session_id: Session ID
            
        Returns:
            是否存在结果
        """
        return session_id in self._results
    
    def count_results(self) -> int:
        """获取已收集结果的数量"""
        return len(self._results)
    
    def count_completed(self) -> int:
        """获取已完成的Agent数量"""
        return sum(
            1 for r in self._results.values()
            if r.get("status") == "completed"
        )
    
    def count_failed(self) -> int:
        """获取失败的Agent数量"""
        return sum(
            1 for r in self._results.values()
            if r.get("status") == "failed"
        )
    
    def register_progress_handler(
        self,
        session_id: str,
        handler: Callable[[float], Any]
    ) -> None:
        """
        注册进度更新处理器
        
        Args:
            session_id: Session ID
            handler: 进度处理函数，接收progress参数
        """
        self._progress_handlers[session_id] = handler
    
    def unregister_progress_handler(self, session_id: str) -> bool:
        """
        注销进度更新处理器
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功注销
        """
        if session_id in self._progress_handlers:
            del self._progress_handlers[session_id]
            return True
        return False
    
    def clear(self) -> None:
        """清空所有结果"""
        self._results.clear()
        self._completion_events.clear()
        self._progress_handlers.clear()
    
    async def close(self) -> None:
        """
        关闭收集器，取消所有订阅
        """
        # 取消订阅
        await self.message_bus.unsubscribe(
            f"session.{self.parent_session_id}.agent.completed",
            self._handle_agent_completed
        )
        await self.message_bus.unsubscribe(
            f"session.{self.parent_session_id}.agent.progress",
            self._handle_agent_progress
        )
        await self.message_bus.unsubscribe(
            f"session.{self.parent_session_id}.agent.failed",
            self._handle_agent_failed
        )
        
        logger.debug(f"ResultCollector closed for session {self.parent_session_id}")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        获取状态摘要
        
        Returns:
            包含total、completed、failed等统计信息
        """
        return {
            "parent_session_id": self.parent_session_id,
            "total": len(self._results),
            "completed": self.count_completed(),
            "failed": self.count_failed(),
            "session_ids": list(self._results.keys())
        }