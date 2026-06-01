# -*- coding: utf-8 -*-
"""
ResearchType - Research Type Enumeration

Phase 11: Composite Intent Support

Defines composable research types for identifying composite nature of user requirements.

Design document: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/COMPOSITE_REQUIREMENT_ORCHESTRATION_ANALYSIS.md
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class ResearchType(Enum):
    """
    Research type (composable)

    Each type represents a class of research task, multiple types can combine to form composite requirements.
    """

    # Basic research types
    INDUSTRY_RESEARCH = "industry_research"          # Industry research
    BRAND_RESEARCH = "brand_research"                # Brand research
    COMPANY_RESEARCH = "company_research"            # Company research
    CONSUMER_RESEARCH = "consumer_research"          # Consumer research
    COMPETITIVE_ANALYSIS = "competitive_analysis"    # Competitive analysis

    # Specialized research types
    MARKET_SIZING = "market_sizing"                  # Market sizing
    POLICY_ANALYSIS = "policy_analysis"              # Policy analysis
    TECHNOLOGY_RESEARCH = "technology_research"      # Technology research

    # Data collection types
    SURVEY = "survey"                                # Survey / Questionnaire
    INTERVIEW = "interview"                          # Interview
    OBSERVATION = "observation"                      # Observation

    # Analysis types
    DATA_ANALYSIS = "data_analysis"                  # Data analysis / statistical analysis
    SWOT_ANALYSIS = "swot_analysis"                  # SWOT analysis
    PESTEL_ANALYSIS = "pestel_analysis"              # PESTEL analysis
    PORTER_ANALYSIS = "porter_analysis"              # Porter's five forces analysis

    @classmethod
    def from_string(cls, value: str) -> Optional["ResearchType"]:
        """Convert from string"""
        try:
            return cls(value.lower())
        except ValueError:
            return None

    def is_primary_research(self) -> bool:
        """Whether it is primary research type (requires data collection)"""
        return self in [
            ResearchType.SURVEY,
            ResearchType.INTERVIEW,
            ResearchType.OBSERVATION,
        ]

    def is_secondary_research(self) -> bool:
        """Whether it is secondary research type (desk research)"""
        return not self.is_primary_research()


@dataclass
class ResearchComposition:
    """
    Research Composition

    Describes the composition and execution mode of a composite research requirement.

    Attributes:
        types: List of research types (deduplicated)
        primary: Primary research type (usually industry research type)
        secondary: Secondary research types (usually survey types)
        sequence: Execution sequence
            - sequential: Sequential execution (survey after industry research)
            - parallel: Parallel execution (simultaneously)
            - conditional: Conditional execution (based on previous results)
        output_mode: Output mode
            - staged: Staged reporting (intermediate report + final report)
            - complete: Complete output (wait for all to complete)
        confidence: Recognition confidence (0.0-1.0)
        detected_keywords: Detected keywords
    """
    
    types: List[ResearchType]
    primary: ResearchType
    secondary: List[ResearchType] = field(default_factory=list)
    sequence: str = "sequential"
    output_mode: str = "staged"
    confidence: float = 0.0
    detected_keywords: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-initialization processing"""
        # Ensure types are deduplicated
        if len(self.types) != len(set(self.types)):
            seen = set()
            unique_types = []
            for t in self.types:
                if t not in seen:
                    seen.add(t)
                    unique_types.append(t)
            self.types = unique_types

        # Ensure primary is not in secondary
        if self.primary in self.secondary:
            self.secondary = [t for t in self.secondary if t != self.primary]

    def is_composite(self) -> bool:
        """Whether it is composite research (multiple types combined)"""
        return len(self.types) > 1

    def is_single(self) -> bool:
        """Whether it is single research type"""
        return len(self.types) == 1

    def requires_survey(self) -> bool:
        """Whether it includes survey"""
        return ResearchType.SURVEY in self.types

    def requires_primary_research(self) -> bool:
        """Whether it requires primary data collection"""
        return any(t.is_primary_research() for t in self.types)

    def is_sync_survey(self, survey_backend: str) -> bool:
        """
        Whether survey is synchronous

        Args:
            survey_backend: Survey backend type

        Returns:
            True if survey can complete synchronously (minute-level)
        """
        if not self.requires_survey():
            return False
        return survey_backend in ["ai_simulation", "mock"]

    def get_execution_phases(self) -> List[str]:
        """
        Get execution phase list

        Returns:
            List of phase IDs
        """
        phases = []

        if self.is_single() and self.primary == ResearchType.SURVEY:
            # Pure survey
            phases = ["survey_design", "survey_execution", "survey_analysis", "report"]
        elif self.requires_survey():
            # Industry research + survey
            phases = [
                "data_collection",
                "analysis",
                "survey_design",
                "survey_execution",
                "survey_analysis",
                "report",
            ]
        else:
            # Pure industry research
            phases = ["data_collection", "analysis", "report"]

        return phases

    def get_workflow_template_id(self) -> str:
        """
        Get corresponding workflow template ID

        Returns:
            Workflow template ID
        """
        if self.is_single():
            if self.primary == ResearchType.SURVEY:
                return "pure_survey"
            else:
                return "pure_research"

        # Composite type
        if ResearchType.SURVEY in self.types:
            if self.primary == ResearchType.INDUSTRY_RESEARCH:
                return "industry_with_survey"
            elif self.primary == ResearchType.BRAND_RESEARCH:
                return "brand_with_survey"
            elif self.primary == ResearchType.COMPANY_RESEARCH:
                return "company_with_survey"
            elif self.primary == ResearchType.CONSUMER_RESEARCH:
                return "consumer_with_survey"

        # Default
        return "default_research"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "types": [t.value for t in self.types],
            "primary": self.primary.value,
            "secondary": [t.value for t in self.secondary],
            "sequence": self.sequence,
            "output_mode": self.output_mode,
            "confidence": self.confidence,
            "detected_keywords": self.detected_keywords,
            "is_composite": self.is_composite(),
            "requires_survey": self.requires_survey(),
            "workflow_template_id": self.get_workflow_template_id(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchComposition":
        """Deserialize from dictionary"""
        types = [ResearchType(t) for t in data.get("types", [])]
        primary = ResearchType(data.get("primary", "industry_research"))
        secondary = [ResearchType(t) for t in data.get("secondary", [])]
        
        return cls(
            types=types,
            primary=primary,
            secondary=secondary,
            sequence=data.get("sequence", "sequential"),
            output_mode=data.get("output_mode", "staged"),
            confidence=data.get("confidence", 0.0),
            detected_keywords=data.get("detected_keywords", []),
        )


# Predefined common compositions
COMMON_COMPOSITIONS: Dict[str, ResearchComposition] = {
    "industry_with_survey": ResearchComposition(
        types=[ResearchType.INDUSTRY_RESEARCH, ResearchType.SURVEY],
        primary=ResearchType.INDUSTRY_RESEARCH,
        secondary=[ResearchType.SURVEY],
        sequence="sequential",
        output_mode="staged",
    ),
    "brand_with_survey": ResearchComposition(
        types=[ResearchType.BRAND_RESEARCH, ResearchType.SURVEY],
        primary=ResearchType.BRAND_RESEARCH,
        secondary=[ResearchType.SURVEY],
        sequence="sequential",
        output_mode="staged",
    ),
    "consumer_with_survey": ResearchComposition(
        types=[ResearchType.CONSUMER_RESEARCH, ResearchType.SURVEY],
        primary=ResearchType.CONSUMER_RESEARCH,
        secondary=[ResearchType.SURVEY],
        sequence="sequential",
        output_mode="staged",
    ),
    "pure_survey": ResearchComposition(
        types=[ResearchType.SURVEY],
        primary=ResearchType.SURVEY,
        secondary=[],
        sequence="sequential",
        output_mode="complete",
    ),
    "pure_research": ResearchComposition(
        types=[ResearchType.INDUSTRY_RESEARCH],
        primary=ResearchType.INDUSTRY_RESEARCH,
        secondary=[],
        sequence="sequential",
        output_mode="complete",
    ),
}


__all__ = [
    "ResearchType",
    "ResearchComposition",
    "COMMON_COMPOSITIONS",
]
