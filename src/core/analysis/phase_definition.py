from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class AnalysisPhase(Enum):
    DATA_COLLECTION = "data_collection"
    DATA_VALIDATION = "data_validation"
    DEEP_ANALYSIS = "deep_analysis"
    SYNTHESIS = "synthesis"
    REPORT_GENERATION = "report_generation"

    @classmethod
    def get_order(cls):
        return [cls.DATA_COLLECTION, cls.DATA_VALIDATION, cls.DEEP_ANALYSIS, cls.SYNTHESIS, cls.REPORT_GENERATION]

    def get_index(self):
        return self.get_order().index(self)

    def get_previous(self):
        order = self.get_order()
        idx = order.index(self)
        return order[idx - 1] if idx > 0 else None

    def get_next(self):
        order = self.get_order()
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else None


class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class PhaseConfig:
    phase: AnalysisPhase
    timeout_seconds: float = 300.0
    max_retries: int = 3
    parallel_enabled: bool = False
    required_inputs: List[str] = field(default_factory=list)


@dataclass
class StageContext:
    phase: AnalysisPhase
    status: PhaseStatus = PhaseStatus.PENDING
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def mark_started(self):
        self.status = PhaseStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, output_data: Dict[str, Any]):
        self.status = PhaseStatus.COMPLETED
        self.completed_at = datetime.now()
        self.output_data = output_data

    def mark_failed(self, error: str):
        self.status = PhaseStatus.FAILED
        self.error = error

    def mark_skipped(self, reason: str):
        self.status = PhaseStatus.SKIPPED
        self.warnings.append(reason)

    def get_duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


PHASE_DEPENDENCIES = {
    AnalysisPhase.DATA_COLLECTION: [],
    AnalysisPhase.DATA_VALIDATION: [AnalysisPhase.DATA_COLLECTION],
    AnalysisPhase.DEEP_ANALYSIS: [AnalysisPhase.DATA_VALIDATION],
    AnalysisPhase.SYNTHESIS: [AnalysisPhase.DEEP_ANALYSIS],
    AnalysisPhase.REPORT_GENERATION: [AnalysisPhase.SYNTHESIS],
}

PHASE_CONFIGS = {}
