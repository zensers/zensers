"""
执行控制机制

包含：
- ConcurrencyManager: 并发管理器
- RetryManager: 重试管理器（集成已有 EnhancedRetryHandler）
- CircuitBreaker: 熔断器（集成已有）
- TimeoutController: 超时控制器
- BackgroundExecutor: 后台执行器
- ResultValidator: 结果验证器

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

from .concurrency import ConcurrencyManager, ConcurrencyConfig
from .retry import RetryManager, RetryConfig, RetryRecord
from .timeout import TimeoutController, TimeoutConfig
from .background import (
    BackgroundExecutor,
    BackgroundTask,
    BackgroundTaskStatus,
    BackgroundExecutorConfig,
)
from .validator import (
    ResultValidator,
    ValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidatorConfig,
)

__all__ = [
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
]
