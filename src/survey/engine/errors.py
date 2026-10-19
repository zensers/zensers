"""Simulation system error type definitions. Fail Fast, Fail Clear."""
from typing import Dict, Optional, List


class SurveySimulationError(Exception):
    """Base exception for survey simulation."""

    def __init__(self, message: str, code: str, detail: Optional[Dict] = None):
        self.code = code
        self.detail = detail or {}
        super().__init__(message)


class LLMConfigurationError(SurveySimulationError):
    """LLM configuration error."""

    def __init__(self, detail: Optional[Dict] = None):
        super().__init__(
            message="LLM configuration unavailable: please check API key and model configuration",
            code="LLM_CONFIG_ERROR", detail=detail)


class LLMTemporaryFailure(SurveySimulationError):
    """LLM temporary failure (retries exhausted)."""

    def __init__(self, attempt: int, max_retries: int, detail: Optional[Dict] = None):
        super().__init__(
            message=f"LLM call failed (attempt {attempt}/{max_retries}), retries exhausted",
            code="LLM_TEMPORARY_FAILURE",
            detail={"attempt": attempt, "max_retries": max_retries, **(detail or {})})


class SimulationQualityError(SurveySimulationError):
    """Simulation quality below threshold."""

    def __init__(self, metric: str, actual: float, threshold: float, detail: Optional[Dict] = None):
        super().__init__(
            message=f"Simulation quality below threshold: {metric}={actual:.2f}, threshold={threshold:.2f}",
            code="SIMULATION_QUALITY_ERROR",
            detail={"metric": metric, "actual": actual, "threshold": threshold, **(detail or {})})


class BudgetExceededError(SurveySimulationError):
    """Budget exceeded."""

    def __init__(self, cost: float, limit: float):
        super().__init__(
            message=f"Task cost ${cost:.2f} exceeds budget limit ${limit:.2f}",
            code="BUDGET_EXCEEDED",
            detail={"cost": cost, "limit": limit})


class CalibrationDataMissingError(SurveySimulationError):
    """Calibration data missing."""

    def __init__(self, missing_datasets: List[str]):
        super().__init__(
            message=f"Calibration data missing: {', '.join(missing_datasets)}. Please download and place them in data/benchmarks/",
            code="CALIBRATION_DATA_MISSING",
            detail={"missing": missing_datasets})


ERROR_MESSAGES = {
    "LLM_CONFIG_ERROR": {"title": "LLM Configuration Error",
                          "message": "LLM service is unavailable. Please check API key and model configuration.",
                          "action": "Go to settings to configure LLM."},
    "LLM_TEMPORARY_FAILURE": {"title": "Service Temporarily Unavailable",
                               "message": "AI simulation service is temporarily unresponsive. Retries exhausted.",
                               "action": "Please try again later."},
    "SIMULATION_QUALITY_ERROR": {"title": "Simulation Quality Below Threshold",
                                  "message": "The simulation fidelity does not meet minimum standards.",
                                  "action": "Increase sample size or change persona template."},
    "BUDGET_EXCEEDED": {"title": "Budget Exceeded",
                         "message": "LLM call cost has exceeded the configured budget limit.",
                         "action": "Adjust budget or reduce sample size."},
    "CALIBRATION_DATA_MISSING": {"title": "Calibration Data Not Ready",
                                  "message": "Calibration mode requires reference datasets.",
                                  "action": "Download calibration data to data/benchmarks/."},
}


def get_error_message(code: str) -> Dict:
    """Get user-facing error message for the given error code."""
    return ERROR_MESSAGES.get(code, {
        "title": "Unknown Error",
        "message": "An unknown error occurred. Check logs for details.",
        "action": "Contact administrator."})
