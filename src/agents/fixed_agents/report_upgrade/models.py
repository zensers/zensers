from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class DataPoint:
    metric: str
    value: str
    unit: str
    source: str
    chapter_id: str = ""
    confidence: float = 1.0


@dataclass
class MetricEntry:
    metric: str
    value: str
    unit: str
    canonical_chapter: str
    source: str
    conflicts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ChapterWriteInput:
    framework_config: Dict[str, Any]
    task_structure: Dict[str, Any]
    chapter_spec: Dict[str, Any]
    chapter_data: Dict[str, Any]
    raw_data_summary: str = ""
    preceding_summary: str = ""
    used_metrics_summary: str = ""
    base_content: str = ""
    upstream_data_points: List[Dict[str, Any]] = None


@dataclass
class ChapterWriteOutput:
    chapter_id: str
    title: str
    content: str
    data_points_used: List[DataPoint] = field(default_factory=list)
    key_conclusions: List[str] = field(default_factory=list)
    self_check_passed: bool = True
    self_check_issues: List[str] = field(default_factory=list)


@dataclass
class ChapterReviewInput:
    framework_config: Dict[str, Any]
    chapter_spec: Dict[str, Any]
    chapter_content: str
    preceding_summary: str
    used_metrics_summary: str
    topic: str = ""
    writer_self_check_issues: List[str] = field(default_factory=list)
    chapter_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterIssue:
    category: str
    severity: str
    location: str
    description: str
    suggestion: str


@dataclass
class ChapterReviewOutput:
    passed: bool
    score: float
    issues: List[ChapterIssue] = field(default_factory=list)


@dataclass
class ReviewInput:
    framework_config: Dict[str, Any]
    report_summary: str
    conflicts_summary: str


@dataclass
class ReviewIssue:
    dimension: str
    severity: str
    description: str
    location: str
    evidence: str


@dataclass
class FixSuggestion:
    target_chapter: str
    issue_id: str
    fix_type: str
    fix_instruction: str
    priority: str


@dataclass
class ReviewOutput:
    overall_score: float
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[ReviewIssue] = field(default_factory=list)
    fix_suggestions: List[FixSuggestion] = field(default_factory=list)


@dataclass
class DataGap:
    chapter_id: str
    metric: str
    context: str
    search_keywords: List[str] = field(default_factory=list)


@dataclass
class DataRepairResult:
    gap: DataGap
    found: bool
    value: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = 0.0


@dataclass
class DataConflict:
    metric: str
    entries: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DataConflictResolution:
    conflict: DataConflict
    canonical_value: str
    canonical_unit: str
    canonical_source: str
    reason: str
    chapters_to_update: List[str] = field(default_factory=list)


@dataclass
class QualityIssueDiagnosis:
    issue_description: str
    source_layer: str
    remediation: str
    resolved: bool = False


@dataclass
class ChapterDiagnostic:
    chapter_id: str
    score: float
    source_layer: str
    gaps: List[str] = field(default_factory=list)
    repair_attempts: List[Dict[str, Any]] = field(default_factory=list)
    remediations: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    overall_score: float = 0.0
    target_score: float = 80.0
    convergence_rounds: int = 0
    converged: bool = False
    chapter_diagnostics: List[ChapterDiagnostic] = field(default_factory=list)
