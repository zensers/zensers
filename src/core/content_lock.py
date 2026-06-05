# -*- coding: utf-8 -*-
"""
ContentLockManager - Content Finalization Manager

Manages content dependencies between sections, ensuring comprehensive sections
(summary, conclusion) only execute after main sections are completed.

Core design concepts:
1. Section-level locking (not Agent level)
2. Automatic lock/unlock management based on content dependencies
3. Support for quality threshold unlock conditions
4. Support for timeout and manual unlock

State machine:
LOCKED → PENDING → RUNNING → COMPLETED
         ↑                    ↓
         └────── FAILED ──────┘

Design document: .sisyphus/plans/intelligent_routing_system_design.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import threading

# Import new components
from .dynamic_orchestrator import ExecutionPlan, ContentLockRule

logger = logging.getLogger(__name__)


class SectionState(Enum):
    """
    Section state

    State transitions:
    LOCKED → PENDING → RUNNING → COMPLETED
                      → FAILED → PENDING (retry)
    """
    LOCKED = "locked"           # Locked, waiting for prerequisite sections
    PENDING = "pending"         # Unlocked, waiting for execution
    RUNNING = "running"         # Currently executing
    COMPLETED = "completed"     # Execution completed
    FAILED = "failed"           # Execution failed
    SKIPPED = "skipped"         # Skipped execution


@dataclass
class SectionStatus:
    """
    Section status details

    Records complete status information for a section.
    """
    section_id: str
    state: SectionState = SectionState.LOCKED
    content_locked: bool = True                # Whether content locked
    lock_reason: str = ""                      # Lock reason
    unlock_time: Optional[datetime] = None     # Unlock time
    start_time: Optional[datetime] = None      # Execution start time
    complete_time: Optional[datetime] = None   # Completion time
    quality_score: float = 0.0                 # Quality score (0-100)
    retry_count: int = 0                       # Retry count
    error_message: str = ""                    # Error message
    output_data: Dict[str, Any] = field(default_factory=dict)  # Output data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "state": self.state.value,
            "content_locked": self.content_locked,
            "lock_reason": self.lock_reason,
            "unlock_time": self.unlock_time.isoformat() if self.unlock_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "complete_time": self.complete_time.isoformat() if self.complete_time else None,
            "quality_score": self.quality_score,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }

    @property
    def is_ready(self) -> bool:
        """Whether ready to execute"""
        return self.state == SectionState.PENDING and not self.content_locked

    @property
    def is_completed(self) -> bool:
        """Whether completed"""
        return self.state == SectionState.COMPLETED

    @property
    def duration_seconds(self) -> Optional[float]:
        """Execution duration (seconds)"""
        if self.start_time and self.complete_time:
            return (self.complete_time - self.start_time).total_seconds()
        return None


class ContentLockManager:
    """
    Content Finalization Manager

    Manages content dependencies between sections, ensuring correct execution order.

    Usage example:
        lock_manager = ContentLockManager(execution_plan)

        # Check if section can execute
        can_exec, reason = lock_manager.can_execute("section_1")

        # Mark section as running
        lock_manager.mark_running("section_1")

        # Mark section as completed
        unlocked = lock_manager.mark_completed("section_1", quality_score=85.0)
    """

    def __init__(
        self,
        execution_plan: ExecutionPlan,
        max_retries: int = 3,
        timeout_seconds: int = 3600,  # 1 hour timeout
    ):
        """
        Initialize content lock manager

        Args:
            execution_plan: Execution plan
            max_retries: Maximum retry count
            timeout_seconds: Timeout duration (seconds)
        """
        self._plan = execution_plan
        self._max_retries = max_retries
        self._timeout = timedelta(seconds=timeout_seconds)

        # Section status table
        self._section_statuses: Dict[str, SectionStatus] = {}

        # Lock rules (indexed by target section)
        self._lock_rules: Dict[str, List[ContentLockRule]] = {}

        # Thread lock to prevent race conditions
        self._lock = threading.RLock()

        # Initialize
        self._initialize()

        logger.info(
            f"ContentLockManager initialized: "
            f"{len(self._section_statuses)} sections, "
            f"{sum(len(v) for v in self._lock_rules.values())} lock rules"
        )

    def _initialize(self) -> None:
        """Initialize status table and lock rules"""
        # Initialize all section statuses
        all_section_ids = set()

        # Collect all sections from execution plan
        for phase in self._plan.phases:
            for section_id in phase.section_ids:
                all_section_ids.add(section_id)

        # Also collect from task structure
        for section in self._plan.task_structure.sections:
            all_section_ids.add(section.section_id)

        # Create initial statuses
        for section_id in all_section_ids:
            self._section_statuses[section_id] = SectionStatus(
                section_id=section_id,
                state=SectionState.LOCKED,
                content_locked=True,
                lock_reason="Initialization",
            )

        # Index lock rules
        for rule in self._plan.content_lock_rules:
            if rule.target_section not in self._lock_rules:
                self._lock_rules[rule.target_section] = []
            self._lock_rules[rule.target_section].append(rule)

        # Initial unlock check (sections with no dependencies)
        self._check_initial_unlocks()

    def _check_initial_unlocks(self) -> None:
        """Check and unlock sections with no dependencies"""
        for section_id, status in self._section_statuses.items():
            rules = self._lock_rules.get(section_id, [])
            if not rules:
                # No lock rules, unlock directly
                status.content_locked = False
                status.state = SectionState.PENDING
                status.lock_reason = "No dependencies"
                status.unlock_time = datetime.now()
                logger.debug(f"Section {section_id} unlocked (no dependencies)")

    def can_execute(self, section_id: str) -> Tuple[bool, str]:
        """
        Check if section can execute

        Args:
            section_id: Section ID

        Returns:
            (can_execute, reason): Whether can execute and reason
        """
        status = self._section_statuses.get(section_id)
        if not status:
            return False, f"Section {section_id} not found"

        # Check state
        if status.state == SectionState.RUNNING:
            return False, "Already running"

        if status.state == SectionState.COMPLETED:
            return False, "Already completed"

        if status.state == SectionState.FAILED:
            if status.retry_count >= self._max_retries:
                return False, f"Max retries ({self._max_retries}) exceeded"
            return True, "Retry after failure"

        # Check content lock (read-only check, don't modify state)
        if status.content_locked:
            can_unlock, reason = self._check_unlock_conditions(section_id)
            if not can_unlock:
                return False, reason

        return True, "Ready to execute"

    def try_unlock(self, section_id: str) -> Tuple[bool, str]:
        """
        Explicitly try to unlock section

        This is a public method for actively triggering unlock check.

        Args:
            section_id: Section ID

        Returns:
            (unlocked, reason): Whether unlocked and reason
        """
        status = self._section_statuses.get(section_id)
        if not status:
            return False, f"Section {section_id} not found"

        if not status.content_locked:
            return True, "Already unlocked"

        return self._try_unlock(section_id)

    def _check_unlock_conditions(self, section_id: str) -> Tuple[bool, str]:
        """
        Check unlock conditions (read-only check, don't modify state)

        Args:
            section_id: Section ID

        Returns:
            (can_unlock, reason): Whether can unlock and reason
        """
        rules = self._lock_rules.get(section_id, [])
        if not rules:
            return True, "No lock rules"

        # Check each rule
        for rule in rules:
            for required_id in rule.required_sections:
                required_status = self._section_statuses.get(required_id)

                if not required_status:
                    return False, f"Required section {required_id} not found"

                # Check completion status
                if required_status.state != SectionState.COMPLETED:
                    return False, (
                        f"Required section {required_id} is {required_status.state.value}, "
                        f"not completed"
                    )

                # Check quality threshold
                if rule.lock_type in ("quality_threshold", "both"):
                    threshold_100 = rule.quality_threshold
                    if threshold_100 <= 1.0:
                        threshold_100 = threshold_100 * 100.0
                    if required_status.quality_score < threshold_100:
                        return False, (
                            f"Required section {required_id} quality "
                            f"{required_status.quality_score:.2f} < threshold {threshold_100:.2f}"
                        )

        return True, "All conditions satisfied"

    def _try_unlock(self, section_id: str) -> Tuple[bool, str]:
        """
        Try to unlock section

        Check if all prerequisite sections satisfy unlock conditions.

        Args:
            section_id: Section ID

        Returns:
            (unlocked, reason): Whether unlocked and reason
        """
        rules = self._lock_rules.get(section_id, [])
        if not rules:
            # No lock rules, unlock directly
            return self._unlock_section(section_id, "No lock rules")

        # Check each rule
        for rule in rules:
            for required_id in rule.required_sections:
                required_status = self._section_statuses.get(required_id)

                if not required_status:
                    return False, f"Required section {required_id} not found"

                # Check completion status
                if required_status.state != SectionState.COMPLETED:
                    return False, (
                        f"Required section {required_id} is {required_status.state.value}, "
                        f"not completed"
                    )

                # Check quality threshold
                if rule.lock_type in ("quality_threshold", "both"):
                    threshold_100 = rule.quality_threshold
                    if threshold_100 <= 1.0:
                        threshold_100 = threshold_100 * 100.0
                    if required_status.quality_score < threshold_100:
                        return False, (
                            f"Required section {required_id} quality "
                            f"{required_status.quality_score:.2f} < threshold {threshold_100:.2f}"
                        )

        # All conditions satisfied, unlock
        return self._unlock_section(
            section_id,
            f"All {len(rules)} lock rules satisfied"
        )

    def _unlock_section(self, section_id: str, reason: str) -> Tuple[bool, str]:
        """Unlock section"""
        status = self._section_statuses.get(section_id)
        if not status:
            return False, f"Section {section_id} not found"
        
        status.content_locked = False
        status.state = SectionState.PENDING
        status.lock_reason = reason
        status.unlock_time = datetime.now()
        
        logger.info(f"Section {section_id} unlocked: {reason}")
        return True, reason
    
    def mark_running(self, section_id: str) -> bool:
        """
        Mark section as running

        Args:
            section_id: Section ID

        Returns:
            Whether successfully marked
        """
        status = self._section_statuses.get(section_id)
        if not status:
            return False
        
        if status.state not in (SectionState.PENDING, SectionState.FAILED):
            return False
        
        status.state = SectionState.RUNNING
        status.start_time = datetime.now()
        
        logger.debug(f"Section {section_id} marked as running")
        return True
    
    def mark_completed(
        self,
        section_id: str,
        quality_score: float = 100.0,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Mark section as completed

        Args:
            section_id: Section ID
            quality_score: Quality score (0-100)

        Raises:
            ValueError: If quality_score is not in [0, 100] range
        """
        # Validate quality_score range
        if not 0.0 <= quality_score <= 100.0:
            raise ValueError(f"quality_score must be between 0 and 100, got {quality_score}")
        
        with self._lock:
            status = self._section_statuses.get(section_id)
            if not status:
                return []
            
            status.state = SectionState.COMPLETED
            status.quality_score = quality_score
            status.complete_time = datetime.now()
            if output_data:
                status.output_data = output_data

            # Log completion
            duration_str = ""
            if status.duration_seconds is not None:
                duration_str = f", duration={status.duration_seconds:.1f}s"
            logger.info(
                f"Section {section_id} completed: quality={quality_score:.2f}{duration_str}"
            )

            # Check which sections are unlocked as a result
            unlocked = []
            for target_id in self._lock_rules.keys():
                if target_id == section_id:
                    continue

                target_status = self._section_statuses.get(target_id)
                if target_status and target_status.content_locked:
                    can_exec, reason = self.can_execute(target_id)
                    if can_exec:
                        unlocked.append(target_id)

            return unlocked

    def mark_failed(
        self,
        section_id: str,
        error_message: str = "",
    ) -> bool:
        """
        Mark section as failed

        Args:
            section_id: Section ID
            error_message: Error message

        Returns:
            Whether can retry
        """
        with self._lock:
            status = self._section_statuses.get(section_id)
            if not status:
                return False
            
            status.error_message = error_message
            status.retry_count += 1
            
            can_retry = status.retry_count < self._max_retries

            if can_retry:
                # Check if section is still locked by content dependencies
                if status.content_locked:
                    can_unlock, lock_reason = self._check_unlock_conditions(section_id)
                    if not can_unlock:
                        # Still locked, cannot retry
                        status.state = SectionState.FAILED
                        logger.error(
                            f"Section {section_id} failed and is still locked: {lock_reason}"
                        )
                        return False

                # Can retry: keep PENDING state, allow re-execution
                status.state = SectionState.PENDING
                logger.warning(
                    f"Section {section_id} failed (retry {status.retry_count}/{self._max_retries}): "
                    f"{error_message}"
                )
            else:
                # Cannot retry: set to FAILED state, indicating permanent failure
                status.state = SectionState.FAILED
                logger.error(
                    f"Section {section_id} failed permanently after {self._max_retries} retries: "
                    f"{error_message}"
                )

            return can_retry

    def get_status(self, section_id: str) -> Optional[SectionStatus]:
        """Get section status"""
        return self._section_statuses.get(section_id)

    def get_all_statuses(self) -> Dict[str, SectionStatus]:
        """Get all section statuses"""
        return dict(self._section_statuses)

    def get_ready_sections(self) -> List[str]:
        """Get all sections ready to execute"""
        ready = []
        for section_id, status in self._section_statuses.items():
            can_exec, _ = self.can_execute(section_id)
            if can_exec:
                ready.append(section_id)
        return ready

    def get_blocked_sections(self) -> List[Tuple[str, str]]:
        """Get all blocked sections and reasons"""
        blocked = []
        for section_id, status in self._section_statuses.items():
            if status.content_locked or status.state == SectionState.LOCKED:
                _, reason = self.can_execute(section_id)
                blocked.append((section_id, reason))
        return blocked

    def get_progress(self) -> Dict[str, Any]:
        """
        Get execution progress

        Returns:
            Progress statistics
        """
        total = len(self._section_statuses)
        completed = sum(1 for s in self._section_statuses.values() if s.is_completed)
        running = sum(1 for s in self._section_statuses.values() if s.state == SectionState.RUNNING)
        pending = sum(1 for s in self._section_statuses.values() if s.state == SectionState.PENDING)
        locked = sum(1 for s in self._section_statuses.values() if s.state == SectionState.LOCKED)
        failed = sum(1 for s in self._section_statuses.values() if s.state == SectionState.FAILED)
        
        return {
            "total": total,
            "completed": completed,
            "running": running,
            "pending": pending,
            "locked": locked,
            "failed": failed,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
        }
    
    def force_unlock(self, section_id: str, reason: str = "Manual unlock") -> bool:
        """
        Force unlock section (manual intervention)

        Args:
            section_id: Section ID
            reason: Unlock reason

        Returns:
            Whether successfully unlocked
        """
        status = self._section_statuses.get(section_id)
        if not status:
            return False
        
        unlocked, _ = self._unlock_section(section_id, f"Force unlock: {reason}")
        return unlocked
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "section_statuses": {
                k: v.to_dict() for k, v in self._section_statuses.items()
            },
            "progress": self.get_progress(),
        }

    # === Extended methods (Step 5-7) ===

    def update_dependencies(self, new_order: List[str]) -> None:
        """
        Update dependencies (used during replan)

        Rebuilds section dependency graph as linear order:
        new_order[0] → new_order[1] → new_order[2] → ...

        Args:
            new_order: New execution order (list of section IDs)
        """
        if not new_order:
            logger.warning("[update_dependencies] new_order is empty, skipping")
            return

        with self._lock:
            # Clear existing rules
            self._lock_rules.clear()

            # Rebuild dependencies in new order
            for i in range(1, len(new_order)):
                rule = ContentLockRule(
                    target_section=new_order[i],
                    required_sections=[new_order[i - 1]],
                    lock_type="completion",
                    quality_threshold=0.0,
                )
                self._lock_rules.setdefault(new_order[i], []).append(rule)

            # Reset affected section statuses
            for section_id in new_order:
                status = self._section_statuses.get(section_id)
                if status:
                    # P1-1 fix: Handle RUNNING state sections
                    if status.state == SectionState.RUNNING:
                        logger.warning(
                            f"[update_dependencies] Section {section_id} is RUNNING, "
                            "not resetting state (may cause dependency inconsistency)"
                        )
                    elif status.state in (SectionState.PENDING, SectionState.FAILED, SectionState.SKIPPED):
                        status.content_locked = True
                        status.state = SectionState.LOCKED
                        status.lock_reason = "Dependencies updated"
                    # COMPLETED state remains unchanged (completed sections should not be reset)

                # If section doesn't exist, create new status
                if section_id not in self._section_statuses:
                    self._section_statuses[section_id] = SectionStatus(
                        section_id=section_id,
                        state=SectionState.LOCKED,
                        content_locked=True,
                        lock_reason="Added during replan",
                    )

            # Check if first section can be unlocked
            if new_order:
                first_status = self._section_statuses.get(new_order[0])
                # P2-3 fix: Add comment - only unlock LOCKED state sections
                # COMPLETED/RUNNING states should not be modified
                if first_status and first_status.state == SectionState.LOCKED:
                    first_status.content_locked = False
                    first_status.state = SectionState.PENDING
                    first_status.lock_reason = "First in new order"
                    first_status.unlock_time = datetime.now()

            logger.info(f"[update_dependencies] Dependencies updated: {new_order}")

    def merge_sections(self, new_sections: List[Any]) -> None:
        """
        Merge new sections into execution plan (used during reanalyze)

        Args:
            new_sections: New section list (SectionSpec or dict)
        """
        if not new_sections:
            logger.debug("[merge_sections] No new sections to merge")
            return

        with self._lock:
            merged_count = 0

            for section in new_sections:
                # Support multiple input formats
                if hasattr(section, 'section_id'):
                    section_id = section.section_id
                    content_dependency = getattr(section, 'content_dependency', None) or []
                elif isinstance(section, dict):
                    section_id = section.get("section_id") or section.get("id", "")
                    content_dependency = section.get("content_dependency", [])
                else:
                    logger.warning(f"[merge_sections] Unknown section format: {type(section)}")
                    continue

                if not section_id:
                    logger.warning("[merge_sections] Section has no ID, skipping")
                    continue

                if section_id not in self._section_statuses:
                    # New section, initialize as locked state
                    has_dependency = bool(content_dependency)
                    status = SectionStatus(
                        section_id=section_id,
                        state=SectionState.LOCKED if has_dependency else SectionState.PENDING,
                        content_locked=has_dependency,
                        lock_reason="Merged from reanalyze" if has_dependency else "No dependencies",
                    )
                    if not has_dependency:
                        status.unlock_time = datetime.now()
                    self._section_statuses[section_id] = status

                    # Add dependency rules
                    if content_dependency:
                        rule = ContentLockRule(
                            target_section=section_id,
                            required_sections=list(content_dependency),
                            lock_type="completion",
                            quality_threshold=0.0,
                        )
                        self._lock_rules.setdefault(section_id, []).append(rule)

                    merged_count += 1
                else:
                    logger.debug(f"[merge_sections] Section {section_id} already exists, skipping")

            logger.info(f"[merge_sections] Merged {merged_count} new sections")

    def get_execution_progress(self) -> Dict[str, Any]:
        """
        Get complete execution progress

        Compared to get_progress(), provides more detailed information including:
        - Section lists by state
        - Dependency graph
        - Estimated remaining time

        Returns:
            {
                "total": Total sections,
                "completed": Completed count,
                "running": Running count,
                "locked": Locked count,
                "failed": Failed count,
                "progress_percent": Progress percentage,
                "sections_by_state": {state: [section ID list]},
                "dependency_graph": {section ID: [dependency section IDs]},
                "estimated_remaining_time": Estimated remaining time (seconds),
            }
        """
        with self._lock:
            # Basic statistics
            total = len(self._section_statuses)
            completed = sum(1 for s in self._section_statuses.values() if s.is_completed)
            running = sum(1 for s in self._section_statuses.values() if s.state == SectionState.RUNNING)
            pending = sum(1 for s in self._section_statuses.values() if s.state == SectionState.PENDING)
            locked = sum(1 for s in self._section_statuses.values() if s.state == SectionState.LOCKED)
            failed = sum(1 for s in self._section_statuses.values() if s.state == SectionState.FAILED)
            # P1-3 fix: Add SKIPPED state statistics
            skipped = sum(1 for s in self._section_statuses.values() if s.state == SectionState.SKIPPED)

            # Group by state
            sections_by_state: Dict[str, List[str]] = {
                "completed": [],
                "running": [],
                "pending": [],
                "locked": [],
                "failed": [],
                "skipped": [],  # P1-3 fix: Add skipped key
            }

            for section_id, status in self._section_statuses.items():
                state_key = status.state.value
                if state_key in sections_by_state:
                    sections_by_state[state_key].append(section_id)

            # Dependency graph
            dependency_graph: Dict[str, List[str]] = {}
            for section_id, status in self._section_statuses.items():
                rules = self._lock_rules.get(section_id, [])
                deps = []
                for rule in rules:
                    deps.extend(rule.required_sections)
                if deps:
                    dependency_graph[section_id] = deps

            # Estimate remaining time (based on average duration of completed sections)
            avg_duration = 0.0
            completed_with_duration = [
                s for s in self._section_statuses.values()
                if s.is_completed and s.duration_seconds is not None
            ]
            if completed_with_duration:
                # P2-2 fix: Keep or 0 to ensure type safety
                avg_duration = sum(s.duration_seconds or 0 for s in completed_with_duration) / len(completed_with_duration)
            
            remaining_count = total - completed - skipped
            estimated_remaining_time = avg_duration * remaining_count
            
            return {
                "total": total,
                "completed": completed,
                "running": running,
                "pending": pending,
                "locked": locked,
                "failed": failed,
                "skipped": skipped,  # P1-3 fix: Add skipped field
                "progress_percent": (completed / total * 100) if total > 0 else 0,
                "sections_by_state": sections_by_state,
                "dependency_graph": dependency_graph,
                "estimated_remaining_time": estimated_remaining_time,
                "average_section_duration": avg_duration,
            }


__all__ = [
    "ContentLockManager",
    "SectionState",
    "SectionStatus",
]
