from unittest.mock import MagicMock

from src.core.semantic_intent import DeepIntentResult
from src.core.task_structure import SectionRole, TaskStructureAnalyzer


def test_partial_llm_dependencies_are_completed_at_stage_boundary():
    intent = MagicMock(spec=DeepIntentResult)
    intent.domain_context = {"industry": "smartphone"}
    analyzer = TaskStructureAnalyzer(use_llm=False)
    llm_output = {
        "sections": [
            {"name": "数据收集", "role": "data_collection"},
            {"name": "市场分析", "role": "analysis"},
            {"name": "结论", "role": "synthesis"},
        ],
        # A partial valid edge must not suppress the missing collection edge.
        "dependencies": [{"from": "市场分析", "to": "结论", "type": "synthesis"}],
    }

    structure = analyzer._build_structure_from_llm(
        llm_output,
        ["数据收集", "市场分析", "结论"],
        "task-dag-1",
        "smartphone",
        intent,
    )

    data_id = next(s.section_id for s in structure.sections if s.section_role == SectionRole.DATA_COLLECTION)
    analysis_id = next(s.section_id for s in structure.sections if s.section_role == SectionRole.ANALYSIS)
    assert any(
        dep.from_section == data_id and dep.to_section == analysis_id
        for dep in structure.dependencies
    )
