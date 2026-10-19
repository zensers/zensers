"""
ResearchTask — structured research task representation (R-FIX-1)

Replaces flat AgentSpec routing with question-driven task decomposition.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ResearchSubQuestion:
    """A sub-question within a research task."""
    question: str
    evidence_type: str  # financial_metrics / causal_analysis / forecast
    produces: List[str] = field(default_factory=list)
    consumes: List[str] = field(default_factory=list)
    section_role: str = ""
    section_id: str = ""


@dataclass
class ResearchTask:
    """Complete research task with core question and sub-questions."""
    core_question: str
    sub_questions: List[ResearchSubQuestion] = field(default_factory=list)
    cross_validation_rules: List[str] = field(default_factory=list)
    data_caliber_decisions: List[Dict] = field(default_factory=list)
