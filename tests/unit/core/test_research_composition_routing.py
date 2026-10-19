"""Tests for routing the two supported research execution chains.

These tests intentionally exercise the shared routing model rather than the
standalone survey REST API.  A survey request must be classified as either a
pure survey workflow or a composite research+survey workflow before any
agents are created.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.research_type import ResearchType, infer_research_composition


def _intent(*types, primary=None):
    return SimpleNamespace(
        research_types=list(types),
        primary_research_type=primary or (types[0] if types else None),
    )


def test_chinese_pure_survey_request_selects_pure_survey_workflow():
    composition = infer_research_composition(
        requirement=SimpleNamespace(
            topic="用户满意度问卷调查",
            include_survey=False,
            enable_questionnaire=False,
        ),
        intent_result=_intent(),
        user_request="请设计一份用户满意度问卷调查并模拟回收",
    )

    assert composition.types == [ResearchType.SURVEY]
    assert composition.primary is ResearchType.SURVEY
    assert composition.get_workflow_template_id() == "pure_survey"
    assert composition.get_execution_phases() == [
        "survey_design",
        "survey_execution",
        "survey_analysis",
        "report",
    ]


def test_industry_plus_survey_request_selects_composite_workflow():
    composition = infer_research_composition(
        requirement=SimpleNamespace(
            topic="新能源汽车行业研究",
            include_survey=False,
            enable_questionnaire=False,
        ),
        intent_result=_intent(
            ResearchType.INDUSTRY_RESEARCH,
            ResearchType.SURVEY,
            primary=ResearchType.INDUSTRY_RESEARCH,
        ),
        user_request="先做新能源汽车行业研究，再用问卷验证用户需求",
    )

    assert composition.types == [
        ResearchType.INDUSTRY_RESEARCH,
        ResearchType.SURVEY,
    ]
    assert composition.primary is ResearchType.INDUSTRY_RESEARCH
    assert composition.get_workflow_template_id() == "industry_with_survey"
    assert composition.get_execution_phases() == [
        "data_collection",
        "analysis",
        "survey_design",
        "survey_execution",
        "survey_analysis",
        "report",
    ]


def test_explicit_survey_flag_is_not_lost_when_intent_result_is_incomplete():
    composition = infer_research_composition(
        requirement=SimpleNamespace(
            topic="新能源汽车行业",
            include_survey=True,
            enable_questionnaire=True,
        ),
        intent_result=_intent(ResearchType.INDUSTRY_RESEARCH),
        user_request="新能源汽车行业",
    )

    assert ResearchType.SURVEY in composition.types
    assert composition.get_workflow_template_id() == "industry_with_survey"


@pytest.mark.asyncio
async def test_routing_pure_survey_bypasses_industry_agent_creation(monkeypatch):
    """The intelligent-router entry point must use the canonical survey agent."""
    from src.core.intelligent_routing_adapter import IntelligentRoutingResult
    from src.core.intent_types import IntentType, TaskComplexity
    from src.core.orchestrator.orchestrator import ResearchOrchestrator
    from src.core.semantic_intent import DeepIntentResult
    from src.core.task_structure import TaskStructure
    from src.core.dynamic_orchestrator import ExecutionPlan

    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    requirement = MagicMock(
        topic="用户满意度问卷",
        aspects=[],
        output_type=MagicMock(value="markdown"),
        include_survey=False,
        enable_questionnaire=False,
        dynamic_fields={},
    )
    orchestrator._parse_requirement = MagicMock(return_value=requirement)
    intent = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="survey",
        complexity=TaskComplexity.SINGLE,
    )
    structure = TaskStructure(
        task_id="test", topic="survey", sections=[], dependencies=[],
        execution_graph={}, parallel_groups=[], critical_path=[],
        total_estimated_agents=0,
    )
    plan = ExecutionPlan(
        plan_id="plan", task_structure=structure, phases=[],
        content_lock_rules=[], total_agents=0, estimated_duration="1m",
    )
    orchestrator._routing_adapter.analyze = MagicMock(return_value=IntelligentRoutingResult(
        user_request="survey", requirement={}, intent_result=intent,
        task_structure=structure, execution_plan=plan,
        decomposition_plan=MagicMock(),
    ))
    orchestrator._execute_survey_integration = AsyncMock(return_value={
        "success": True, "status": "completed", "steps": ["survey"],
        "analysis": {"report": "ok"},
    })
    orchestrator._task_persistence = MagicMock(update_task_state=MagicMock())
    create_agents = MagicMock()
    orchestrator._create_agents = create_agents
    orchestrator._create_agents_from_plan = create_agents

    result = await orchestrator._research_with_routing(
        user_input="请设计用户满意度问卷并模拟回收",
        output_dir=None, user_id=None, interaction_mode=False,
        interaction_callback=None, task_id="survey_task",
    )

    assert result.status == "completed"
    orchestrator._execute_survey_integration.assert_awaited_once()
    create_agents.assert_not_called()


@pytest.mark.asyncio
async def test_routing_composite_runs_industry_before_survey(monkeypatch):
    """The composite chain must finish industry execution before survey starts."""
    from src.core.dynamic_orchestrator import ExecutionPlan
    from src.core.intelligent_routing_adapter import IntelligentRoutingResult
    from src.core.intent_types import IntentType, TaskComplexity
    from src.core.orchestrator.orchestrator import ResearchOrchestrator
    from src.core.semantic_intent import DeepIntentResult
    from src.core.task_structure import TaskStructure

    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    requirement = MagicMock(
        topic="新能源汽车行业",
        aspects=["市场规模"],
        output_type=MagicMock(value="markdown"),
        include_survey=False,
        enable_questionnaire=False,
        dynamic_fields={},
        session_id="composite_task",
    )
    orchestrator._parse_requirement = MagicMock(return_value=requirement)
    intent = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="composite",
        research_types=[ResearchType.INDUSTRY_RESEARCH, ResearchType.SURVEY],
        primary_research_type=ResearchType.INDUSTRY_RESEARCH,
        secondary_research_types=[ResearchType.SURVEY],
        complexity=TaskComplexity.SINGLE,
        is_composite=True,
    )
    structure = TaskStructure(
        task_id="test", topic="industry", sections=[], dependencies=[],
        execution_graph={}, parallel_groups=[], critical_path=[],
        total_estimated_agents=0,
    )
    plan = ExecutionPlan(
        plan_id="plan", task_structure=structure, phases=[],
        content_lock_rules=[], total_agents=0, estimated_duration="1m",
    )
    orchestrator._routing_adapter.analyze = MagicMock(return_value=IntelligentRoutingResult(
        user_request="industry + survey", requirement={}, intent_result=intent,
        task_structure=structure, execution_plan=plan, decomposition_plan=None,
    ))
    orchestrator._create_agents = MagicMock(return_value=[])
    execution = MagicMock(status="completed", errors=[], stage_results={})
    orchestrator._execution_engine = MagicMock(execute=AsyncMock(return_value=execution))
    orchestrator._task_persistence = MagicMock(update_task_state=MagicMock())
    aggregate = MagicMock(to_dict=MagicMock(return_value={"sections": []}))
    orchestrator._result_aggregator = MagicMock(aggregate=MagicMock(return_value=aggregate))
    orchestrator._document_agent = MagicMock(execute=AsyncMock(return_value={}))
    orchestrator._wisdom_store = MagicMock(get_recommended_skills=MagicMock(return_value=[]))
    orchestrator._knowledge_manager = None
    order = []

    async def execute_industry(*args, **kwargs):
        order.append("industry")
        return execution

    async def execute_survey(*args, **kwargs):
        order.append("survey")
        return {
            "success": True, "status": "completed", "steps": ["survey"],
            "survey_section": {"title": "Survey"}, "responses_count": 1,
            "findings": {"ok": True}, "analysis": {"report": "survey ok"},
        }

    orchestrator._execution_engine.execute = execute_industry
    orchestrator._execute_survey_integration = execute_survey
    with patch(
        "src.agents.fixed_agents.report_upgrade.orchestrator.ReportOrchestrator.generate_report",
        new=AsyncMock(return_value={
            "title": "新能源汽车行业",
            "sections": [{
                "section_id": "industry",
                "title": "行业研究",
                "content": "industry and survey summary",
            }],
        }),
    ):
        result = await orchestrator._research_with_routing(
            user_input="先做新能源汽车行业研究，再用问卷验证需求",
            output_dir=None, user_id=None, interaction_mode=False,
            interaction_callback=None, task_id="composite_task",
        )

    assert result.status in ("completed", "completed_with_warnings")
    assert order == ["industry", "survey"]
