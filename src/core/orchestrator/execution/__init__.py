"""
执行层模块

包含：
- ExecutionEngine: 执行引擎（核心）
- control/: 控制机制
- coordinator/: 协调机制

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

from .engine import (
    ExecutionEngine,
    ExecutionConfig,
    ExecutionResult,
    ExecutionStage,
    AgentCategory,
)

from .control import (
    # 并发控制
    ConcurrencyManager,
    ConcurrencyConfig,
    
    # 重试管理
    RetryManager,
    RetryConfig,
    RetryRecord,
    
    # 超时控制
    TimeoutController,
    TimeoutConfig,
    
    # 后台执行
    BackgroundExecutor,
    BackgroundTask,
    BackgroundTaskStatus,
    BackgroundExecutorConfig,
    
    # 结果验证
    ResultValidator,
    ValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidatorConfig,
)

from .coordinator import (
    # 核心协调器
    AgentCoordinator,
    CoordinatorConfig,
    ActiveTask,
    
    # 任务分发
    TaskDispatcher,
    TaskOptions,
    PreparedTask,
    
    # 进度追踪
    ProgressTracker,
    TaskProgress,
    
    # 心跳监控
    HeartbeatMonitor,
    HeartbeatConfig,
    
    # 取消管理
    CancelManager,
    CancelReason,
)

__all__ = [
    # 执行引擎
    "ExecutionEngine",
    "ExecutionConfig",
    "ExecutionResult",
    "ExecutionStage",
    "AgentCategory",
    
    # 并发控制
    "ConcurrencyManager",
    "ConcurrencyConfig",
    
    # 重试管理
    "RetryManager",
    "RetryConfig",
    "RetryRecord",
    
    # 超时控制
    "TimeoutController",
    "TimeoutConfig",
    
    # 后台执行
    "BackgroundExecutor",
    "BackgroundTask",
    "BackgroundTaskStatus",
    "BackgroundExecutorConfig",
    
    # 结果验证
    "ResultValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationLevel",
    "ValidatorConfig",
    
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
