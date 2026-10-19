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


async def complete_research_with_document_option(
    orchestrator, task_id, result=None, output_format=None, template=None
):
    """Legacy functional facade for :meth:`ResearchOrchestrator.complete_research`.

    ``result`` is accepted for compatibility with the former helper API; the
    migrated orchestrator remains the source of truth for task persistence.
    """
    if result is not None:
        orchestrator._task_history.append({"task_id": task_id, "result": result})
    return await orchestrator.complete_research(task_id, output_format, template)


async def generate_document_later(orchestrator, task_id, output_format, template=None, adjustments=None):
    if not any(record.get("task_id") == task_id for record in orchestrator._task_history):
        legacy_loader = getattr(orchestrator._result_store, "load_result", None)
        if callable(legacy_loader):
            loaded = legacy_loader(task_id)
            if loaded:
                orchestrator._task_history.append({"task_id": task_id, "result": loaded})
    return await orchestrator.generate_document_later(
        task_id, output_format, template, adjustments
    )


def list_completed_research(orchestrator, user_id=None, limit=20):
    return orchestrator.list_completed_research(user_id=user_id, limit=limit)

# 向后兼容：导出原有的便捷函数
__all__ = [
    "ResearchOrchestrator",
    "ResearchRequirement", 
    "ResearchResult",
    "research",
    "complete_research_with_document_option",
    "generate_document_later",
    "list_completed_research",
]
