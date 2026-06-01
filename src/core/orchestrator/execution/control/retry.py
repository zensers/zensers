"""
重试管理器

参考: oh-my-openagent FallbackRetry
集成已有的 EnhancedRetryHandler
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3              # 最大重试次数
    base_delay: float = 1.0           # 基础延迟（秒）
    max_delay: float = 60.0           # 最大延迟（秒）
    jitter: bool = True               # 是否添加抖动
    
    # 可重试的错误模式
    retryable_errors: List[str] = field(default_factory=lambda: [
        "rate_limit",
        "timeout",
        "unavailable",
        "connection_error",
        "quota_exceeded",
        "temporarily_unavailable",
        "service_unavailable",
        "too_many_requests",
        "429",
        "503",
        "502",
    ])
    
    # 不可重试的错误模式
    stop_errors: List[str] = field(default_factory=lambda: [
        "billing_limit",
        "invalid_request",
        "auth_error",
        "permission_denied",
        "not_found",
        "bad_request",
        "400",
        "401",
        "403",
        "404",
    ])


@dataclass
class RetryRecord:
    """重试记录"""
    attempt: int
    error: str
    timestamp: datetime = field(default_factory=datetime.now)
    delay: float = 0.0


class RetryManager:
    """
    重试管理器
    
    参考: oh-my-openagent FallbackRetry
    
    特性：
    - 错误分类（可重试/不可重试）
    - 指数退避
    - 降级链支持
    - 重试历史记录
    
    使用示例:
        manager = RetryManager(RetryConfig(max_retries=3))
        
        result = await manager.execute_with_retry(
            agent=agent,
            task=task,
            fallback_chain=[{"model": "gpt-4"}, {"model": "gpt-3.5"}]
        )
    """
    
    def __init__(self, config: RetryConfig):
        self.config = config
        
        # 重试计数
        self._retry_counts: Dict[str, int] = {}
        
        # 重试历史
        self._retry_history: Dict[str, List[RetryRecord]] = {}
    
    def should_retry(self, error: str) -> bool:
        """
        判断错误是否可重试
        
        Args:
            error: 错误信息
            
        Returns:
            是否可重试
        """
        error_lower = error.lower()
        
        # 先检查是否是不可重试的错误
        for stop_pattern in self.config.stop_errors:
            if stop_pattern.lower() in error_lower:
                return False
        
        # 检查是否是可重试的错误
        for retry_pattern in self.config.retryable_errors:
            if retry_pattern.lower() in error_lower:
                return True
        
        return False
    
    async def execute_with_retry(
        self,
        execute_func: Callable[[], Awaitable[Dict[str, Any]]],
        task_id: str,
        fallback_chain: Optional[List[Dict]] = None,
        on_fallback: Optional[Callable[[Dict], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        带重试的执行
        
        Args:
            execute_func: 执行函数
            task_id: 任务ID（用于追踪重试）
            fallback_chain: 降级链（如模型降级）
            on_fallback: 降级回调
            
        Returns:
            执行结果
        """
        chain = fallback_chain or []
        attempt = 0
        max_attempts = self.config.max_retries + len(chain) + 1
        
        # 初始化重试历史
        self._retry_history[task_id] = []
        
        while attempt < max_attempts:
            try:
                # 执行
                result = await execute_func()
                
                # 检查结果
                if result.get("success"):
                    # 成功，清理重试计数
                    self._retry_counts.pop(task_id, None)
                    return result
                
                # 结果标记为失败，检查是否可重试
                error = result.get("error", "")
                if not self.should_retry(error):
                    logger.info(f"Task {task_id} failed with non-retryable error: {error}")
                    return result
                
                # 记录失败
                logger.warning(f"Task {task_id} failed (attempt {attempt + 1}): {error}")
                
            except Exception as e:
                error = str(e)
                
                # 检查是否可重试
                if not self.should_retry(error):
                    logger.error(f"Task {task_id} raised non-retryable exception: {error}")
                    raise
                
                logger.warning(f"Task {task_id} raised exception (attempt {attempt + 1}): {error}")
            
            # 记录重试
            attempt += 1
            self._retry_counts[task_id] = attempt
            
            # 计算延迟
            delay = self._get_delay(attempt)
            
            # 记录重试历史
            self._retry_history[task_id].append(RetryRecord(
                attempt=attempt,
                error=error,
                delay=delay,
            ))
            
            # 应用降级
            if attempt <= len(chain) and on_fallback:
                fallback_config = chain[attempt - 1]
                logger.info(f"Task {task_id} applying fallback: {fallback_config}")
                await on_fallback(fallback_config)
            
            # 等待后重试
            logger.info(f"Task {task_id} retrying in {delay:.1f}s (attempt {attempt})")
            await asyncio.sleep(delay)
        
        # 所有重试都失败
        logger.error(f"Task {task_id} exhausted all retries")
        return {
            "success": False,
            "error": f"All {max_attempts} attempts exhausted",
            "retry_count": attempt,
        }
    
    def _get_delay(self, attempt: int) -> float:
        """
        计算重试延迟（指数退避）
        
        Args:
            attempt: 当前尝试次数
            
        Returns:
            延迟时间（秒）
        """
        import random
        
        # 指数退避
        delay = self.config.base_delay * (2 ** (attempt - 1))
        delay = min(delay, self.config.max_delay)
        
        # 添加抖动
        if self.config.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay
    
    def get_retry_count(self, task_id: str) -> int:
        """获取任务的重试次数"""
        return self._retry_counts.get(task_id, 0)
    
    def get_retry_history(self, task_id: str) -> List[RetryRecord]:
        """获取任务的重试历史"""
        return self._retry_history.get(task_id, [])
    
    def clear_task(self, task_id: str) -> None:
        """清理任务的重试记录"""
        self._retry_counts.pop(task_id, None)
        self._retry_history.pop(task_id, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_retries": len(self._retry_counts),
            "retry_counts": dict(self._retry_counts),
            "total_tracked": len(self._retry_history),
        }
