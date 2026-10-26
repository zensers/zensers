from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


def resolve_expected_chars(chapter_spec: Optional[Dict[str, Any]], framework_config: Optional[Dict[str, Any]]) -> int:
    """Chapter length target in chars.

    Priority: explicit per-chapter ``word_count_target`` → framework
    ``agent_config.content.min_section_length`` → legacy 2000 default.
    Shared by the chapter writer (prompt directive + streaming budget) and
    the reviewer (length criterion) so both enforce the same contract.
    """
    raw = (chapter_spec or {}).get("word_count_target")
    if raw is None:
        content_cfg = ((framework_config or {}).get("agent_config") or {}).get(
            "content"
        ) or {}
        raw = content_cfg.get("min_section_length")
    try:
        resolved = int(raw) if raw is not None else 2000
    except (TypeError, ValueError):
        resolved = 2000
    return max(500, resolved)


@dataclass
class ChapterRequirement:
    section_id: str
    sub_section_id: str = ""
    required_topics: List[str] = field(default_factory=list)
    required_metrics: List[str] = field(default_factory=list)
    claim_scope: str = ""
    exclude_topics: List[str] = field(default_factory=list)
    evidence_level: str = "factual"


@dataclass
class ReportEvidenceContext:
    structured_data: Dict[str, Any] = field(default_factory=dict)
    raw_search_results: List[Dict[str, Any]] = field(default_factory=list)
    source_catalog: List[Dict[str, Any]] = field(default_factory=list)
    evidence_registry: Dict[str, Any] = field(default_factory=dict)
    section_index: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterCoverage:
    ready_to_write: bool
    missing_topics: List[str] = field(default_factory=list)
    missing_metrics: List[str] = field(default_factory=list)
    available_in_structured: List[str] = field(default_factory=list)
    available_in_raw_search: List[str] = field(default_factory=list)
    external_search_required: bool = False


@dataclass
class DataPoint:
    metric: str
    value: str
    unit: str
    source: str
    chapter_id: str = ""
    sub_section_id: str = ""
    confidence: float = 1.0
    # Evidence contract fields.  These must survive the writer -> registry ->
    # final report path; otherwise a source name without its scope is not
    # sufficient to audit a claim.
    source_url: str = ""
    evidence_id: str = ""
    provenance_id: str = ""
    evidence_excerpt: str = ""
    locator: str = ""
    geographic_scope: str = ""
    period: str = ""
    population: str = ""
    epistemic_level: str = "factual"
    evidence_status: str = "unverified"


@dataclass
class MetricEntry:
    metric: str
    value: str
    unit: str
    canonical_chapter: str
    source: str
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    # 定性表述变体（复述差异，无数值分歧）——仅展示用途，不进 L5 blocking。
    variants: List[Dict[str, Any]] = field(default_factory=list)
    evidence_id: str = ""
    provenance_id: str = ""
    source_url: str = ""
    period: str = ""
    geographic_scope: str = ""
    population: str = ""


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
    parent_section_context: Dict[str, Any] = field(default_factory=dict)
    global_evidence_pool: List[Dict[str, Any]] = field(default_factory=list)
    raw_search_results: List[Dict[str, Any]] = field(default_factory=list)
    # Pointer to the complete task evidence snapshot; it is not a filtered
    # replacement for the raw evidence available to the report agent.
    raw_data_location: str = ""
    sibling_section_summaries: List[Dict[str, Any]] = field(default_factory=list)
    chapter_requirements: Dict[str, Any] = field(default_factory=dict)
    used_claims: List[str] = field(default_factory=list)
    used_evidence_ids: List[str] = field(default_factory=list)
    # The writer must know the delivery format.  Word and PPT require
    # different editorial contracts; keep this optional for legacy callers.
    output_format: str = "docx"


@dataclass
class ChapterWriteOutput:
    chapter_id: str
    title: str
    content: str
    sub_section_id: str = ""
    data_points_used: List[DataPoint] = field(default_factory=list)
    key_conclusions: List[str] = field(default_factory=list)
    self_check_passed: bool = True
    self_check_issues: List[str] = field(default_factory=list)
    # Explicit lifecycle state prevents a failed chapter from disappearing
    # from the assembled report and being mistaken for successful coverage.
    status: str = "ready"
    error: str = ""
    # Planning assessment from the LLM's pre-writing analysis
    planning_assessment: Optional[Dict[str, Any]] = None


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
    # Reviewer-output-unparseable marker: distinguishes "the LLM review text
    # could not be parsed" from "the chapter is genuinely bad", so the
    # orchestrator quality loop can gate rewrite() calls (a parse-failed
    # review carries no usable signal to rewrite against).
    parse_failed: bool = False


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
    audit_layer: str = ""


@dataclass
class DataRepairResult:
    gap: DataGap
    found: bool
    value: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = 0.0
    source_url: str = ""
    evidence_id: str = ""
    provenance_id: str = ""
    evidence_excerpt: str = ""
    locator: str = ""
    task_id: str = ""
    request_id: str = ""
    retrieved_at: Optional[str] = None
    geographic_scope: str = ""
    period: str = ""
    population: str = ""
    epistemic_level: str = ""


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
