from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class RevisionComplexity(Enum):
    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    COMPLEX = "complex"
    FULL = "full"


@dataclass
class RevisionTarget:
    chapter_id: str
    chapter_title: str
    revision_type: str
    revision_description: str
    data_patches: List[str] = field(default_factory=list)


@dataclass
class RevisionLocation:
    complexity: RevisionComplexity = RevisionComplexity.STANDARD
    targets: List[RevisionTarget] = field(default_factory=list)
    data_gaps: List[Dict[str, Any]] = field(default_factory=list)
    data_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    preceding_summary: str = ""


@dataclass
class ChapterRewriteResult:
    chapter_id: str
    original_content: str
    revised_content: str
    review_passed: bool
    review_score: float
    data_points_changed: List[Dict[str, Any]] = field(default_factory=list)
    data_points_added: List[Dict[str, Any]] = field(default_factory=list)
    data_points_removed: List[Dict[str, Any]] = field(default_factory=list)
    rewrite_rounds: int = 1
