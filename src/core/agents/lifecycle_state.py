"""
Agent生命周期状态定义

定义Agent从创建到终止的完整生命周期状态机。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
"""
from enum import Enum
from typing import Dict, List


class AgentLifecycleState(Enum):
    """
    Agent生命周期状态
    
    状态流转：
    CREATED → INITIALIZING → READY → RUNNING → COMPLETED/FAILED
                ↓              ↓
            HIBERNATING → HIBERNATED → RESUMING → READY
                                        ↓
                                    TERMINATED
    """
    
    # 创建阶段
    CREATED = "created"           # 已创建，未初始化
    INITIALIZING = "initializing" # 初始化中（加载Skills）
    READY = "ready"               # 就绪，等待执行
    
    # 执行阶段
    RUNNING = "running"           # 执行中
    PAUSED = "paused"             # 已暂停
    
    # 完成阶段
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 执行失败
    
    # 休眠阶段
    HIBERNATING = "hibernating"   # 休眠中（释放资源）
    HIBERNATED = "hibernated"     # 已休眠（仅保留Session）
    
    # 恢复阶段
    RESUMING = "resuming"         # 恢复中（从休眠恢复）
    
    # 终止阶段
    TERMINATED = "terminated"     # 已终止（资源完全释放）


# 合法状态转换映射
VALID_TRANSITIONS: Dict[AgentLifecycleState, List[AgentLifecycleState]] = {
    AgentLifecycleState.CREATED: [
        AgentLifecycleState.INITIALIZING,
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.INITIALIZING: [
        AgentLifecycleState.READY,
        AgentLifecycleState.FAILED,
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.READY: [
        AgentLifecycleState.RUNNING,
        AgentLifecycleState.HIBERNATING,
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.RUNNING: [
        AgentLifecycleState.COMPLETED,
        AgentLifecycleState.FAILED,
        AgentLifecycleState.PAUSED,
        AgentLifecycleState.HIBERNATING,
    ],
    AgentLifecycleState.PAUSED: [
        AgentLifecycleState.RUNNING,
        AgentLifecycleState.HIBERNATING,
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.HIBERNATING: [
        AgentLifecycleState.HIBERNATED,
        AgentLifecycleState.FAILED,
    ],
    AgentLifecycleState.HIBERNATED: [
        AgentLifecycleState.RESUMING,
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.RESUMING: [
        AgentLifecycleState.READY,
        AgentLifecycleState.FAILED,
    ],
    AgentLifecycleState.COMPLETED: [
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.FAILED: [
        AgentLifecycleState.TERMINATED,
    ],
    AgentLifecycleState.TERMINATED: [],  # 终态，无转换
}


class InvalidStateError(Exception):
    """
    非法状态转换异常
    
    当尝试进行不合法的状态转换时抛出。
    """
    
    def __init__(
        self, 
        current_state: AgentLifecycleState, 
        target_state: AgentLifecycleState,
        message: str = ""
    ):
        self.current_state = current_state
        self.target_state = target_state
        
        if not message:
            valid_targets = VALID_TRANSITIONS.get(current_state, [])
            message = (
                f"Invalid state transition: {current_state.value} → {target_state.value}. "
                f"Valid transitions: {[s.value for s in valid_targets]}"
            )
        
        super().__init__(message)


def validate_transition(
    current: AgentLifecycleState, 
    target: AgentLifecycleState
) -> bool:
    """
    验证状态转换是否合法
    
    Args:
        current: 当前状态
        target: 目标状态
        
    Returns:
        是否为合法转换
    """
    valid_targets = VALID_TRANSITIONS.get(current, [])
    return target in valid_targets


def get_valid_transitions(state: AgentLifecycleState) -> List[AgentLifecycleState]:
    """
    获取某状态的所有合法转换
    
    Args:
        state: 当前状态
        
    Returns:
        可转换到的状态列表
    """
    return VALID_TRANSITIONS.get(state, [])