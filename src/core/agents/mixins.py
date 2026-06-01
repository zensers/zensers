"""
Agent Mixins 定义
================

提供Agent的共享能力实现，通过组合模式复用代码。

设计原则：
1. Mixin不定义__init__，由宿主类负责初始化
2. Mixin依赖宿主类提供必要的属性
3. Mixin方法必须是独立的，不依赖其他Mixin

关键约束：
- StateManagementMixin必须包含_lock机制（异步安全）
- CommunicationMixin必须正确处理None情况（通信组件可能未注入）

v2.1 修复：
- 将threading.Lock替换为asyncio.Lock，避免在异步环境中阻塞事件循环

设计文档: .sisyphus/plans/agent_mixin_refactor_plan.md
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from src.core.communication import MessageBus, SharedMemory, Event
    from src.core.agents.agent_session import AgentSession
    from src.core.agents.base import AgentState

logger = logging.getLogger(__name__)


class StateManagementMixin:
    """
    状态管理Mixin
    
    提供Agent的状态管理能力，包括：
    - 状态读写（异步安全）
    - 状态快照
    - 状态重置
    
    宿主类必须提供：
    - agent_id: str
    - _status: str（初始值"idle"）
    - _data: Dict[str, Any]（初始值{}）
    - _lock: asyncio.Lock（初始值asyncio.Lock()）
    - _created_at: str（创建时间）
    - _updated_at: str（更新时间）
    
    异步安全保证：
    - 所有状态读写都通过asyncio.Lock保护
    - update_state()和get_state()是原子操作
    - 注意：status属性是同步的（只读，风险较低）
    """
    
    # 宿主类必须定义这些属性（类型提示）
    agent_id: str
    _status: str
    _data: Dict[str, Any]
    _lock: asyncio.Lock
    _created_at: str
    _updated_at: str
    
    @property
    def status(self) -> str:
        """
        获取当前状态（同步，只读）
        
        注意：这是同步方法，用于快速状态检查。
        对于需要原子性的操作，请使用async get_state()。
        
        Returns:
            状态字符串: idle/running/completed/error
        """
        return self._status
    
    async def update_state(
        self,
        status: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        更新状态（异步安全）
        
        Args:
            status: 新状态（可选）
            data: 附加数据，合并到现有数据（可选）
        """
        async with self._lock:
            if status is not None:
                self._status = status
            if data is not None:
                self._data.update(data)
            self._updated_at = datetime.now().isoformat()
    
    async def get_state(self) -> "AgentState":
        """
        获取当前状态快照（异步安全）
        
        Returns:
            AgentState实例，包含完整状态信息
        """
        from src.core.agents.base import AgentState
        
        async with self._lock:
            return AgentState(
                agent_id=self.agent_id,
                status=self._status,
                data=self._data.copy(),  # 返回副本，避免外部修改
                created_at=self._created_at,
                updated_at=self._updated_at
            )
    
    async def reset(self) -> None:
        """
        重置Agent状态（异步安全）
        
        将状态重置为idle，清空数据。
        用于测试验证和固定Agent复用场景。
        """
        async with self._lock:
            self._status = "idle"
            self._data.clear()
            self._updated_at = datetime.now().isoformat()
        logger.debug(f"Agent {self.agent_id}: 状态已重置")


