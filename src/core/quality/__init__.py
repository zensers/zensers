# -*- coding: utf-8 -*-
"""
质量控制模块
============

提供研究报告系统的质量控制能力：

1. QualityMetadataExtractor - 从Skill输出提取质量元数据
2. QualityChecker - 三阶段质量检查器
3. QualityFeedbackExecutor - 反馈循环执行器 (已废弃，由engine统一重试替代)

设计文档: docs/KNOWLEDGE_BASE/03_QUALITY/COMPLETE_DESIGN.md
配置文件: config/system.yaml (quality节点)
"""

from .metadata_extractor import QualityMetadataExtractor, QualityMetadata, SourceInfo
from .checkers import (
    BaseQualityChecker as QualityCheckerBase,
    QualityResult,
    DataCollectionQualityChecker,
    AnalysisQualityChecker,
    ReportQualityChecker,
)
from .feedback_executor import (
    QualityFeedbackExecutor,
    AttemptRecord,
    FeedbackAction,
)
from .findings import SectionFindings, extract_findings


__all__ = [
    # 元数据提取
    "QualityMetadataExtractor",
    "QualityMetadata",
    "SourceInfo",
    
    # 质量检查器
    "QualityCheckerBase",
    "QualityResult",
    "DataCollectionQualityChecker",
    "AnalysisQualityChecker",
    "ReportQualityChecker",
    
    # 反馈执行
    "QualityFeedbackExecutor",
    "AttemptRecord",
    "FeedbackAction",
    
    # 结构化研究发现
    "SectionFindings",
    "extract_findings",
]
