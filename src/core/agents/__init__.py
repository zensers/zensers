"""
Agent 模块

提供 Agent 基类和工厂

v2.0 更新：
- 新增 IAgent Protocol（统一接口契约）
- 新增 Mixins（StateManagement, Communication, InputValidation）

v2.2 更新：
- 新增 AgentLifecycleState（生命周期状态）
- 新增 batch_structures（批次管理数据结构）
"""
from .base import BaseAgent, AgentState, AgentFactory
from .protocol import IAgent, AgentLike
from .mixins import StateManagementMixin, CommunicationMixin, InputValidationMixin
from .factory import (
    DynamicAgentFactory, 
    AgentCapability,
    GenericAgent,
    get_agent_factory
)
from .agent_session import (
    AgentSession,
    AgentSessionStatus,
    AgentSessionRegistry,
    SessionOrigin,
    generate_session_id,
    create_agent_session,
)
from .result_collector import ResultCollector
from .lifecycle_state import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
    get_valid_transitions,
)
from .batch_structures import (
    BatchStatus,
    BatchCreationResult,
    AgentExecutionRecord,
    BatchExecutionResult,
)

__all__ = [
    # Base Agent
    'BaseAgent', 
    'AgentState', 
    'AgentFactory',
    
    # Protocol
    'IAgent',
    'AgentLike',
    
    # Mixins
    'StateManagementMixin',
    'CommunicationMixin',
    'InputValidationMixin',
    
    # Dynamic Agent Factory
    'DynamicAgentFactory',
    'AgentCapability',
    'GenericAgent',
    'get_agent_factory',
    
    # Agent Session
    'AgentSession',
    'AgentSessionStatus',
    'AgentSessionRegistry',
    'SessionOrigin',
    'generate_session_id',
    'create_agent_session',
    
    # Result Collector
    'ResultCollector',
    
    # Lifecycle State (v2.2)
    'AgentLifecycleState',
    'InvalidStateError',
    'validate_transition',
    'get_valid_transitions',
    
    # Batch Structures (v2.2)
    'BatchStatus',
    'BatchCreationResult',
    'AgentExecutionRecord',
    'BatchExecutionResult',
]
