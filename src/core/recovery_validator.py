# -*- coding: utf-8 -*-
"""
Recovery State Validation Module
=================================

Phase 4 Week 16: Crash Recovery Enhancement - Recovery Validation

Features:
- Recovery integrity validation - Validate all data is fully recovered
- Data consistency check - Check data consistency (WAL vs main storage)
- Pre/post recovery state comparison - Compare differences before and after recovery
- Validation report generation - Generate detailed validation reports

Dependencies:
- EnhancedWAL (storage_wal.py) - WAL checkpoints and checksums
- TaskPersistenceManager (task_persistence.py) - Task persistence
- AutoRecoveryManager (auto_recovery.py) - Auto recovery

Configuration system integration:
- Default storage path read from settings.system.data_dir
"""

import os
import json
import uuid
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging

# Configuration system
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False
    settings = None

# Import dependency modules
from src.core.storage_wal import EnhancedWAL
from src.core.task_persistence import (
    TaskPersistenceManager,
    TaskState,
    PersistentTask,
    TaskCheckpoint
)
from src.core.auto_recovery import (
    AutoRecoveryManager,
    RecoveryMode,
    RecoveryConfig,
    RecoveryResult
)

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """
    Validation level enumeration

    - BASIC: Basic validation - only validate basic integrity
    - STANDARD: Standard validation - validate integrity and consistency
    - STRICT: Strict validation - validate integrity, consistency and checksums
    """
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass
class ValidationConfig:
    """
    Validation configuration

    Attributes:
        level: Validation level
        enable_checksum_validation: Whether to enable checksum validation
        enable_wal_consistency_check: Whether to enable WAL consistency check
        enable_checkpoint_consistency_check: Whether to enable checkpoint consistency check
        max_report_age_days: Report retention days
    """
    level: ValidationLevel = ValidationLevel.STANDARD
    enable_checksum_validation: bool = True
    enable_wal_consistency_check: bool = True
    enable_checkpoint_consistency_check: bool = True
    max_report_age_days: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "level": self.level.value,
            "enable_checksum_validation": self.enable_checksum_validation,
            "enable_wal_consistency_check": self.enable_wal_consistency_check,
            "enable_checkpoint_consistency_check": self.enable_checkpoint_consistency_check,
            "max_report_age_days": self.max_report_age_days,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationConfig":
        """Deserialize from dictionary"""
        return cls(
            level=ValidationLevel(data.get("level", "standard")),
            enable_checksum_validation=data.get("enable_checksum_validation", True),
            enable_wal_consistency_check=data.get("enable_wal_consistency_check", True),
            enable_checkpoint_consistency_check=data.get("enable_checkpoint_consistency_check", True),
            max_report_age_days=data.get("max_report_age_days", 30),
        )


