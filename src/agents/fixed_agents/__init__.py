"""
Fixed Agent Team (Core Team)
========================

Responsible for executing standardized tasks. Agents can be repeatedly optimized with controllable quality.

Includes:
- RequirementAnalysisAgent: Requirement analysis agent, deeply parses user requirements
- ReportGenerationAgent: Report generation agent, integrates content to produce reports
- LayoutDesignAgent: Layout design agent, formats output
- QualityCheckAgent: Quality check agent, reviews output quality
- DataCollectionAgent: Data collection agent, searches and organizes data
- SimulatedResponseAgent: Simulated response agent, makes personas answer surveys
- PersonaGenerationAgent: Persona generation agent, generates virtual respondent profiles
- SurveyOptimizationAgent: Survey optimization agent, analyzes and optimizes questions
- SurveyAnalysisAgent: Survey analysis agent, statistical analysis and report generation
- SurveyIntegrationAgent: Survey integration agent, coordinates complete workflow
- ResultCalibrationAgent: Result calibration agent, calibrates simulation results
- DocumentGenerationAgent: Document generation agent, unified document output (Phase 6)
"""

from .requirement_analysis_agent import RequirementAnalysisAgent
from .report_generation_agent import ReportGenerationAgent
from .layout_design_agent import LayoutDesignAgent
from .quality_check_agent import QualityCheckAgent
from .data_collection_agent import DataCollectionAgent
from .simulated_response_agent import SimulatedResponseAgent
from .persona_generation_agent import PersonaGenerationAgent
from .survey_optimization_agent import SurveyOptimizationAgent
from .survey_analysis_agent import SurveyAnalysisAgent
from .survey_integration_agent import SurveyIntegrationAgent
from .result_calibration_agent import ResultCalibrationAgent

# Phase 6: Unified document generation agent
from .document_generation_agent import DocumentGenerationAgent
from .document_models import (
    DocumentFormat,
    GenerationAction,
    DocumentGenerationRequest,
    DocumentGenerationResult,
    DocumentVersion,
    ValidationError,
)

__all__ = [
    "RequirementAnalysisAgent",
    "ReportGenerationAgent", 
    "LayoutDesignAgent",
    "QualityCheckAgent",
    "DataCollectionAgent",
    "SimulatedResponseAgent",
    "PersonaGenerationAgent",
    "SurveyOptimizationAgent",
    "SurveyAnalysisAgent",
    "SurveyIntegrationAgent",
    "ResultCalibrationAgent",
    # Phase 6
    "DocumentGenerationAgent",
    "DocumentFormat",
    "GenerationAction",
    "DocumentGenerationRequest",
    "DocumentGenerationResult",
    "DocumentVersion",
    "ValidationError",
]
