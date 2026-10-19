from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator
from src.core.task_structure import (
    ContentDependency,
    SectionRole,
    SectionSpec,
    TaskStructure,
)
from src.core.intent_types import TaskComplexity


def _intent():
    return SimpleNamespace(
        complexity=TaskComplexity.MULTI,
        requires_primary_data=False,
        used_fallback=False,
        forensic_mode=False,
    )


def _plan(*, upstream_first: bool):
    downstream = SectionSpec(
        "section_0::sub_0_0",
        "下游分析",
        SectionRole.ANALYSIS,
        content_dependency=["section_1::sub_1_0"],
    )
    upstream = SectionSpec(
        "section_1::sub_1_0",
        "上游数据",
        SectionRole.ANALYSIS,
    )
    layers = (
        [[upstream.section_id], [downstream.section_id]]
        if upstream_first
        else [[downstream.section_id], [upstream.section_id]]
    )
    structure = TaskStructure(
        task_id="dag-audit-test",
        topic="测试主题",
        sections=[downstream, upstream],
        dependencies=[
            ContentDependency(
                from_section=upstream.section_id,
                to_section=downstream.section_id,
                dependency_type="analysis",
            )
        ],
        parallel_groups=layers,
    )
    return DynamicPhaseOrchestrator().plan(structure, _intent(), "测试主题")


def test_auditor_rejects_downstream_layer_before_upstream_layer():
    from src.core.dag_plan_audit import DAGPlanAuditor

    result = DAGPlanAuditor().audit(_plan(upstream_first=False))

    assert result.passed is False
    assert any(issue.code == "dependency_order" for issue in result.issues)
    assert result.revision_feedback


def test_auditor_accepts_valid_upstream_first_plan():
    from src.core.dag_plan_audit import DAGPlanAuditor

    result = DAGPlanAuditor().audit(_plan(upstream_first=True))

    assert result.passed is True
    assert result.issues == []


def test_auditor_rejects_unknown_agent_dependency_and_unassigned_section():
    from src.core.dag_plan_audit import DAGPlanAuditor

    plan = _plan(upstream_first=True)
    plan.phases[0].section_ids = []
    plan.phases[0].agent_specs[0].dependencies = ["ghost_agent"]
    plan.phases[0].agent_specs[0].config["resolved_dependencies"] = ["ghost_agent"]

    result = DAGPlanAuditor().audit(plan)

    assert result.passed is False
    assert any(issue.code == "unassigned_section" for issue in result.issues)
    assert any(issue.code == "unresolved_agent_dependency" for issue in result.issues)


def test_routing_result_exposes_dag_audit_before_execution():
    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

    adapter = IntelligentRoutingAdapter(use_llm=False)
    adapter._analyze_intent = lambda *_args, **_kwargs: _intent()
    adapter._analyze_structure = lambda *_args, **_kwargs: _plan(
        upstream_first=False
    ).task_structure
    adapter._orchestrate_phases = lambda *_args, **_kwargs: _plan(
        upstream_first=False
    )

    result = adapter.analyze(
        "测试任务",
        {"topic": "测试主题", "aspects": ["下游分析", "上游数据"]},
        "测试主题",
    )

    assert result.dag_audit.passed is False
    assert result.dag_audit.revision_feedback


def test_routing_reaudits_after_safe_order_revision():
    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

    adapter = IntelligentRoutingAdapter(use_llm=False)
    adapter._analyze_intent = lambda *_args, **_kwargs: _intent()
    structure = _plan(upstream_first=False).task_structure
    adapter._analyze_structure = lambda *_args, **_kwargs: structure

    def replan(*_args, **_kwargs):
        return DynamicPhaseOrchestrator().plan(structure, _intent(), "测试主题")

    adapter._orchestrate_phases = replan

    result = adapter.analyze(
        "测试任务",
        {"topic": "测试主题", "aspects": ["下游分析", "上游数据"]},
        "测试主题",
    )

    assert result.dag_audit.passed is True
    assert len(result.dag_review_history) == 2
    assert result.dag_review_history[0]["passed"] is False
    assert result.dag_review_history[-1]["passed"] is True
    assert result.dag_document["audit"]["passed"] is True