class CommunicationMixin:
    """
    通信能力Mixin
    
    提供Agent的通信能力，包括：
    - 事件发布（MessageBus）
    - 状态共享（SharedMemory）
    - 通信组件注入
    
    宿主类必须提供：
    - agent_id: str
    - _message_bus: Optional[MessageBus]
    - _shared_memory: Optional[SharedMemory]
    - _session: Optional[AgentSession]
    
    安全保证：
    - 所有方法正确处理None情况（通信组件可能未注入）
    - 异步方法不阻塞事件循环
    """
    
    # 宿主类必须定义这些属性（类型提示）
    agent_id: str
    _message_bus: Optional["MessageBus"]
    _shared_memory: Optional["SharedMemory"]
    _session: Optional["AgentSession"]
    
    def inject_communication(
        self,
        message_bus: Optional["MessageBus"] = None,
        shared_memory: Optional["SharedMemory"] = None,
        session: Optional["AgentSession"] = None
    ) -> None:
        """
        注入通信能力

        由AgentFactory调用，注入MessageBus、SharedMemory和Session实例。

        Args:
            message_bus: MessageBus实例，用于事件发布
            shared_memory: SharedMemory实例，用于状态共享
            session: AgentSession实例，用于Session管理
        """
        if message_bus is not None:
            self._message_bus = message_bus
        if shared_memory is not None:
            self._shared_memory = shared_memory
        if session is not None:
            self._session = session
        logger.debug(f"Agent {self.agent_id}: 通信能力已注入")

    def set_message_bus(self, message_bus: Optional["MessageBus"]) -> None:
        """
        设置MessageBus（向后兼容方法）

        Args:
            message_bus: MessageBus实例
        """
        self._message_bus = message_bus
        logger.debug(f"Agent {self.agent_id}: MessageBus已设置")

    def set_shared_memory(self, shared_memory: Optional["SharedMemory"]) -> None:
        """
        设置SharedMemory（向后兼容方法）

        Args:
            shared_memory: SharedMemory实例
        """
        self._shared_memory = shared_memory
        logger.debug(f"Agent {self.agent_id}: SharedMemory已设置")
    
    async def publish_event(self, event_type: str, data: Any) -> None:
        """
        发布事件到MessageBus
        
        Args:
            event_type: 事件类型（如task_started, task_completed, task_error）
            data: 事件数据
            
        注意：
            如果_message_bus为None，静默忽略（不抛出异常）
        """
        if self._message_bus is None:
            logger.debug(f"Agent {self.agent_id}: MessageBus未注入，跳过事件发布")
            return
        
        from src.core.communication import Event
        
        await self._message_bus.publish(
            topic=f"agent.{self.agent_id}",
            event=Event(
                type=event_type,
                data=data,
                source=self.agent_id
            )
        )
    
    async def read_shared_state(self, key: str) -> Optional[Any]:
        """
        读取共享状态
        
        Args:
            key: 状态键
            
        Returns:
            状态值，无SharedMemory返回None
        """
        if self._shared_memory is None:
            logger.debug(f"Agent {self.agent_id}: SharedMemory未注入，返回None")
            return None
        
        return await self._shared_memory.read(key)
    
    async def write_shared_state(self, key: str, value: Any) -> None:
        """
        写入共享状态
        
        Args:
            key: 状态键
            value: 状态值
            
        注意：
            如果_shared_memory为None，静默忽略
        """
        if self._shared_memory is None:
            logger.debug(f"Agent {self.agent_id}: SharedMemory未注入，跳过状态写入")
            return
        
        await self._shared_memory.write(key, value)


class InputValidationMixin:
    """
    输入验证Mixin
    
    提供Agent的输入验证能力。
    
    宿主类必须提供：
    - agent_id: str
    
    设计说明：
    - validate_input()是FixedAgent的重要契约
    - run()方法强制调用此方法
    - 子类可覆盖添加特定验证逻辑
    """
    
    agent_id: str
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证输入参数（默认实现）
        
        Args:
            task_input: 待验证的输入参数
            
        Returns:
            (是否有效, 错误信息)
            
        默认实现：
            - 检查task_input是否为dict类型
            
        子类覆盖示例：
            def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
                # 先调用父类验证
                valid, error = super().validate_input(task_input)
                if not valid:
                    return valid, error
                
                # 添加特定验证
                if "required_field" not in task_input:
                    return False, "缺少必需字段: required_field"
                
                return True, ""
        """
        if not isinstance(task_input, dict):
            return False, "输入必须是字典类型"
        return True, ""
