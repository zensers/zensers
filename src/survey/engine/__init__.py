"""
Persona Simulation Engine

Provides AI-driven virtual respondent generation, simulation, and management capabilities.
"""

from .persona_models import PersonaV2, PromptLevel, PersonaType
from .persona_templates import PersonaTemplateRegistry
from .persona_generator import PersonaGeneratorV2, sanitize_context
from .data import RegionData, load_region, list_regions, reload_all
from .prompt_builder import SimulationPromptBuilder, TemperatureScheduler, PromptResult
from .simulation_engine import SimulationExecutor
from .cost_monitor import LLMCostTracker, RetryHandler
from .alignment_engine import DistributionAligner
from .calibrator import SimulationCalibrator, CalibrationReport
from .errors import (
    SurveySimulationError,
    LLMConfigurationError,
    LLMTemporaryFailure,
    SimulationQualityError,
    BudgetExceededError,
    CalibrationDataMissingError,
    get_error_message,
)

__all__ = [
    # Data models
    "PersonaV2",
    "PromptLevel",
    "PersonaType",
    # Templates
    "PersonaTemplateRegistry",
    # Generator
    "PersonaGeneratorV2",
    "sanitize_context",
    # Region data
    "RegionData",
    "load_region",
    "list_regions",
    "reload_all",
    # Prompt building
    "SimulationPromptBuilder",
    "TemperatureScheduler",
    "PromptResult",
    # Engine
    "SimulationExecutor",
    # Cost
    "LLMCostTracker",
    "RetryHandler",
    # Distribution alignment
    "DistributionAligner",
    # Calibration
    "SimulationCalibrator",
    "CalibrationReport",
    # Errors
    "SurveySimulationError",
    "LLMConfigurationError",
    "LLMTemporaryFailure",
    "SimulationQualityError",
    "BudgetExceededError",
    "CalibrationDataMissingError",
    "get_error_message",
]
