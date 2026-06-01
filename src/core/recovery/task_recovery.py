# -*- coding: utf-8 -*-
"""
TaskRecoveryManager - Task Recovery Manager

Phase 9: Survey System and Master Control Integration

Responsibilities:
- Recover interrupted tasks
- Process multiple task results in parallel
- Merge early task and survey task results

Design doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/SURVEY_ORCHESTRATOR_INTEGRATION.md
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.survey.models import SurveyTask, SurveyStatus

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Recovery result"""
    parent_task_id: str
    success: bool
    main_task: Optional[Dict[str, Any]] = None
    research_results: Dict[str, Any] = field(default_factory=dict)
    survey_results: Dict[str, Any] = field(default_factory=dict)
    waiting_surveys: List[str] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_task_id": self.parent_task_id,
            "success": self.success,
            "main_task": self.main_task,
            "research_results": self.research_results,
            "survey_results": self.survey_results,
            "waiting_surveys": self.waiting_surveys,
            "error": self.error,
        }


class TaskRecoveryManager:
    """
    Task Recovery Manager
    
    Scenarios:
    - Recover interrupted tasks after system restart
    - Process multiple completed task results in parallel
    - Merge early task and survey task results
    
    Usage example:
        recovery = TaskRecoveryManager(
            persistence=persistence,
            shared_memory=shared_memory,
            task_coordinator=coordinator,
        )
        
        # Recover and merge results
        result = await recovery.recover_and_merge("research_xxx")
        
        # Process results in parallel
        processed = await recovery.process_results_in_parallel(
            result,
            processors={
                "research": process_research_data,
                "survey": analyze_survey_responses,
            }
        )
    """
    
    def __init__(
        self,
        persistence: Any,          # TaskPersistenceManager
        shared_memory: Any,        # SharedMemory
        task_coordinator: Any,     # TaskCoordinator
    ):
        self._persistence = persistence
        self._shared_memory = shared_memory
        self._task_coordinator = task_coordinator
        
        # Statistics
        self._stats = {
            "total_recoveries": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
        }
    
    async def recover_and_merge(
        self,
        parent_task_id: str,
    ) -> RecoveryResult:
        """
        Recover task and merge all results
        
        Process:
        1. Load main task state
        2. Find associated survey tasks
        3. Classify (completed/waiting)
        4. Fetch completed results in parallel
        5. Merge all results
        6. Resume monitoring for waiting tasks
        
        Args:
            parent_task_id: Parent task ID
            
        Returns:
            RecoveryResult: Recovery result
        """
        self._stats["total_recoveries"] += 1
        result = RecoveryResult(parent_task_id=parent_task_id, success=False)
        
        try:
            # 1. Load main task
            main_task = await self._load_main_task(parent_task_id)
            if not main_task:
                result.error = f"Main task {parent_task_id} not found"
                self._stats["failed_recoveries"] += 1
                return result
            
            result.main_task = main_task
            
            # 2. Find associated survey tasks
            survey_tasks = await self._find_child_survey_tasks(parent_task_id)
            
            # 3. Classify
            completed_surveys = []
            waiting_surveys = []
            
            for st in survey_tasks:
                if st.status == SurveyStatus.COMPLETED:
                    completed_surveys.append(st)
                elif st.status in (SurveyStatus.WAITING, SurveyStatus.ACTIVE):
                    waiting_surveys.append(st)
            
            result.waiting_surveys = [st.task_id for st in waiting_surveys]
            
            # 4. Fetch completed survey results in parallel
            if completed_surveys:
                survey_results = await asyncio.gather(
                    *[self._get_survey_result(st.task_id) for st in completed_surveys],
                    return_exceptions=True,
                )
                
                for st, sr in zip(completed_surveys, survey_results):
                    if not isinstance(sr, Exception) and sr:
                        result.survey_results[st.task_id] = sr
            
            # 5. Restore main task early results
            result.research_results = await self._get_research_results(parent_task_id)
            
            # 6. Resume monitoring for waiting tasks (using public methods)
            for st in waiting_surveys:
                try:
                    if hasattr(self._task_coordinator, 'resume_monitoring'):
                        await self._task_coordinator.resume_monitoring(st)
                    else:
                        logger.warning(
                            f"TaskCoordinator does not support resume_monitoring, "
                            f"survey {st.task_id} will not be monitored"
                        )
                except Exception as e:
                    logger.error(f"Failed to resume monitoring for survey {st.task_id}: {e}")
            
            result.success = True
            self._stats["successful_recoveries"] += 1
            
            logger.info(
                f"Recovery complete for {parent_task_id}: "
                f"surveys={len(completed_surveys)}, waiting={len(waiting_surveys)}"
            )
            
        except Exception as e:
            result.error = str(e)
            self._stats["failed_recoveries"] += 1
            logger.error(f"Recovery failed for {parent_task_id}: {e}")
        
        return result
    
    async def process_results_in_parallel(
        self,
        recovery_result: RecoveryResult,
        processors: Dict[str, Callable],
    ) -> Dict[str, Any]:
        """
        Process multiple results in parallel
        
        Args:
            recovery_result: Recovery result
            processors: Processor mapping {"research": func, "survey": func}
            
        Returns:
            Processed result
        """
        async def apply_processor(name: str, processor: Callable, data: Any) -> tuple:
            try:
                result = await processor(data)
                return (name, result, None)
            except Exception as e:
                return (name, None, str(e))
        
        tasks = []
        
        # Process research data
        if "research" in processors and recovery_result.research_results:
            tasks.append(apply_processor(
                "research",
                processors["research"],
                recovery_result.research_results,
            ))
        
        # Process survey data
        if "survey" in processors and recovery_result.survey_results:
            tasks.append(apply_processor(
                "survey",
                processors["survey"],
                recovery_result.survey_results,
            ))
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Integrate results
        processed = {
            "total_processors": len(processors),
            "successful": 0,
            "failed": 0,
            "results": {},
            "errors": {},
        }
        
        for result in results:
            if isinstance(result, Exception):
                processed["failed"] += 1
            else:
                name, data, error = result
                if error:
                    processed["failed"] += 1
                    processed["errors"][name] = error
                else:
                    processed["successful"] += 1
                    processed["results"][name] = data
        
        return processed
    
    async def batch_recover(
        self,
        parent_task_ids: List[str],
    ) -> Dict[str, RecoveryResult]:
        """
        Batch recover multiple tasks
        
        Args:
            parent_task_ids: Parent task ID list
            
        Returns:
            Task ID -> RecoveryResult mapping
        """
        results = await asyncio.gather(
            *[self.recover_and_merge(tid) for tid in parent_task_ids],
            return_exceptions=True,
        )
        
        return {
            tid: result if not isinstance(result, Exception) else RecoveryResult(
                parent_task_id=tid,
                success=False,
                error=str(result),
            )
            for tid, result in zip(parent_task_ids, results)
        }
    
    async def get_all_recoverable_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all recoverable tasks
        
        Returns:
            Recoverable task list
        """
        recoverable = []
        
        # 1. Find all parent tasks with survey subtasks
        if self._persistence:
            all_survey_tasks = await self._persistence.find_survey_tasks_by_status(
                SurveyStatus.WAITING
            )
            
            parent_ids = set()
            for st in all_survey_tasks:
                if st.parent_task_id:
                    parent_ids.add(st.parent_task_id)
            
            for parent_id in parent_ids:
                main_task = await self._load_main_task(parent_id)
                if main_task:
                    recoverable.append({
                        "parent_task_id": parent_id,
                        "topic": main_task.get("topic", "Unknown"),
                        "status": main_task.get("status", "unknown"),
                        "has_waiting_surveys": True,
                    })
        
        return recoverable
    
    # ===== Internal Methods =====
    
    async def _load_main_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load main task"""
        if self._persistence:
            return await self._persistence.load_task(task_id)
        
        # Load from SharedMemory
        if self._shared_memory:
            return await self._shared_memory.read(f"task.{task_id}")
        
        return None
    
    async def _find_child_survey_tasks(self, parent_task_id: str) -> List[SurveyTask]:
        """Find associated survey tasks"""
        if self._persistence:
            return await self._persistence.find_child_survey_tasks(parent_task_id)
        
        # Lookup from TaskManager
        from src.survey.task_manager import get_task_manager
        task_manager = get_task_manager()
        
        all_tasks = await task_manager.store.list_all()
        return [
            st for st in all_tasks
            if st.parent_task_id == parent_task_id
        ]
    
    async def _get_survey_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get survey result"""
        if self._shared_memory:
            return await self._shared_memory.read(f"survey_result.{task_id}")
        
        # Load from TaskManager
        from src.survey.task_manager import get_task_manager
        task_manager = get_task_manager()
        
        task = await task_manager.store.load(task_id)
        if task and task.status == SurveyStatus.COMPLETED:
            return {
                "task_id": task_id,
                "parent_task_id": task.parent_task_id,
                "collected_count": task.collected_count,
                "valid_count": task.valid_count,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
        
        return None
    
    async def _get_research_results(self, task_id: str) -> Dict[str, Any]:
        """Get research results"""
        if self._shared_memory:
            results = {}
            
            # Get outputs from each phase
            phases = [
                "data_collection",
                "data_validation",
                "deep_analysis",
                "synthesis",
                "report_generation",
            ]
            
            for phase in phases:
                key = f"phase_output.{phase}"
                data = await self._shared_memory.read(key)
                if data:
                    results[phase] = data
            
            return results
        
        return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            **self._stats,
            "success_rate": (
                self._stats["successful_recoveries"] / self._stats["total_recoveries"]
                if self._stats["total_recoveries"] > 0 else 0
            ),
        }


# Global singleton
_recovery_manager: Optional[TaskRecoveryManager] = None


def get_recovery_manager() -> TaskRecoveryManager:
    """Get global recovery manager"""
    global _recovery_manager
    if _recovery_manager is None:
        from src.core.communication import SharedMemory
        from src.core.coordination import TaskCoordinator
        
        _recovery_manager = TaskRecoveryManager(
            persistence=None,
            shared_memory=SharedMemory(),
            task_coordinator=TaskCoordinator(
                shared_memory=SharedMemory(),
                message_bus=None,
                persistence=None,
            ),
        )
    return _recovery_manager