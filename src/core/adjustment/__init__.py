# -*- coding: utf-8 -*-
"""
调整模块

Phase 8: 报告修订闭环

提供文档修订和调整功能：
- AdjustmentHandler: 调整处理器
- RevisionManager: 修订历史管理
- SectionLocator: 章节定位器
- ContentApplier: 内容应用器
- RevisionHandler: 修订处理器（统一入口）
- RevisionService: 修订服务（多场景统一入口）
- RevisionIntentMapper: 修订意图映射器（三级映射架构）
- BatchRevisionService: 批量修订服务（单次 LLM 调用优化）
- OrdinalReferenceParser: 序数词引用解析器（Phase 2.1）
- ConversationReferenceTracker: 对话历史引用追踪器（Phase 2.2）
- EnhancedSectionLocator: 增强版章节定位器（Phase 2.3）
- CascadeUpdateAnalyzer: 级联更新分析器（Phase 3.1）
- RevisionTypeInferrer: 修订类型推断器（Phase 3.2）
"""

from .adjustment_handler import AdjustmentHandler, AdjustmentResult
from .batch_revision_service import BatchRevisionService, BatchRevisionResult
from .cascade_update_analyzer import CascadeUpdateAnalyzer, CascadeImpact, ConsistencyCheck
from .content_applier import ContentApplier, ApplyResult
from .conversation_reference_tracker import ConversationReferenceTracker
from .enhanced_section_locator import EnhancedSectionLocator
from .ordinal_parser import OrdinalReferenceParser, SectionMatch
from .revision_handler import RevisionHandler, RevisionRequest, RevisionResult, RevisionStatus
from .revision_manager import RevisionDiff, RevisionManager, RevisionRecord
from .revision_intent_mapper import RevisionIntentMapper, RouteDecision
from .revision_service import RevisionService, RevisionContext, QualityIssue
from .revision_type_inferrer import RevisionTypeInferrer, RevisionTypeInferenceResult
from .section_locator import (
    CachedIndex,
    DocumentNotFoundError,
    DocumentParseError,
    SectionLocation,
    SectionLocator,
    SectionLocatorError,
    UnsupportedFormatError,
)

# 修订引擎新模块 (Phase 8)
# 注意: revision_types 必须在 revision_executor 前导入 (避免循环导入)
from .revision_types import (
    AnalysisResult,
    BrokenReference,
    Choice,
    CommitStatus,
    Conflict,
    ConflictType,
    DataValidation,
    DiffReport,
    DuplicatePair,
    ExecContext,
    ExecFailure,
    ExecutionFlow,
    ExecutionResult,
    ExecutionStatus,
    FixReport,
    ImpactAnalysis,
    ImpactEstimate,
    InsertPosition,
    LocationResult,
    LocationStrategy,
    ManipulationResult,
    MergeConflict,
    MergeStrategy,
    PlanConflictError,
    PlanExecutionResult,
    PreviewDiff,
    ReferenceMatch,
    RefType,
    ReportTree,
    RestoreResult,
    RevisionAbortedException,
    RevisionAction,
    RevisionBranch,
    RevisionCommit,
    RevisionOpType,
    RevisionPlan,
    RevisionSession,
    RevisionTarget,
    RollbackResult,
    SectionNode,
    SectionRef,
    SectionReference,
    SnapshotId,
    SnapshotInfo,
    SnapshotType,
    StructuralImpact,
    TOCChange,
    ValidationResult,
)
from .content_manipulator import ContentManipulator
from .cross_reference_fixer import CrossReferenceFixer
from .report_lock_manager import ReportLockManager
from .revision_executor import LLMOptimizer, ProgressNotifier, RevisionExecutor
from .section_locator_v2 import SectionLocatorV2
from .section_renumberer import SectionRenumberer
from .snapshot_manager import SnapshotManager
from .structural_analyzer import DuplicateDetector, StructuralAnalyzer
from .version_manager import VersionManager
from .atomic_operations.base import AtomicRevision
from .atomic_operations.factory import AtomicOperationFactory

__all__ = [
    # 调整处理
    "AdjustmentHandler",
    "AdjustmentResult",
    # 修订历史
    "RevisionManager",
    "RevisionRecord",
    "RevisionDiff",
    # 章节定位
    "SectionLocator",
    "SectionLocation",
    "SectionLocatorError",
    "DocumentNotFoundError",
    "UnsupportedFormatError",
    "DocumentParseError",
    "CachedIndex",
    # 内容应用
    "ContentApplier",
    "ApplyResult",
    # 修订处理器
    "RevisionHandler",
    "RevisionRequest",
    "RevisionResult",
    "RevisionStatus",
    # 修订服务
    "RevisionService",
    "RevisionContext",
    "QualityIssue",
    # 三级映射 (Phase 1.1)
    "RevisionIntentMapper",
    "RouteDecision",
    # 批量处理 (Phase 1.3)
    "BatchRevisionService",
    "BatchRevisionResult",
    # 问题定位增强 (Phase 2)
    "OrdinalReferenceParser",
    "SectionMatch",
    "ConversationReferenceTracker",
    "EnhancedSectionLocator",
    # 级联更新 (Phase 3)
    "CascadeUpdateAnalyzer",
    "CascadeImpact",
    "ConsistencyCheck",
    "RevisionTypeInferrer",
    "RevisionTypeInferenceResult",
    # 修订引擎 (Phase 8)
    "AtomicOperationFactory",
    "AtomicRevision",
    "BrokenReference",
    "Choice",
    "Conflict",
    "ConflictType",
    "ContentManipulator",
    "CrossReferenceFixer",
    "DuplicateDetector",
    "ExecContext",
    "ExecFailure",
    "ExecutionFlow",
    "ExecutionResult",
    "ExecutionStatus",
    "FixReport",
    "ImpactAnalysis",
    "LLMOptimizer",
    "LocationStrategy",
    "MergeConflict",
    "MergeStrategy",
    "PlanConflictError",
    "PlanExecutionResult",
    "PreviewDiff",
    "ProgressNotifier",
    "ReferenceMatch",
    "RefType",
    "ReportLockManager",
    "ReportTree",
    "RevisionAbortedException",
    "RevisionAction",
    "RevisionBranch",
    "RevisionCommit",
    "RevisionExecutor",
    "RevisionOpType",
    "RevisionPlan",
    "RevisionSession",
    "RevisionTarget",
    "RollbackResult",
    "SectionLocatorV2",
    "SectionNode",
    "SectionRef",
    "SectionRenumberer",
    "SnapshotId",
    "SnapshotInfo",
    "SnapshotManager",
    "SnapshotType",
    "StructuralAnalyzer",
    "StructuralImpact",
    "ValidationResult",
    "VersionManager",
]