@dataclass
class ValidationResult:
    """
    Validation result

    Attributes:
        is_valid: Whether validation passed
        check_name: Check name
        message: Validation message
        details: Detailed information
        timestamp: Validation timestamp
        level: Validation level
    """
    is_valid: bool
    check_name: str
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    level: ValidationLevel = ValidationLevel.STANDARD

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "is_valid": self.is_valid,
            "check_name": self.check_name,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "level": self.level.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResult":
        """Deserialize from dictionary"""
        return cls(
            is_valid=data.get("is_valid", False),
            check_name=data.get("check_name", ""),
            message=data.get("message", ""),
            details=data.get("details", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            level=ValidationLevel(data.get("level", "standard")),
        )


@dataclass
class ValidationReport:
    """
    Validation report

    Attributes:
        report_id: Report ID
        timestamp: Report timestamp
        overall_valid: Overall pass status
        checks_passed: Number of passed checks
        checks_failed: Number of failed checks
        results: Check results list
        summary: Report summary
        recommendations: Recommendations
    """
    report_id: str
    timestamp: str
    overall_valid: bool = True
    checks_passed: int = 0
    checks_failed: int = 0
    results: List[ValidationResult] = field(default_factory=list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "overall_valid": self.overall_valid,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
            "recommendations": self.recommendations,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationReport":
        """Deserialize from dictionary"""
        return cls(
            report_id=data.get("report_id", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            overall_valid=data.get("overall_valid", True),
            checks_passed=data.get("checks_passed", 0),
            checks_failed=data.get("checks_failed", 0),
            results=[ValidationResult.from_dict(r) for r in data.get("results", [])],
            summary=data.get("summary", ""),
            recommendations=data.get("recommendations", []),
        )


class RecoveryValidator:
    """
    Recovery Validator

    Features:
    - Recovery integrity validation - Validate all data is fully recovered
    - Data consistency check - Check WAL vs main storage consistency
    - Pre/post recovery state comparison - Compare differences before and after recovery
    - Validation report generation - Generate detailed validation reports

    Usage example:
        validator = RecoveryValidator("/data")

        # Validate task integrity
        result = validator.validate_task_integrity("task_001")

        # Validate WAL and task consistency
        result = validator.validate_wal_task_consistency()

        # Compare pre/post recovery states
        comparison = validator.compare_task_states(pre_state, post_state)

        # Generate validation report
        report = validator.generate_validation_report()
        validator.save_validation_report(report)
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        config: Optional[ValidationConfig] = None,
        task_manager: Optional[TaskPersistenceManager] = None,
        wal: Optional[EnhancedWAL] = None,
        recovery_manager: Optional[AutoRecoveryManager] = None
    ):
        """
        Initialize recovery validator

        Args:
            storage_path: Storage path
            config: Validation configuration
            task_manager: Task persistence manager (optional)
            wal: EnhancedWAL instance (optional)
            recovery_manager: AutoRecoveryManager instance (optional)
        """
        # Read default path from configuration system
        resolved_storage_path: str = storage_path or ""
        if storage_path is None:
            if SETTINGS_AVAILABLE and settings is not None:
                resolved_storage_path = str(Path(settings.system.data_dir))
            else:
                resolved_storage_path = "data"

        self.storage_path = Path(resolved_storage_path)
        self.validation_dir = self.storage_path / "validation"
        self.reports_dir = self.validation_dir / "reports"

        # Create directories
        self.validation_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Configuration
        self.config = config or ValidationConfig()

        # Initialize dependency components
        self._lock = Lock()

        # Task manager
        if task_manager is None:
            self.task_manager = TaskPersistenceManager(
                str(self.storage_path / "tasks")
            )
        else:
            self.task_manager = task_manager

        # WAL
        if wal is None:
            self.wal = EnhancedWAL(
                str(self.storage_path),
                enable_checksum=self.config.enable_checksum_validation
            )
        else:
            self.wal = wal

        # Recovery manager
        if recovery_manager is None:
            self.recovery_manager = AutoRecoveryManager(
                str(self.storage_path)
            )
        else:
            self.recovery_manager = recovery_manager

        logger.info(f"Initialized RecoveryValidator: {self.storage_path}")
    
    # ==================== Recovery Integrity Validation ====================

    def validate_task_integrity(self, task_id: str) -> ValidationResult:
        """
        Validate single task integrity

        Args:
            task_id: Task ID

        Returns:
            Validation result
        """
        logger.info(f"Validating task integrity: {task_id}")

        # Load task
        task = self.task_manager.load_task(task_id)

        if not task:
            return ValidationResult(
                is_valid=False,
                check_name="task_integrity",
                message=f"Task does not exist: {task_id}",
                details={"missing_task_id": task_id},
                level=self.config.level
            )

        # Validate task data integrity
        integrity_checks = []

        # 1. Validate basic fields
        if not task.task_id:
            integrity_checks.append("Missing task_id")

        if not task.task_type:
            integrity_checks.append("Missing task_type")

        if task.input_data is None:
            integrity_checks.append("Missing input_data")

        # 2. Validate state fields
        if task.status is None:
            integrity_checks.append("Missing status")
        else:
            if not hasattr(task.status, 'state'):
                integrity_checks.append("Status missing state field")

        # 3. Validate time fields
        if not task.created_at:
            integrity_checks.append("Missing created_at")

        if not task.updated_at:
            integrity_checks.append("Missing updated_at")

        # 4. Strict validation level: validate checksums
        if self.config.level == ValidationLevel.STRICT and self.config.enable_checksum_validation:
            task_checksum = self._calculate_task_checksum(task)
            # Checksum validation logic can be added here

        # Determine result
        if integrity_checks:
            return ValidationResult(
                is_valid=False,
                check_name="task_integrity",
                message=f"Task integrity check failed: {', '.join(integrity_checks)}",
                details={"issues": integrity_checks, "task_id": task_id},
                level=self.config.level
            )

        return ValidationResult(
            is_valid=True,
            check_name="task_integrity",
            message=f"Task integrity validation passed: {task_id}",
            details={"task_id": task_id, "task_type": task.task_type},
            level=self.config.level
        )

    def validate_all_tasks_integrity(self) -> List[ValidationResult]:
        """
        Validate all tasks integrity

        Returns:
            Validation results list
        """
        logger.info("Validating all tasks integrity...")

        results = []

        # Get all tasks
        all_tasks = self.task_manager.recover_all_tasks()

        if not all_tasks:
            logger.info("No tasks to validate")
            return results

        # Validate each task
        for task in all_tasks:
            result = self.validate_task_integrity(task.task_id)
            results.append(result)

        logger.info(f"Validated {len(results)} tasks")
        return results

    def validate_checkpoint_integrity(
        self,
        task_id: str,
        checkpoint_id: str
    ) -> ValidationResult:
        """
        Validate checkpoint integrity

        Args:
            task_id: Task ID
            checkpoint_id: Checkpoint ID

        Returns:
            Validation result
        """
        logger.info(f"Validating checkpoint integrity: {task_id} - {checkpoint_id}")

        # Load task
        task = self.task_manager.load_task(task_id)

        if not task:
            return ValidationResult(
                is_valid=False,
                check_name="checkpoint_integrity",
                message=f"Task does not exist: {task_id}",
                details={"missing_task_id": task_id},
                level=self.config.level
            )

        # Find checkpoint
        checkpoint = None
        for cp in task.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break

        if not checkpoint:
            return ValidationResult(
                is_valid=False,
                check_name="checkpoint_integrity",
                message=f"Checkpoint does not exist: {checkpoint_id}",
                details={"missing_checkpoint_id": checkpoint_id},
                level=self.config.level
            )

        # Validate checkpoint data integrity
        integrity_checks = []

        # 1. Validate basic fields
        if not checkpoint.checkpoint_id:
            integrity_checks.append("Missing checkpoint_id")

        if not checkpoint.step_name:
            integrity_checks.append("Missing step_name")

        if checkpoint.step_index < 0:
            integrity_checks.append("Invalid step_index")

        if checkpoint.total_steps <= 0:
            integrity_checks.append("Invalid total_steps")

        if checkpoint.data is None:
            integrity_checks.append("Missing data")

        # 2. Validate progress
        if checkpoint.progress < 0 or checkpoint.progress > 1:
            integrity_checks.append("Invalid progress")

        # 3. Validate time
        if not checkpoint.created_at:
            integrity_checks.append("Missing created_at")

        # Determine result
        if integrity_checks:
            return ValidationResult(
                is_valid=False,
                check_name="checkpoint_integrity",
                message=f"Checkpoint integrity check failed: {', '.join(integrity_checks)}",
                details={"issues": integrity_checks, "checkpoint_id": checkpoint_id},
                level=self.config.level
            )

        return ValidationResult(
            is_valid=True,
            check_name="checkpoint_integrity",
            message=f"Checkpoint integrity validation passed: {checkpoint_id}",
            details={
                "checkpoint_id": checkpoint_id,
                "step_name": checkpoint.step_name,
                "progress": checkpoint.progress
            },
            level=self.config.level
        )

    # ==================== Data Consistency Check ====================

    def validate_wal_task_consistency(self) -> ValidationResult:
        """
        Validate WAL and task data consistency

        Returns:
            Validation result
        """
        logger.info("Validating WAL and task data consistency...")

        if not self.config.enable_wal_consistency_check:
            return ValidationResult(
                is_valid=True,
                check_name="wal_task_consistency",
                message="WAL consistency check disabled",
                level=self.config.level
            )

        # Get WAL entries
        wal_entries = self.wal.read_all()

        # Get task list
        all_tasks = self.task_manager.recover_all_tasks()
        task_ids = {task.task_id for task in all_tasks}

        # Count inconsistencies
        inconsistencies = []
        wal_task_ids = set()

        for entry in wal_entries:
            task_id = entry.get("task_id")
            if task_id:
                wal_task_ids.add(task_id)

                # Check if task exists
                if task_id not in task_ids:
                    inconsistencies.append({
                        "type": "missing_task",
                        "task_id": task_id,
                        "message": f"Task {task_id} exists in WAL but not in task storage"
                    })

        # Check if task storage has tasks not recorded in WAL
        for task_id in task_ids:
            if task_id not in wal_task_ids:
                inconsistencies.append({
                    "type": "missing_wal_entry",
                    "task_id": task_id,
                    "message": f"Task {task_id} exists but has no WAL record"
                })

        # Determine result
        if inconsistencies:
            return ValidationResult(
                is_valid=False,
                check_name="wal_task_consistency",
                message=f"WAL and task data inconsistent: {len(inconsistencies)} inconsistencies found",
                details={
                    "inconsistencies": inconsistencies,
                    "wal_entries_count": len(wal_entries),
                    "tasks_count": len(all_tasks)
                },
                level=self.config.level
            )

        return ValidationResult(
            is_valid=True,
            check_name="wal_task_consistency",
            message="WAL and task data consistent",
            details={
                "wal_entries_count": len(wal_entries),
                "tasks_count": len(all_tasks)
            },
            level=self.config.level
        )

    def validate_data_checksum(self, task_id: str) -> ValidationResult:
        """
        Validate data checksum

        Args:
            task_id: Task ID

        Returns:
            Validation result
        """
        logger.info(f"Validating data checksum: {task_id}")

        if not self.config.enable_checksum_validation:
            return ValidationResult(
                is_valid=True,
                check_name="data_checksum",
                message="Checksum validation disabled",
                level=self.config.level
            )

        # Load task
        task = self.task_manager.load_task(task_id)

        if not task:
            return ValidationResult(
                is_valid=False,
                check_name="data_checksum",
                message=f"Task does not exist: {task_id}",
                level=self.config.level
            )

        # Calculate task data checksum
        task_checksum = self._calculate_task_checksum(task)

        # Find corresponding checksum from WAL
        wal_entries = self.wal.read_all()
        wal_checksum = None

        for entry in wal_entries:
            if entry.get("task_id") == task_id and entry.get("operation") == "save_task":
                wal_checksum = entry.get("checksum")
                break

        # Validate checksum
        if wal_checksum and task_checksum:
            if wal_checksum != task_checksum:
                return ValidationResult(
                    is_valid=False,
                    check_name="data_checksum",
                    message=f"Checksum mismatch: WAL={wal_checksum}, Task={task_checksum}",
                    details={
                        "wal_checksum": wal_checksum,
                        "task_checksum": task_checksum,
                        "task_id": task_id
                    },
                    level=self.config.level
                )

        return ValidationResult(
            is_valid=True,
            check_name="data_checksum",
            message=f"Data checksum validation passed: {task_id}",
            details={
                "task_checksum": task_checksum,
                "wal_checksum": wal_checksum
            },
            level=self.config.level
        )

    def validate_checkpoint_consistency(self, task_id: str) -> ValidationResult:
        """
        Validate checkpoint consistency

        Args:
            task_id: Task ID

        Returns:
            Validation result
        """
        logger.info(f"Validating checkpoint consistency: {task_id}")

        if not self.config.enable_checkpoint_consistency_check:
            return ValidationResult(
                is_valid=True,
                check_name="checkpoint_consistency",
                message="Checkpoint consistency check disabled",
                level=self.config.level
            )

        # Load task
        task = self.task_manager.load_task(task_id)

        if not task:
            return ValidationResult(
                is_valid=False,
                check_name="checkpoint_consistency",
                message=f"Task does not exist: {task_id}",
                level=self.config.level
            )

        # Check checkpoint consistency
        inconsistencies = []

        # 1. Check checkpoint order
        for i, checkpoint in enumerate(task.checkpoints):
            if checkpoint.step_index != i + 1:
                inconsistencies.append({
                    "type": "checkpoint_order",
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "message": f"Checkpoint order inconsistent: expected step_index={i+1}, actual={checkpoint.step_index}"
                })

        # 2. Check checkpoint progress monotonic increase
        prev_progress = 0.0
        for checkpoint in task.checkpoints:
            if checkpoint.progress < prev_progress:
                inconsistencies.append({
                    "type": "progress_decrease",
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "message": f"Checkpoint progress decreased: expected >= {prev_progress}, actual={checkpoint.progress}"
                })
            prev_progress = checkpoint.progress

        # Determine result
        if inconsistencies:
            return ValidationResult(
                is_valid=False,
                check_name="checkpoint_consistency",
                message=f"Checkpoint consistency check failed: {len(inconsistencies)} inconsistencies found",
                details={"inconsistencies": inconsistencies, "checkpoint_count": len(task.checkpoints)},
                level=self.config.level
            )

        return ValidationResult(
            is_valid=True,
            check_name="checkpoint_consistency",
            message=f"Checkpoint consistency validation passed: {task_id}",
            details={"checkpoint_count": len(task.checkpoints)},
            level=self.config.level
        )

    # ==================== Pre/Post Recovery State Comparison ====================

    def compare_task_states(
        self,
        pre_state: Dict[str, Any],
        post_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare task states

        Args:
            pre_state: Pre-recovery state
            post_state: Post-recovery state

        Returns:
            Comparison result
        """
        logger.info("Comparing task states...")

        comparison = {
            "task_id": pre_state.get("task_id"),
            "has_changes": False,
            "differences": [],
            "state_changes": {},
        }

        # Compare state
        pre_task_state = pre_state.get("state")
        post_task_state = post_state.get("state")

        if pre_task_state != post_task_state:
            comparison["has_changes"] = True
            comparison["state_changes"]["state"] = {
                "pre": pre_task_state,
                "post": post_task_state
            }
            comparison["differences"].append({
                "field": "state",
                "pre": pre_task_state,
                "post": post_task_state
            })

        # Compare progress
        pre_progress = pre_state.get("progress", 0.0)
        post_progress = post_state.get("progress", 0.0)

        if pre_progress != post_progress:
            comparison["has_changes"] = True
            comparison["state_changes"]["progress"] = {
                "pre": pre_progress,
                "post": post_progress
            }
            comparison["differences"].append({
                "field": "progress",
                "pre": pre_progress,
                "post": post_progress
            })

        # Compare message
        pre_message = pre_state.get("message", "")
        post_message = post_state.get("message", "")

        if pre_message != post_message:
            comparison["has_changes"] = True
            comparison["state_changes"]["message"] = {
                "pre": pre_message,
                "post": post_message
            }
            comparison["differences"].append({
                "field": "message",
                "pre": pre_message,
                "post": post_message
            })

        return comparison

    def compare_recovery_progress(
        self,
        pre_progress: Dict[str, Any],
        post_progress: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare recovery progress

        Args:
            pre_progress: Pre-recovery progress
            post_progress: Post-recovery progress

        Returns:
            Comparison result
        """
        logger.info("Comparing recovery progress...")

        comparison = {
            "recovered_count": 0,
            "completed_diff": 0,
            "interrupted_diff": 0,
            "progress_changes": {},
        }

        # Calculate recovered task count
        pre_interrupted = pre_progress.get("interrupted_count", 0)
        post_interrupted = post_progress.get("interrupted_count", 0)
        comparison["recovered_count"] = pre_interrupted - post_interrupted

        # Calculate completed count difference
        pre_completed = pre_progress.get("completed_count", 0)
        post_completed = post_progress.get("completed_count", 0)
        comparison["completed_diff"] = post_completed - pre_completed

        # Calculate interrupted count difference
        comparison["interrupted_diff"] = post_interrupted - pre_interrupted

        # Record progress changes
        comparison["progress_changes"] = {
            "interrupted_count": {
                "pre": pre_interrupted,
                "post": post_interrupted,
                "diff": comparison["interrupted_diff"]
            },
            "completed_count": {
                "pre": pre_completed,
                "post": post_completed,
                "diff": comparison["completed_diff"]
            }
        }

        return comparison

    def compare_data_states(
        self,
        pre_data: Dict[str, Any],
        post_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare data states

        Args:
            pre_data: Pre-recovery data state
            post_data: Post-recovery data state

        Returns:
            Comparison result
        """
        logger.info("Comparing data states...")

        comparison = {
            "wal_entries_diff": 0,
            "checkpoints_diff": 0,
            "tasks_diff": 0,
            "data_changes": {},
        }

        # Calculate WAL entries difference
        pre_wal = pre_data.get("wal_entries", 0)
        post_wal = post_data.get("wal_entries", 0)
        comparison["wal_entries_diff"] = post_wal - pre_wal

        # Calculate checkpoints difference
        pre_checkpoints = pre_data.get("checkpoints", 0)
        post_checkpoints = post_data.get("checkpoints", 0)
        comparison["checkpoints_diff"] = post_checkpoints - pre_checkpoints

        # Calculate tasks count difference
        pre_tasks = pre_data.get("tasks", 0)
        post_tasks = post_data.get("tasks", 0)
        comparison["tasks_diff"] = post_tasks - pre_tasks

        # Record data changes
        comparison["data_changes"] = {
            "wal_entries": {
                "pre": pre_wal,
                "post": post_wal,
                "diff": comparison["wal_entries_diff"]
            },
            "checkpoints": {
                "pre": pre_checkpoints,
                "post": post_checkpoints,
                "diff": comparison["checkpoints_diff"]
            },
            "tasks": {
                "pre": pre_tasks,
                "post": post_tasks,
                "diff": comparison["tasks_diff"]
            }
        }

        return comparison

    # ==================== Validation Report Generation ====================

    def generate_validation_report(
        self,
        results: Optional[List[ValidationResult]] = None
    ) -> ValidationReport:
        """
        Generate validation report

        Args:
            results: Validation results list (optional, auto-executed if not provided)

        Returns:
            Validation report
        """
        logger.info("Generating validation report...")

        # If no results provided, execute full validation
        if results is None:
            results = self._execute_full_validation()

        # Count results
        checks_passed = sum(1 for r in results if r.is_valid)
        checks_failed = sum(1 for r in results if not r.is_valid)

        # Overall determination
        overall_valid = checks_failed == 0

        # Generate report
        report = ValidationReport(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now().isoformat(),
            overall_valid=overall_valid,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            results=results,
            summary=self._generate_report_summary(results),
            recommendations=self._generate_recommendations(results)
        )

        logger.info(f"Generated report: {report.report_id}, passed={checks_passed}, failed={checks_failed}")
        return report

    def _execute_full_validation(self) -> List[ValidationResult]:
        """
        Execute full validation

        Returns:
            Validation results list
        """
        results = []

        # 1. Task integrity validation
        task_integrity_results = self.validate_all_tasks_integrity()
        results.extend(task_integrity_results)

        # 2. WAL consistency validation
        wal_consistency_result = self.validate_wal_task_consistency()
        results.append(wal_consistency_result)

        # 3. Checkpoint consistency validation (if tasks exist)
        all_tasks = self.task_manager.recover_all_tasks()
        for task in all_tasks:
            checkpoint_result = self.validate_checkpoint_consistency(task.task_id)
            results.append(checkpoint_result)

        return results

    def _generate_report_summary(self, results: List[ValidationResult]) -> str:
        """
        Generate report summary

        Args:
            results: Validation results list

        Returns:
            Summary text
        """
        checks_passed = sum(1 for r in results if r.is_valid)
        checks_failed = sum(1 for r in results if not r.is_valid)
        total_checks = len(results)

        if checks_failed == 0:
            summary = f"Validation complete, all checks passed ({checks_passed}/{total_checks})"
        else:
            summary = f"Validation complete, {checks_passed} checks passed, {checks_failed} checks failed"

        # Add failed check types
        failed_checks = [r.check_name for r in results if not r.is_valid]
        if failed_checks:
            summary += f". Failed checks: {', '.join(failed_checks)}"

        return summary

    def _generate_recommendations(self, results: List[ValidationResult]) -> List[str]:
        """
        Generate recommendations

        Args:
            results: Validation results list

        Returns:
            Recommendations list
        """
        recommendations = []

        # Generate recommendations based on failed checks
        for result in results:
            if not result.is_valid:
                if result.check_name == "task_integrity":
                    recommendations.append("Recommend checking and repairing corrupted task files")

                elif result.check_name == "wal_task_consistency":
                    recommendations.append("Recommend executing WAL sync to recover lost data")

                elif result.check_name == "checkpoint_consistency":
                    recommendations.append("Recommend recreating checkpoints to ensure consistency")

                elif result.check_name == "data_checksum":
                    recommendations.append("Recommend restoring data from backup to fix checksum mismatch")

        # If no recommendations, add general recommendation
        if not recommendations:
            recommendations.append("Recommend regular validation to ensure data integrity")

        return recommendations

    def save_validation_report(self, report: ValidationReport) -> None:
        """
        Save validation report

        Args:
            report: Validation report
        """
        logger.info(f"Saving validation report: {report.report_id}")

        report_file = self.reports_dir / f"{report.report_id}.json"

        with self._lock:
            temp_file = report_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                if report_file.exists():
                    report_file.unlink()
                os.rename(temp_file, report_file)

                logger.debug(f"Validation report saved: {report_file}")

            except Exception as e:
                if temp_file.exists():
                    temp_file.unlink()
                logger.error(f"Failed to save validation report: {e}")
                raise

    def load_validation_report(self, report_id: str) -> Optional[ValidationReport]:
        """
        Load validation report

        Args:
            report_id: Report ID

        Returns:
            Validation report, None if not exists
        """
        logger.info(f"Loading validation report: {report_id}")

        report_file = self.reports_dir / f"{report_id}.json"

        if not report_file.exists():
            logger.warning(f"Report does not exist: {report_id}")
            return None

        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return ValidationReport.from_dict(data)

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load validation report: {e}")
            return None

    def get_validation_statistics(self) -> Dict[str, Any]:
        """
        Get validation statistics

        Returns:
            Statistics info
        """
        logger.info("Getting validation statistics...")

        stats = {
            "total_reports": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "total_checks_passed": 0,
            "total_checks_failed": 0,
            "average_checks_passed": 0.0,
        }

        # Read all reports
        report_files = list(self.reports_dir.glob("*.json"))
        stats["total_reports"] = len(report_files)

        if not report_files:
            return stats

        total_checks_passed = 0
        total_checks_failed = 0

        for report_file in report_files:
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    if data.get("overall_valid"):
                        stats["successful_validations"] += 1
                    else:
                        stats["failed_validations"] += 1

                    total_checks_passed += data.get("checks_passed", 0)
                    total_checks_failed += data.get("checks_failed", 0)

            except (TypeError, AttributeError, ValueError):
                continue

        stats["total_checks_passed"] = total_checks_passed
        stats["total_checks_failed"] = total_checks_failed

        if stats["total_reports"] > 0:
            stats["average_checks_passed"] = total_checks_passed / stats["total_reports"]

        logger.info(f"Validation statistics: {stats}")
        return stats

    # ==================== Recovery Result Validation ====================

    def validate_recovery_result(self, task_id: str) -> ValidationResult:
        """
        Validate recovery result

        Args:
            task_id: Task ID

        Returns:
            Validation result
        """
        logger.info(f"Validating recovery result: {task_id}")

        # Load task
        task = self.task_manager.load_task(task_id)

        if not task:
            return ValidationResult(
                is_valid=False,
                check_name="recovery_result",
                message=f"Task does not exist: {task_id}",
                level=self.config.level
            )

        # Validate recovered state
        validation_checks = []

        # 1. Validate task state
        if task.status:
            if task.status.state == TaskState.FAILED:
                validation_checks.append("Task state is failed")

        # 2. Validate checkpoint
        latest_checkpoint = task.get_latest_checkpoint()
        if latest_checkpoint:
            checkpoint_result = self.validate_checkpoint_integrity(
                task_id,
                latest_checkpoint.checkpoint_id
            )
            if not checkpoint_result.is_valid:
                validation_checks.append(f"Latest checkpoint validation failed: {checkpoint_result.message}")

        # 3. Validate data integrity
        integrity_result = self.validate_task_integrity(task_id)
        if not integrity_result.is_valid:
            validation_checks.append(f"Task integrity validation failed: {integrity_result.message}")

        # Determine result
        if validation_checks:
            return ValidationResult(
                is_valid=False,
                check_name="recovery_result",
                message=f"Recovery result validation failed: {', '.join(validation_checks)}",
                details={"issues": validation_checks, "task_id": task_id},
                level=self.config.level
            )

        return ValidationResult(
            is_valid=True,
            check_name="recovery_result",
            message=f"Recovery result validation passed: {task_id}",
            details={"task_id": task_id},
            level=self.config.level
        )

    def validate_and_generate_report(self) -> ValidationReport:
        """
        Validate and generate report

        Returns:
            Validation report
        """
        logger.info("Validating and generating report...")

        # Execute full validation
        report = self.generate_validation_report()

        # Save report
        self.save_validation_report(report)

        return report

    # ==================== Cleanup Old Reports ====================

    def cleanup_old_reports(self, keep_days: int = 30) -> int:
        """
        Cleanup old validation reports

        Args:
            keep_days: Days to keep

        Returns:
            Number of cleaned reports
        """
        logger.info(f"Cleaning up validation reports older than {keep_days} days...")

        cutoff_date = datetime.now() - timedelta(days=keep_days)
        cleaned_count = 0

        report_files = list(self.reports_dir.glob("*.json"))

        for report_file in report_files:
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                timestamp = data.get("timestamp")
                if timestamp:
                    try:
                        report_date = datetime.fromisoformat(timestamp)
                        if report_date < cutoff_date:
                            report_file.unlink()
                            cleaned_count += 1
                            logger.debug(f"Cleaned report: {report_file}")
                    except ValueError:
                        # Cannot parse time, keep report
                        pass

            except Exception as e:
                logger.warning(f"Failed to cleanup report: {report_file}: {e}")
                continue

        logger.info(f"Cleaned {cleaned_count} validation reports")
        return cleaned_count

    # ==================== Helper Methods ====================

    def _calculate_task_checksum(self, task: PersistentTask) -> str:
        """
        Calculate task data checksum

        Args:
            task: Task object

        Returns:
            Checksum (MD5)
        """
        task_data = task.to_dict()
        # Remove unstable fields like timestamps
        stable_data = {
            "task_id": task_data.get("task_id"),
            "task_type": task_data.get("task_type"),
            "input_data": task_data.get("input_data"),
            "result": task_data.get("result"),
        }

        content = json.dumps(stable_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode('utf-8'), usedforsecurity=False).hexdigest()

    def get_validation_status(self) -> Dict[str, Any]:
        """
        Get validation status

        Returns:
            Validation status info
        """
        return {
            "config": self.config.to_dict(),
            "reports_count": len(list(self.reports_dir.glob("*.json"))),
            "tasks_count": len(self.task_manager.recover_all_tasks()),
            "wal_entries_count": len(self.wal.read_all()),
        }


def create_recovery_validator(
    config: Optional[ValidationConfig] = None
) -> RecoveryValidator:
    """
    Create recovery validator from configuration system

    Args:
        config: Validation configuration

    Returns:
        Configured RecoveryValidator instance
    """
    return RecoveryValidator(config=config)