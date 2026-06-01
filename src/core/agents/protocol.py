"""
Agent Protocol 定义
==================

定义所有Agent必须实现的统一接口契约。

关键约束（CRITICAL）：
1. 主控Orchestrator依赖 config.get("name") 和 config.get("context") 分类Agent
2. AgentFactory依赖 agent_id, agent_type, config 构造函数参数
3. Factory直接设置 _session, _message_bus, _shared_memory 私有属性

设计文档: .sisyphus/plans/agent_mixin_refactor_plan.md
"""
from typing import Any, Dict, Optional, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.communication import MessageBus, SharedMemory
    from src.core.agents.agent_session import AgentSession


@runtime_checkable
class IAgent(Protocol):
    """
    Agent统一接口契约
    
    所有Agent必须实现此Protocol定义的接口。
    使用@runtime_checkable允许运行时isinstance检查。
    
    实现约束：
    - 必须有agent_id, agent_type, config属性
    - 必须支持通信能力注入（_session, _message_bus, _shared_memory）
    - 必须实现异步execute()方法
    
    主控依赖（research_orchestrator.py:688）：
        data_agents = [a for a in agents if "数据" in a.config.get("name", "")]
    
    Factory依赖（factory.py:133）：
        agent = GenericAgent(agent_id=agent_id, agent_type="dynamic", config=config)
    
    通信注入依赖（factory.py:178）：
        agent._session = session
        agent._message_bus = self._message_bus
        agent._shared_memory = self._shared_memory
    """
    
    # === 核心标识属性（Factory必需） ===
    agent_id: str
    agent_type: str
    
    # === 配置字典（主控依赖name和context键） ===
    config: Dict[str, Any]
    
    # === 通信能力属性（Factory注入） ===
    # 注意：Protocol中这些是类型提示，实现类必须有这些属性
    _session: Optional["AgentSession"]
    _message_bus: Optional["MessageBus"]
    _shared_memory: Optional["SharedMemory"]
    
    # === 核心执行方法 ===
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务（核心方法，必须实现）
        
        Args:
            task: 任务定义，具体格式由子类定义
            
        Returns:
            执行结果，必须包含success字段
            
        注意：
        - 必须是异步方法
        - FixedAgent: 子类必须实现具体逻辑
        - GenericAgent: 有默认实现，路由到Skill
        """
        ...
    
    async def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行任务（带生命周期管理）
        
        包含：
        - 输入验证（调用validate_input）
        - 状态转换（idle → running → completed/error）
        - 事件发布（task_started, task_completed, task_error）
        - 错误处理
        
        Args:
            task: 任务定义
            
        Returns:
            执行结果，包含success, agent_id, agent_name等字段
        """
        ...
    
    # === 通信能力注入 ===
    
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
        ...
    
    # === 状态管理 ===
    
    @property
    def status(self) -> str:
        """
        获取当前状态
        
        Returns:
            状态字符串: idle/running/completed/error
        """
        ...
    
    def update_state(
        self, 
        status: Optional[str] = None, 
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        更新状态
        
        线程安全：使用_lock保护状态读写
        
        Args:
            status: 新状态（可选）
            data: 附加数据，合并到现有数据（可选）
        """
        ...
    
    def get_state(self) -> "AgentState":
        """
        获取当前状态快照
        
        线程安全：使用_lock保护状态读取
        
        Returns:
            AgentState实例，包含agent_id, status, data等
        """
        ...
    
    # === 输入验证（FixedAgent契约） ===
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证输入参数
        
        FixedAgent的重要契约，run()方法强制调用。
        30+子类覆盖此方法添加特定验证逻辑。
        
        Args:
            task_input: 待验证的输入参数
            
        Returns:
            (是否有效, 错误信息)
            
        默认实现：
            - 检查task_input是否为dict类型
            - 子类可覆盖添加特定验证
        """
        ...
    
    # === 状态重置 ===
    
    def reset(self) -> None:
        """
        重置Agent状态
        
        用于测试验证和固定Agent复用场景。
        将状态重置为idle，清空数据。
        """
        ...
    
    # === 通信方法 ===
    
    async def publish_event(self, event_type: str, data: Any) -> None:
        """
        发布事件到MessageBus
        
        Args:
            event_type: 事件类型（如task_started, task_completed, task_error）
            data: 事件数据
        """
        ...
    
    async def read_shared_state(self, key: str) -> Optional[Any]:
        """
        读取共享状态
        
        Args:
            key: 状态键
            
        Returns:
            状态值，无SharedMemory返回None
        """
        ...
    
    async def write_shared_state(self, key: str, value: Any) -> None:
        """
        写入共享状态
        
        Args:
            key: 状态键
            value: 状态值
        """
        ...


# 类型别名，方便使用
AgentLike = IAgent  # 任何实现IAgent Protocol的对象
