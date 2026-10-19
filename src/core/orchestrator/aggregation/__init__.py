"""
聚合层模块

包含：
- ResultAggregator: 结果聚合器
- KnowledgeCompiler: 知识编译器
- WisdomRecorder: 经验记录器

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

from .result_aggregator import (
    ResultAggregator,
    AggregationConfig,
    AggregationResult,
    ConflictRecord,
    ConflictResolution,
)

from .knowledge_compiler import (
    KnowledgeCompiler,
    KnowledgeCompilerConfig,
    KnowledgePage,
    KnowledgeType,
)

from .wisdom_recorder import (
    WisdomRecorder,
    WisdomRecorderConfig,
    ExperienceRecord,
)

__all__ = [
    # 结果聚合
    "ResultAggregator",
    "AggregationConfig",
    "AggregationResult",
    "ConflictRecord",
    "ConflictResolution",
    
    # 知识编译
    "KnowledgeCompiler",
    "KnowledgeCompilerConfig",
    "KnowledgePage",
    "KnowledgeType",
    
    # 经验记录
    "WisdomRecorder",
    "WisdomRecorderConfig",
    "ExperienceRecord",
]
