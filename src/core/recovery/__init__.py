"""
Task Recovery Module

Phase 9: Survey System and Master Control Integration

Core components:
- TaskRecoveryManager: Task recovery manager (crash recovery, result merging)
"""

from .task_recovery import TaskRecoveryManager, RecoveryResult

__all__ = ["TaskRecoveryManager", "RecoveryResult"]