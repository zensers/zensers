from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from datetime import datetime
from uuid import uuid4


# ============================================================
# 6.0 全局类型定义
# ============================================================

SnapshotId = str


class ExecutionStatus(Enum):
    PENDING = "pending"
    PREVIEW_READY = "preview_ready"
    ABORTED = "aborted"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    FULL_REWRITE_NEEDED = "full_rewrite_needed"
    FULL_RESEARCH_NEEDED = "full_research_needed"
    CLARIFICATION_FAILED = "clarification_failed"
    COMPLETED = "completed"
    LIGHTWEIGHT_DONE = "lightweight_done"


class Choice(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"
    ABORT = "abort"
    SKIP = "skip"
    INSERT = "insert"
    REMOVE = "remove"
    REORDER = "reorder"
    COMMIT = "commit"


class TaskStatus(Enum):
    PENDING = "pending"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MergeStrategy(Enum):
    OURS = "ours"
    THEIRS = "theirs"
    UNION = "union"
    MANUAL = "manual"


class CommitStatus(Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


class RevisionOpType(Enum):
    MODIFY = "modify"
    DELETE = "delete"
    ADD = "add"
    COPY = "copy"
    MERGE = "merge"
    SPLIT = "split"
    SWAP = "swap"
    REORDER = "reorder"
    DEDUP = "dedup"
    STYLE = "style"
    REVIEW = "review"
    UNKNOWN = "unknown"
    UPDATE_TITLE = "update_title"
    REPLACE_TEXT = "replace_text"
    CHANGE_CASE = "change_case"
    FIX_PUNCTUATION = "fix_punctuation"
    MODIFY_TABLE = "modify_table"
    MODIFY_CHART = "modify_chart"
    ADD_ELEMENT = "add_element"
    DELETE_ELEMENT = "delete_element"
    TRANSLATE = "translate"


class RefType(Enum):
    UUID = "uuid"
    NUMBER = "number"
    INDEX = "index"


class ConflictType(Enum):
    CIRCULAR_DEPENDENCY = "circular_dependency"
    SAME_TARGET_MODIFY_DELETE = "same_target"
    CROSS_REF_BROKEN = "cross_ref_broken"
    ORDER_SENSITIVE = "order_sensitive"
    RESOURCE_CONTENTION = "resource_contention"


class LocationStrategy(Enum):
    ORDINAL = "ordinal"
    REFERENCE = "reference"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


class SnapshotType(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


# ---- Dataclasses ----

@dataclass
class SectionRef:
    uuid: str
    ref_type: RefType
    number: Optional[str] = None
    index: Optional[int] = None
    parent_id: Optional[str] = None
    raw_text: str = ""


@dataclass
class RevisionTarget:
    raw_text: str
    section_refs: List[SectionRef]
    location_strategy: LocationStrategy
    is_ambiguous: bool


@dataclass
class RevisionAction:
    action_id: str
    action_type: RevisionOpType
    target: RevisionTarget
    source: Optional[RevisionTarget] = None
    content: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    ambiguity_flags: List[str] = field(default_factory=list)


@dataclass
class RevisionTask:
    id: str
    action: RevisionAction
    status: TaskStatus = TaskStatus.PENDING
    checkpoint_id: Optional[SnapshotId] = None
    error: Optional[str] = None
    preview: Optional[PreviewDiff] = None
    result: Optional[ExecutionResult] = None


@dataclass
class SectionNode:
    id: str
    section: "Section"
    children: List["SectionNode"] = field(default_factory=list)
    parent_id: Optional[str] = None


@dataclass
class ReportTree:
    root: Optional[SectionNode] = None
    node_map: Dict[str, SectionNode] = field(default_factory=dict)

    def find(self, node_id: str) -> Optional[SectionNode]:
        return self.node_map.get(node_id)

    def find_by_number(self, number: str) -> Optional[SectionNode]:
        for node in self.node_map.values():
            if hasattr(node.section, "number") and node.section.number == number:
                return node
        return None

    def find_by_index(self, parent_id: str, index: int) -> Optional[SectionNode]:
        parent = self.node_map.get(parent_id)
        if parent and 0 <= index < len(parent.children):
            return parent.children[index]
        return None

    def sync_to_report(self, report: "Report") -> None:
        if hasattr(report, "sections"):
            sections = []
            if self.root is not None:
                for child in self.root.children:
                    self._collect_sections(child, sections)
            report.sections = sections

    def _collect_sections(self, node: Optional[SectionNode], acc: List) -> None:
        if node is None:
            return
        acc.append(node.section)
        for child in node.children:
            self._collect_sections(child, acc)


InsertPosition = str


@dataclass
class LocationResult:
    matches: List[SectionRef]
    is_ambiguous: bool
    strategy_used: LocationStrategy
    confidence: float
    fallback_chain: List[LocationStrategy]


@dataclass
class ManipulationResult:
    success: bool
    error: Optional[str] = None
    affected_ids: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    intents: List[RevisionAction]
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)
    is_uncertain: bool = False
    suggested_section: Optional[str] = None
    is_global_feedback: bool = False
    confidence: float = 1.0


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class PreviewDiff:
    before: Any = None
    after: Any = None
    structural_changes: Optional["StructuralImpact"] = None
    commit_message: Optional[str] = None


@dataclass
class DataValidation:
    has_changes: bool = False
    changes: List[str] = field(default_factory=list)
    change_ratio: float = 0.0


@dataclass
class ExecutionResult:
    success: bool
    error: Optional[str] = None
    created_ids: List[str] = field(default_factory=list)
    affected_ids: List[str] = field(default_factory=list)
    diff: Optional[PreviewDiff] = None
    validation: Optional[DataValidation] = None
    sub_results: List["ExecutionResult"] = field(default_factory=list)


@dataclass
class RollbackResult:
    success: bool
    error: Optional[str] = None


@dataclass
class ImpactEstimate:
    affected_sections: List[str] = field(default_factory=list)


@dataclass
class ImpactAnalysis:
    affected_sections: List[str] = field(default_factory=list)
    risk_level: str = "low"


@dataclass
class ClarificationRequest:
    question: str
    options: List[str] = field(default_factory=list)


@dataclass
class ExecFailure:
    failed_index: int
    error: str
    result: Optional[ExecutionResult] = None


@dataclass
class PlanExecutionResult:
    success: bool
    error: Optional[str] = None
    exec_failure: Optional[ExecFailure] = None
    sub_results: List[ExecutionResult] = field(default_factory=list)


@dataclass
class TOCChange:
    section_id: str
    old_number: Optional[str] = None
    new_number: Optional[str] = None
    change_type: str = "modified"


@dataclass
class DuplicatePair:
    source_id: str
    target_id: str
    similarity: float


@dataclass
class DiffReport:
    from_commit_id: str
    to_commit_id: str
    changes: List["ChangeRecord"] = field(default_factory=list)


@dataclass
class BlameEntry:
    section_id: str
    commit_id: str
    author: str
    timestamp: datetime
    operation: str


@dataclass
class RestoreResult:
    success: bool
    restored_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SnapshotInfo:
    snapshot_id: SnapshotId
    report_id: str
    snapshot_type: SnapshotType
    created_at: datetime
    parent_id: Optional[SnapshotId] = None
    size_bytes: int = 0


@dataclass
class ChangeRecord:
    section_id: str
    field: str
    old_value: Any
    new_value: Any
    change_type: str


@dataclass
class BrokenReference:
    original_text: str
    target_section_id: str
    new_target_number: Optional[str] = None
    is_fixable: bool = False


@dataclass
class ReferenceMatch:
    original_text: str
    target_number: str
    start: int
    end: int
    ref_type: str


@dataclass
class SectionReference:
    section_id: str
    ref_text: str
    context: str


@dataclass
class FixReport:
    fixed: int = 0
    unfixable: int = 0
    details: List[str] = field(default_factory=list)


@dataclass
class StructuralImpact:
    affected_sections: List[str]
    toc_changes: List[TOCChange]
    cross_refs_broken: List[BrokenReference]
    data_refs_affected: List[str]
    renumbering_required: bool = False
    renumbering_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecContext:
    report: "Report"
    report_tree: ReportTree
    snapshot_manager: "SnapshotManager"
    snapshot_id: Optional[SnapshotId] = None
    user_id: str = ""
    session_id: str = ""
    content_manipulator: Optional["ContentManipulator"] = None
    progress_callback: Optional[Callable] = None
    operation_index: int = 0
    total_operations: int = 0
    id_remapper: Optional["IdRemapper"] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Conflict:
    type: ConflictType
    description: str
    involved_action_ids: List[str]
    resolution: Optional[str] = None


@dataclass
class MergeConflict:
    source_commit_id: str
    target_commit_id: str
    section_id: str
    conflict_type: str
    description: str


@dataclass
class RevisionPlan:
    plan_id: str
    actions: List[RevisionAction]
    dependency_graph: Dict[str, List[str]]
    id_remap_table: Dict[str, str]
    conflicts: List[Conflict] = field(default_factory=list)
    snapshot_required: bool = True
    estimated_impact: Optional[ImpactAnalysis] = None


@dataclass
class ExecutionFlow:
    status: ExecutionStatus = ExecutionStatus.PENDING
    preview: Optional[PreviewDiff] = None
    snapshot_id: Optional[SnapshotId] = None
    plan: Optional[RevisionPlan] = None
    impacts: Optional[StructuralImpact] = None
    error: Optional[str] = None
    section_id: Optional[str] = None
    partial_results: Optional[List[ExecutionResult]] = None
    tasks: List[RevisionTask] = field(default_factory=list)
    current_index: int = 0
    _report_version: int = 0
    _conversation_container: Any = None


@dataclass
class RevisionCommit:
    commit_id: str
    parent_commit_id: Optional[str]
    report_id: str
    operations: List[RevisionAction]
    diff_summary: str
    author: str
    timestamp: datetime
    message: str
    snapshot_id: SnapshotId
    tags: List[str]
    status: CommitStatus = CommitStatus.PENDING


@dataclass
class RevisionBranch:
    branch_id: str
    name: str
    report_id: str
    head_commit_id: str
    created_at: datetime


@dataclass
class RevisionSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_message: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    plan: Optional[RevisionPlan] = None
    snapshot_id: Optional[SnapshotId] = None
    commit_id: Optional[str] = None
    history: List[RevisionAction] = field(default_factory=list)


class PlanConflictError(Exception):
    def __init__(self, message: str, conflicts: Optional[List[Conflict]] = None):
        super().__init__(message)
        self.conflicts = conflicts if conflicts is not None else []


class RevisionAbortedException(Exception):
    pass


# 为避免循环导入，在模块末尾设置 SnapshotManager 的前向引用
SnapshotManager = Any
ContentManipulator = Any
IdRemapper = Any
Report = Any
Section = Any