def test_routing_reaudits_subsection_plan_without_reexpansion_failure():
    """A safe DAG reorder must be able to re-plan an already expanded tree."""
    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

    downstream = SectionSpec(
        "section_0",
        "下游分析",
        SectionRole.ANALYSIS,
        content_dependency=["section_1"],
    )
    upstream = SectionSpec("section_1", "上游数据", SectionRole.ANALYSIS)
    structure = TaskStructure(
        task_id="dag-subsection-replan-test",
        topic="测试主题",
        sections=[downstream, upstream],
        section_data_specs=[
            {
                "section_id": "section_0",
                "name": "下游分析",
                "sub_sections": [{"id": "sub_0_0", "name": "下游指标", "points": ["指标"]}],
            },
            {
                "section_id": "section_1",
                "name": "上游数据",
                "sub_sections": [{"id": "sub_1_0", "name": "上游指标", "points": ["指标"]}],
            },
        ],
        dependencies=[
            ContentDependency(
                from_section="section_1",
                to_section="section_0",
                dependency_type="analysis",
            )
        ],
    )

    adapter = IntelligentRoutingAdapter(use_llm=False)
    adapter._analyze_intent = lambda *_args, **_kwargs: _intent()
    adapter._analyze_structure = lambda *_args, **_kwargs: structure

    result = adapter.analyze(
        "测试任务",
        {"topic": "测试主题", "aspects": ["下游分析", "上游数据"]},
        "测试主题",
    )

    assert result.dag_audit.passed is True
    assert len(result.dag_review_history) == 2
    assert result.dag_review_history[0]["passed"] is False
    assert result.dag_review_history[-1]["passed"] is True


@pytest.mark.asyncio
async def test_failed_dag_audit_blocks_agent_creation():
    from unittest.mock import MagicMock

    from src.core.dag_plan_audit import DAGPlanAuditor
    from src.core.intelligent_routing_adapter import IntelligentRoutingResult
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    requirement = MagicMock(
        topic="测试主题",
        aspects=["下游分析"],
        output_type=MagicMock(value="markdown"),
        include_survey=False,
        enable_questionnaire=False,
        survey_mode=None,
        survey_target_count=None,
        dynamic_fields={},
        session_id="dag-gate-test",
    )
    orchestrator._parse_requirement = MagicMock(return_value=requirement)
    failed_audit = DAGPlanAuditor().audit(_plan(upstream_first=False))
    routing_result = IntelligentRoutingResult(
        user_request="测试任务",
        requirement={},
        intent_result=MagicMock(),
        task_structure=_plan(upstream_first=False).task_structure,
        execution_plan=_plan(upstream_first=False),
        decomposition_plan=MagicMock(),
        dag_audit=failed_audit,
        dag_document={"audit": failed_audit.to_dict()},
    )
    orchestrator._routing_adapter.analyze = MagicMock(return_value=routing_result)
    orchestrator._create_agents_from_plan = MagicMock()
    orchestrator._create_agents = MagicMock()
    orchestrator._task_persistence = MagicMock()

    result = await orchestrator._research_with_routing(
        user_input="测试任务",
        output_dir=None,
        user_id=None,
        interaction_mode=False,
        interaction_callback=None,
        task_id="dag-gate-test",
    )

    assert result.status == "failed"
    assert "DAG计划审查未通过" in result.summary
    orchestrator._create_agents_from_plan.assert_not_called()
    orchestrator._create_agents.assert_not_called()


@pytest.mark.asyncio
async def test_routing_receives_confirmed_framework_context_before_dag_planning():
    """The routing boundary must not discard the confirmed chapter tree.

    This is a diagnostic regression test for the manifest failure observed in
    the six-chapter E2E.  The adapter is stopped immediately after capture so
    the test exercises only the requirement -> routing boundary and cannot
    pass because of later report assembly behavior.
    """
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    orchestrator._task_persistence = MagicMock()
    orchestrator._preparse_annual_report = AsyncMock(return_value=True)

    captured = {}

    def capture_and_stop(*args, **kwargs):
        captured["requirement"] = kwargs["requirement"]
        raise RuntimeError("stop after routing-boundary capture")

    orchestrator._routing_adapter.analyze = capture_and_stop

    framework_tree = [
        {
            "id": "market",
            "name": "市场规模与出货量",
            "sub_sections": [{"id": "volume", "name": "出货量", "points": ["出货量"]}],
        }
    ]
    result = await orchestrator._research_with_routing(
        user_input={
            "topic": "中国智能手机行业分析",
            "aspects": ["市场规模与出货量"],
            "sections_tree": framework_tree,
        },
        output_dir=None,
        user_id=None,
        interaction_mode=False,
        interaction_callback=None,
        task_id="routing-context-contract-test",
    )

    assert result.status == "failed"
    assert "section_details" in captured["requirement"]
    assert captured["requirement"]["section_details"][0]["id"] == "market"
    assert captured["requirement"]["sections_tree"] == framework_tree
    assert captured["requirement"]["dynamic_fields"]["sections_tree"] == framework_tree
