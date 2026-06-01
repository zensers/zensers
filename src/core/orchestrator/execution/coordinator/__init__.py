"""
协调机制模块

包含：
- AgentCoordinator: Agent协调器（核心）
- TaskDispatcher: 任务分发器
- ProgressTracker: 进度追踪器
- HeartbeatMonitor: 心跳监控
- CancelManager: 取消管理器

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_COORDINATION_DESIGN.md
"""

from .agent_coordinator import (
    AgentCoordinator,
    CoordinatorConfig,
    ActiveTask,
)
from .task_dispatcher import (
    TaskDispatcher,
    TaskOptions,
    PreparedTask,
)
from .progress_tracker import (
    ProgressTracker,
    TaskProgress,
)
from .heartbeat_monitor import (
    HeartbeatMonitor,
    HeartbeatConfig,
)
from .cancel_manager import (
    CancelManager,
    CancelReason,
)

__all__ = [
    # 核心协调器
    "AgentCoordinator",
    "CoordinatorConfig",
    "ActiveTask",
    
    # 任务分发
    "TaskDispatcher",
    "TaskOptions",
    "PreparedTask",
    
    # 进度追踪
    "ProgressTracker",
    "TaskProgress",
    
    # 心跳监控
    "HeartbeatMonitor",
    "HeartbeatConfig",
    
    # 取消管理
    "CancelManager",
    "CancelReason",
]
