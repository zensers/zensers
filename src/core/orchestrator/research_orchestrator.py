"""
Research Orchestrator - 向后兼容适配器

此文件保留向后兼容性，所有实现已迁移到精简版 orchestrator.py

迁移指南:
    # 旧导入（仍然有效）
    from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
    
    # 新导入（推荐）
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

# 从精简版导入所有公共API
from .orchestrator import (
    ResearchOrchestrator,
    ResearchRequirement,
    ResearchResult,
    research,
)

# 向后兼容：导出原有的便捷函数
__all__ = [
    "ResearchOrchestrator",
    "ResearchRequirement", 
    "ResearchResult",
    "research",
]
