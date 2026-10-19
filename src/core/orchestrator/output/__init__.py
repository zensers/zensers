"""
输出层模块

包含：
- ReportGenerator: 报告生成器
- DocumentGenerator: 文档生成器
- StorageManager: 存储管理器

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

from .report_generator import (
    ReportGenerator,
    ReportConfig,
    ReportResult,
    ReportSection,
    ReportFormat,
)

from .document_generator import (
    DocumentGenerator,
    DocumentConfig,
    DocumentResult,
    DocumentFormat,
)

from .storage_manager import (
    StorageManager,
    StorageConfig,
    ResearchRecord,
)

__all__ = [
    # 报告生成
    "ReportGenerator",
    "ReportConfig",
    "ReportResult",
    "ReportSection",
    "ReportFormat",
    
    # 文档生成
    "DocumentGenerator",
    "DocumentConfig",
    "DocumentResult",
    "DocumentFormat",
    
    # 存储管理
    "StorageManager",
    "StorageConfig",
    "ResearchRecord",
]
