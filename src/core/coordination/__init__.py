"""
任务协调模块

Phase 9: 问卷系统与主控集成

核心组件:
- TaskCoordinator: 任务协调器（非阻塞启动、后台监控）
"""

from .task_coordinator import TaskCoordinator, TaskCoordinatorConfig

__all__ = ["TaskCoordinator", "TaskCoordinatorConfig"]