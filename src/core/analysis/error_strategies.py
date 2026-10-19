from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ErrorStrategy(Enum):
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"


@dataclass
class ErrorHandlingConfig:
    strategy: ErrorStrategy = ErrorStrategy.RETRY
    max_retries: int = 3
    fallback_action: Optional[str] = None


@dataclass
class PhaseError:
    phase: str
    error_type: str
    error_message: str
    details: Dict[str, Any] = field(default_factory=dict)


class ErrorStrategies:
    def __init__(self):
        self._configs = {
            "data_collection": ErrorHandlingConfig(ErrorStrategy.RETRY, 3),
            "data_validation": ErrorHandlingConfig(ErrorStrategy.RETRY, 2),
            "deep_analysis": ErrorHandlingConfig(ErrorStrategy.RETRY, 2),
            "synthesis": ErrorHandlingConfig(ErrorStrategy.RETRY, 2),
            "report_generation": ErrorHandlingConfig(ErrorStrategy.RETRY, 2),
        }
        self._error_history: Dict[str, List[PhaseError]] = {}

    def get_config(self, phase: str) -> ErrorHandlingConfig:
        return self._configs.get(phase, ErrorHandlingConfig())

    def should_retry(self, phase: str, retry_count: int) -> bool:
        config = self.get_config(phase)
        return retry_count < config.max_retries

    def record_error(self, error: PhaseError):
        if error.phase not in self._error_history:
            self._error_history[error.phase] = []
        self._error_history[error.phase].append(error)

    def get_error_history(self, phase: str) -> List[PhaseError]:
        return self._error_history.get(phase, [])
