# -*- coding: utf-8 -*-
"""
Knowledge Module - 混合知识管理模块

实现不依赖向量数据库的知识管理：
- 时间有效性追踪
- 来源追溯与审计
- 知识编译（结构化存储）
- 矛盾检测
- 引用关联
- 知识导入

设计理念：
- 用户越用越强
- 每次研究自动积累知识
- 知识可审计、可追溯
"""

from .temporal_knowledge import (
    TemporalKnowledge,
    TemporalFact,
    FactVersion,
    TemporalQuery,
    FactStatus
)

from .provenance_store import (
    ProvenanceStore,
    SourceRecord,
    SourceTrustLevel,
    AuditEntry
)

from .compiler import (
    KnowledgeCompiler,
    KnowledgePage,
    CompiledKnowledge,
    PageType,
    BacklinkSystem
)

from .contradiction_detector import (
    ContradictionDetector,
    Contradiction,
    ContradictionType,
    ResolutionStatus
)

from .importer import (
    KnowledgeImporter,
    ImportResult,
    FileParser,
    ImportProgress
)

__all__ = [
    # 时间有效性
    "TemporalKnowledge",
    "TemporalFact",
    "FactVersion",
    "TemporalQuery",
    "FactStatus",
    
    # 来源追溯
    "ProvenanceStore",
    "SourceRecord",
    "SourceTrustLevel",
    "AuditEntry",
    
    # 知识编译
    "KnowledgeCompiler",
    "KnowledgePage",
    "CompiledKnowledge",
    "PageType",
    "BacklinkSystem",
    
    # 矛盾检测
    "ContradictionDetector",
    "Contradiction",
    "ContradictionType",
    "ResolutionStatus",
    
    # 知识导入
    "KnowledgeImporter",
    "ImportResult",
    "FileParser",
    "ImportProgress",
]