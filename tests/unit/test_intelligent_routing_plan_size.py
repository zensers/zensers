from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator
from src.core.intent_types import IntentType, TaskComplexity
from src.core.semantic_intent import DeepIntentResult
from src.core.task_structure import SectionRole, SectionSpec, TaskStructure
from src.core.task_structure import ContentDependency


def _plan_for(complexity):
    sections = [
        SectionSpec(f"section_{i}", f"章节{i}", SectionRole.ANALYSIS)
        for i in range(4)
    ]
    structure = TaskStructure(
        task_id="routing-size-test",
        topic="topic",
        sections=sections,
        parallel_groups=[[s.section_id for s in sections]],
    )
    intent = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="test",
        complexity=complexity,
    )
    return DynamicPhaseOrchestrator().plan(structure, intent, "topic")


def test_single_complexity_uses_one_agent_per_analysis_section():
    plan = _plan_for(TaskComplexity.SINGLE)

    assert plan.total_agents == 6  # 4 analysis + calibration + report
    assert [phase.phase_type.value for phase in plan.phases] == [
        "analysis", "calibration", "report"
    ]


def test_multi_complexity_keeps_separate_data_collection_phase():
    plan = _plan_for(TaskComplexity.MULTI)

    assert plan.total_agents == 10  # 4 data + 4 analysis + calibration + report
    assert [phase.phase_type.value for phase in plan.phases] == [
        "data_collection", "analysis", "calibration", "report"
    ]


def test_dependency_layers_follow_source_to_target_direction():
    sections = [
        SectionSpec("a", "A", SectionRole.ANALYSIS),
        SectionSpec("b", "B", SectionRole.ANALYSIS),
        SectionSpec("c", "C", SectionRole.ANALYSIS),
    ]
    structure = TaskStructure(
        task_id="dag-test",
        topic="topic",
        sections=sections,
        dependencies=[
            ContentDependency("a", "b", "analysis"),
            ContentDependency("b", "c", "analysis"),
        ],
    )

    from src.core.task_structure import TaskStructureAnalyzer
    groups = TaskStructureAnalyzer(use_llm=False)._compute_parallel_groups(
        sections, structure.dependencies
    )

    assert groups == [["a"], ["b"], ["c"]]


def test_large_multi_report_uses_compact_route_without_primary_data():
    sections = [
        SectionSpec(f"section_{i}", f"章节{i}", SectionRole.ANALYSIS)
        for i in range(9)
    ]
    structure = TaskStructure(
        task_id="large-routing-test",
        topic="topic",
        sections=sections,
        parallel_groups=[[s.section_id for s in sections]],
    )
    intent = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="test",
        complexity=TaskComplexity.MULTI,
        requires_primary_data=False,
    )

    plan = DynamicPhaseOrchestrator().plan(structure, intent, "topic")

    assert plan.total_agents == 11  # 9 analysis + calibration + report
    assert plan.phases[0].phase_type.value == "analysis"
    assert all(
        spec.config.get("compact_route") is True
        for spec in plan.phases[0].agent_specs
    )


def test_same_role_other_sections_share_one_parallel_phase():
    sections = [
        SectionSpec("analysis", "分析", SectionRole.ANALYSIS),
        SectionSpec("data_a", "数据A", SectionRole.DATA_COLLECTION),
        SectionSpec("data_b", "数据B", SectionRole.DATA_COLLECTION),
        SectionSpec("data_c", "数据C", SectionRole.DATA_COLLECTION),
    ]
    structure = TaskStructure(
        task_id="grouped-other-sections-test",
        topic="topic",
        sections=sections,
        parallel_groups=[[s.section_id for s in sections]],
    )
    intent = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="test",
        complexity=TaskComplexity.SINGLE,
    )

    plan = DynamicPhaseOrchestrator().plan(structure, intent, "topic")

    data_phases = [p for p in plan.phases if p.phase_type.value == "data_collection"]
    assert len(data_phases) == 1
    assert data_phases[0].section_ids == ["data_a", "data_b", "data_c"]
