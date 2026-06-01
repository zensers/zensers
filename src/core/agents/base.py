"""
Agent 基类实现
============

提供所有 Agent 的基础功能，包括:
- 状态管理
- 通信能力（MessageBus/SharedMemory）
- 异步执行
- 生命周期管理

设计文档: docs/STATUS/AGENT_UNIFICATION_PLAN.md
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, Type, TYPE_CHECKING
from threading import Lock
import logging

if TYPE_CHECKING:
    from src.core.communication import MessageBus, SharedMemory, Event
    from src.core.agents.agent_session import AgentSession

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """
    Agent 状态数据类
    
    Attributes:
        agent_id: Agent 唯一标识
        status: 当前状态 (idle/running/completed/error)
        data: 附加数据
        created_at: 创建时间
        updated_at: 更新时间
    """
    agent_id: str
    status: str = "idle"
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "data": self.data,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        """从字典创建"""
        return cls(
            agent_id=data["agent_id"],
            status=data.get("status", "idle"),
            data=data.get("data", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat())
        )


class BaseAgent(ABC):
    """
    Agent 抽象基类
    
    所有具体 Agent 必须继承此类。
    提供统一的状态管理、通信能力和生命周期管理。
    
    通信能力:
    - _message_bus: MessageBus 实例（通过 inject_communication 注入）
    - _shared_memory: SharedMemory 实例（通过 inject_communication 注入）
    - _session: AgentSession 实例（可选）
    
    使用示例:
        agent = MyAgent(agent_id="001", agent_type="analysis")
        agent.inject_communication(message_bus=bus, shared_memory=mem)
        result = await agent.execute(task)
    """
    
    def __init__(self, agent_id: str, agent_type: str, config: Optional[Dict] = None):
        """
        初始化 Agent
        
        Args:
            agent_id: 唯一标识
            agent_type: Agent 类型
            config: 配置字典
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.config = config or {}
        
        # 状态管理
        self._status = "idle"
        self._data: Dict[str, Any] = {}
        self._lock = Lock()
        
        # 通信能力（通过 inject_communication 注入）
        self._message_bus: Optional['MessageBus'] = None
        self._shared_memory: Optional['SharedMemory'] = None
        self._session: Optional['AgentSession'] = None
        
        # P0-1修复: 从 config.context 中提取 section_id
        # 用于 ContentLockManager 的章节锁定机制
        # self.config 在第96行已确保是字典，无需额外检查
        context = self.config.get("context", {})
        self.section_id = context.get("section_id", "")
        
        # 创建时间
        self._created_at = datetime.now().isoformat()
        self._updated_at = self._created_at
    
    # === 通信能力 ===
    
    def inject_communication(
        self,
        message_bus: Optional['MessageBus'] = None,
        shared_memory: Optional['SharedMemory'] = None,
        session: Optional['AgentSession'] = None
    ) -> None:
        """
        注入通信能力
        
        Args:
            message_bus: MessageBus 实例
            shared_memory: SharedMemory 实例
            session: AgentSession 实例
        """
        if message_bus is not None:
            self._message_bus = message_bus
        if shared_memory is not None:
            self._shared_memory = shared_memory
        if session is not None:
            self._session = session
        logger.debug(f"Agent {self.agent_id}: 通信能力已注入")
    
    async def publish_event(self, event_type: str, data: Any) -> None:
        """
        发布事件到 MessageBus
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self._message_bus:
            from src.core.communication import Event
            await self._message_bus.publish(
                topic=f"agent.{self.agent_id}",
                event=Event(type=event_type, data=data, source=self.agent_id)
            )
    
    async def read_shared_state(self, key: str) -> Any:
        """
        读取共享状态
        
        Args:
            key: 状态键
            
        Returns:
            状态值，无 SharedMemory 返回 None
        """
        if self._shared_memory:
            return await self._shared_memory.read(key)
        return None
    
    async def write_shared_state(self, key: str, value: Any) -> None:
        """
        写入共享状态
        
        Args:
            key: 状态键
            value: 状态值
        """
        if self._shared_memory:
            await self._shared_memory.write(key, value)
    
    # === 状态管理 ===
    
    @property
    def status(self) -> str:
        """获取当前状态"""
        with self._lock:
            return self._status
    
    def update_state(self, status: Optional[str] = None, data: Optional[Dict] = None) -> None:
        """
        更新状态
        
        Args:
            status: 新状态
            data: 附加数据（合并到现有数据）
        """
        with self._lock:
            if status:
                self._status = status
            if data:
                self._data.update(data)
            self._updated_at = datetime.now().isoformat()
    
    def get_state(self) -> AgentState:
        """获取当前状态"""
        with self._lock:
            return AgentState(
                agent_id=self.agent_id,
                status=self._status,
                data=self._data.copy(),
                created_at=self._created_at,
                updated_at=self._updated_at
            )
    
    # === 执行接口 ===
    
    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务（必须由子类实现，异步）
        
        Args:
            task: 任务定义
            
        Returns:
            执行结果
        """
        pass
    
    async def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行任务（带生命周期管理）
        
        Args:
            task: 任务定义
            
        Returns:
            执行结果
        """
        try:
            # 发布开始事件
            await self.publish_event("task_started", {"task_keys": list(task.keys())})
            
            # 开始执行
            self.update_state(status="running", data={"task": task})
            
            # 执行
            result = await self.execute(task)
            
            # 完成
            self.update_state(status="completed", data={"result": result})
            
            # 发布完成事件
            await self.publish_event("task_completed", {
                "success": result.get("success", True) if isinstance(result, dict) else True
            })
            
            return result
            
        except Exception as e:
            # 错误
            self.update_state(status="error", data={"error": str(e)})
            
            # 发布错误事件
            await self.publish_event("task_error", {"error": str(e)})
            
            raise


class AgentFactory:
    """
    Agent 工厂
    
    用于注册和创建 Agent 实例。
    支持自动注入通信能力。
    """
    
    def __init__(self):
        self._registry: Dict[str, Type[BaseAgent]] = {}
        self._message_bus: Optional['MessageBus'] = None
        self._shared_memory: Optional['SharedMemory'] = None
    
    def set_communication(
        self,
        message_bus: Optional['MessageBus'] = None,
        shared_memory: Optional['SharedMemory'] = None
    ) -> None:
        """
        设置通信组件（创建Agent时自动注入）
        
        Args:
            message_bus: MessageBus 实例
            shared_memory: SharedMemory 实例
        """
        self._message_bus = message_bus
        self._shared_memory = shared_memory
    
    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        注册 Agent 类型
        
        Args:
            agent_type: 类型标识
            agent_class: Agent 类
        """
        self._registry[agent_type] = agent_class
    
    def create(
        self, 
        agent_type: str, 
        agent_id: str, 
        config: Optional[Dict] = None,
        inject_communication: bool = True
    ) -> BaseAgent:
        """
        创建 Agent 实例
        
        Args:
            agent_type: 类型标识
            agent_id: 唯一标识
            config: 配置
            inject_communication: 是否自动注入通信能力
            
        Returns:
            Agent 实例
            
        Raises:
            ValueError: 未注册的类型
        """
        if agent_type not in self._registry:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_class = self._registry[agent_type]
        agent = agent_class(agent_id=agent_id, agent_type=agent_type, config=config)
        
        # 自动注入通信能力
        if inject_communication and (self._message_bus or self._shared_memory):
            agent.inject_communication(
                message_bus=self._message_bus,
                shared_memory=self._shared_memory
            )
        
        return agent
    
    def list_types(self) -> list:
        """列出所有注册的类型"""
        return list(self._registry.keys())
    
    def has_type(self, agent_type: str) -> bool:
        """检查是否已注册类型"""
        return agent_type in self._registry
