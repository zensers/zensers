"""数据提供者模块."""

from .base import (
    DataProvider,
    DataError,
    DataErrorType,
    RetryHandler,
    DataCache,
)

from .databus import (
    DataBusV2,
    DataSourceConfig,
    DataSourcePriority,
    DataSourceHealth,
    MultiLevelCache,
    MemoryCacheBackend,
    DiskCacheBackend,
    create_databus_with_defaults,
)

from .sources import (
    AkshareProvider,
    AkshareDataBusAdapter,
)

from .error_handling import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerConfig,
    TokenBucketRateLimiter,
    RateLimitConfig,
    RateLimiterManager,
    EnhancedRetryHandler,
    RetryConfig,
    ResilienceConfig,
    execute_with_resilience,
)

# 兼容别名
DataBus = DataBusV2

__all__ = [
    # Base
    "DataProvider",
    "DataError",
    "DataErrorType",
    "RetryHandler",
    "DataCache",
    # DataBus
    "DataBus",
    "DataBusV2",
    "DataSourceConfig",
    "DataSourcePriority",
    "DataSourceHealth",
    "MultiLevelCache",
    "MemoryCacheBackend",
    "DiskCacheBackend",
    "create_databus_with_defaults",
    # Sources
    "AkshareProvider",
    "AkshareDataBusAdapter",
    # Error Handling (Phase 2)
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerConfig",
    "TokenBucketRateLimiter",
    "RateLimitConfig",
    "RateLimiterManager",
    "EnhancedRetryHandler",
    "RetryConfig",
    "ResilienceConfig",
    "execute_with_resilience",
]
