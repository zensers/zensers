# -*- coding: utf-8 -*-
"""
SubIntent & ReadinessLevel - Shared data classes for dialogue intent tracking.

ReadinessLevel is placed here (not in dialogue_intent_state.py) to avoid
state_machine.py (low-level infrastructure) importing from a higher-level
business module, which would create an architectural inversion.
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum


class ReadinessLevel(Enum):
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"


@dataclass
class SubIntent:
    intent_id: str
    description: str
    aspects: List[str] = field(default_factory=list)
    research_types: List[str] = field(default_factory=list)
    dependency: str = "none"