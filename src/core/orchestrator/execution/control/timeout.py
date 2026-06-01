"""
超时控制器

参考: oh-my-openagent abortWithTimeout
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """超时配置"""
    default_timeout: float = 300.0    # 默认超时（秒）
    agent_timeout: float = 300.0      # 单Agent超时
    stage_timeout: float = 600.0      # 阶段超时
    task_timeout: float = 1800.0      # 整体任务超时


class TimeoutController:
    """
    超时控制器
    
    参考: oh-my-openagent abortWithTimeout
    
    特性：
    - 单Agent超时
    - 阶段超时
    - 整体任务超时
    - 超时回调支持
    
    使用示例:
        controller = TimeoutController(TimeoutConfig())
        
        result = await controller.execute_with_timeout(
            execute_func=lambda: agent.execute(task),
            timeout=300.0,
            on_timeout=lambda: cleanup()
        )
    """
    
    def __init__(self, config: TimeoutConfig):
        self.config = config
        
        # 活跃的超时任务
        self._active_tasks: Dict[str, asyncio.Task] = {}
    
    async def execute_with_timeout(
        self,
        execute_func: Callable[[], Awaitable[Dict[str, Any]]],
        task_id: Optional[str] = None,
        timeout: Optional[float] = None,
        on_timeout: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        带超时的执行
        
        Args:
            execute_func: 执行函数
            task_id: 任务ID（可选）
            timeout: 超时时间（秒），None使用默认值
            on_timeout: 超时回调
            
        Returns:
            执行结果，超时时返回错误字典
        """
        timeout = timeout or self.config.default_timeout
        
        try:
            # 使用asyncio.wait_for实现超时
            result = await asyncio.wait_for(
                execute_func(),
                timeout=timeout
            )
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_id or 'unknown'} timed out after {timeout}s")
            
            # 调用超时回调
            if on_timeout:
                try:
                    await on_timeout()
                except Exception as e:
                    logger.error(f"Timeout callback failed: {e}")
            
            return {
                "success": False,
                "error": f"Timeout after {timeout}s",
                "task_id": task_id,
                "timeout": timeout,
            }
        
        except asyncio.CancelledError:
            logger.info(f"Task {task_id or 'unknown'} was cancelled")
            raise
    
    async def execute_with_deadline(
        self,
        execute_func: Callable[[], Awaitable[Dict[str, Any]]],
        deadline: float,
        task_id: Optional[str] = None,
        on_timeout: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        带截止时间的执行
        
        Args:
            execute_func: 执行函数
            deadline: 截止时间（时间戳，秒）
            task_id: 任务ID
            on_timeout: 超时回调
            
        Returns:
            执行结果
        """
        import time
        remaining = deadline - time.time()
        
        if remaining <= 0:
            logger.warning(f"Task {task_id or 'unknown'} already past deadline")
            return {
                "success": False,
                "error": "Deadline already passed",
                "task_id": task_id,
            }
        
        return await self.execute_with_timeout(
            execute_func=execute_func,
            task_id=task_id,
            timeout=remaining,
            on_timeout=on_timeout,
        )
    
    def get_timeout_for_stage(self, stage: str) -> float:
        """
        获取指定阶段的超时时间
        
        Args:
            stage: 阶段名称（"data_collection", "analysis", "report"）
            
        Returns:
            超时时间（秒）
        """
        stage_timeouts = {
            "data_collection": self.config.agent_timeout,
            "analysis": self.config.agent_timeout,
            "report": self.config.agent_timeout,
            "stage": self.config.stage_timeout,
            "task": self.config.task_timeout,
        }
        return stage_timeouts.get(stage, self.config.default_timeout)
