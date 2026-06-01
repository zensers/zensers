"""LLM call cost monitoring with budget limit checks."""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

from .errors import BudgetExceededError

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    """Single LLM call record."""
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    phase: str = ""
    timestamp: str = ""


class LLMCostTracker:
    """LLM call cost tracker with budget limits."""

    PRICING = {
        "gpt-4o": {"input": 5.00 / 1e6, "output": 15.00 / 1e6},
        "gpt-4o-mini": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
        "gpt-4-turbo": {"input": 10.00 / 1e6, "output": 30.00 / 1e6},
        "gpt-3.5-turbo": {"input": 0.50 / 1e6, "output": 1.50 / 1e6},
        "claude-3.5-sonnet": {"input": 3.00 / 1e6, "output": 15.00 / 1e6},
        "deepseek-v4-pro": {"input": 0.14 / 1e6, "output": 0.28 / 1e6},
    }

    def __init__(self, task_id: str, budget_limit: float = 5.0):
        self.task_id = task_id
        self.budget_limit = budget_limit
        self.calls: List[LLMCallRecord] = []

    def record_call(self, model: str, input_tokens: int, output_tokens: int, phase: str = "") -> float:
        """Record an LLM call and return the cost."""
        pricing = self.PRICING.get(model, self.PRICING["gpt-4o-mini"])
        cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
        self.calls.append(LLMCallRecord(model=model, input_tokens=input_tokens,
                                         output_tokens=output_tokens, cost=cost,
                                         phase=phase, timestamp=datetime.now().isoformat()))
        if self.total_cost > self.budget_limit:
            logger.warning(f"Task {self.task_id} cost ${self.total_cost:.2f} exceeds limit ${self.budget_limit:.2f}")
            raise BudgetExceededError(cost=self.total_cost, limit=self.budget_limit)
        return cost

    @property
    def total_cost(self) -> float:
        return sum(c.cost for c in self.calls)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    def get_report(self) -> Dict:
        by_model = {}
        by_phase = {}
        for c in self.calls:
            by_model[c.model] = by_model.get(c.model, 0) + 1
            by_phase[c.phase] = by_phase.get(c.phase, 0) + c.cost
        return {"task_id": self.task_id, "total_calls": self.total_calls,
                "total_cost": round(self.total_cost, 4),
                "budget_limit": self.budget_limit,
                "budget_remaining": round(self.budget_limit - self.total_cost, 4),
                "by_model": {k: {"calls": v} for k, v in by_model.items()},
                "by_phase": {k: round(v, 4) for k, v in by_phase.items()}}


class RetryHandler:
    """LLM call retry handler with exponential backoff."""

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0
    BACKOFF_MULTIPLIER = 2.0
    MAX_BACKOFF = 30.0
    TIMEOUT = 30.0
    RETRYABLE_ERROR_NAMES = frozenset({
        "TimeoutError", "RateLimitError", "ConnectionError",
        "ServiceUnavailableError", "asyncio.TimeoutError"})

    @classmethod
    def should_retry(cls, error: Exception) -> bool:
        return type(error).__name__ in cls.RETRYABLE_ERROR_NAMES

    @classmethod
    def get_backoff(cls, attempt: int) -> float:
        return min(cls.BACKOFF_BASE * (cls.BACKOFF_MULTIPLIER ** (attempt - 1)), cls.MAX_BACKOFF)
