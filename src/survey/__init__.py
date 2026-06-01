"""
Survey System
============

Provides a unified survey backend system，Supports multiple survey methods.

:
- api_tencent: surveyAPI
- api_wenjuanxing: surveyAPI
- ai_simulation: AI
- ai_hybrid: AI+

v2.0 :
- （SurveyTaskStore）
- （SurveyCheckpointStore）
- （third_party | ai_simulation）

:
from src.survey import SurveyClient, SurveyBackend

# Create survey
survey = Survey(title="research", questions=[...])

#
client = SurveyClient(backend_type="api_tencent")

# Distribute survey
result = await client.distribute(survey, config)

#
responses = await client.get_results(survey.id)
"""

from .models import (
    Survey,
    Question,
    QuestionOption,
    QuestionType,
    SurveyResponse,
    Answer,
    SurveyStatus,
    DistributionConfig,
    QuotaConfig,
    SurveyTask,
)
from .backends.base import SurveyBackend
from .backends.factory import BackendFactory
from .task_manager import SurveyTaskManager
from .client import SurveyClient
from .stores import (
    SurveyTaskStore,
    SurveyResponseStore,
    SurveyPersonaStore,
    SurveyCheckpointStore,
)

# --- Engine v2.0 ---
try:
    from .engine import (
        PersonaV2,
        PromptLevel,
        PersonaType,
        PersonaTemplateRegistry,
        PersonaGeneratorV2,
    )
    from .engine.errors import (
        SurveySimulationError,
        LLMConfigurationError,
        LLMTemporaryFailure,
        BudgetExceededError,
    )
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False

    __all__ = [
        #
        "Survey",
        "Question",
        "QuestionOption",
        "QuestionType",
        "SurveyResponse",
        "Answer",
        "SurveyStatus",
        "DistributionConfig",
        "QuotaConfig",
        "SurveyTask",
        #
        "SurveyBackend",
        "BackendFactory",
        #
        "SurveyTaskManager",
        #
        "SurveyClient",
        # （v2.0）
        "SurveyTaskStore",
        "SurveyResponseStore",
        "SurveyPersonaStore",
        "SurveyCheckpointStore",
        # Engine v2.0
        "PersonaV2",
        "PromptLevel",
        "PersonaType",
        "PersonaTemplateRegistry",
        "PersonaGeneratorV2",
        "SurveySimulationError",
        "LLMConfigurationError",
        "LLMTemporaryFailure",
        "BudgetExceededError",
        "HAS_ENGINE",
    ]
