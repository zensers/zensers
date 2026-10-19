"""Fast complete E2E for a six-chapter China smartphone industry report.

The routing, DAG planner, compatibility decomposition and scheduler are real.
Only the report writer/review boundary is deterministic so the test remains
fast and reproducible while still exercising the complete hand-off.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.fixed_agents.report_upgrade.models import (
    ChapterReviewOutput,
    ChapterWriteOutput,
    ReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator
from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
from src.core.orchestrator.execution.scheduler import ExecutionScheduler
from src.core.task_structure import ContentDependency, SectionRole, SectionSpec, TaskStructure


TOPIC = "中国智能手机行业分析"
CHAPTERS = [
    "市场规模与出货量",
    "品牌竞争格局",
    "产品结构与价格带",
    "渠道与用户需求",
    "芯片与操作系统生态",
    "政策环境与未来趋势",
]


@dataclass
class _Provenance:
    source_key: str
    section_target: str
    stage: str = "analysis"


class _Aggregation:
    def __init__(self, section_ids, agent_ids):
        self.sources = [
            {"source_id": "source_cn_smartphone_1", "url": "https://example.test/source"}
        ]
        self.conflicts = []
        self.stats = {"section_count": len(section_ids)}
        self.data = {"data_points": []}
        self.layered_content = {"analysis": {}}
        self.content_provenance = {}
        for section_id, agent_id in zip(section_ids, agent_ids):
            self.layered_content["analysis"][agent_id] = {
                "content": f"{section_id}的行业研究内容，包含出货量、竞争和趋势分析。",
                "data_points": [{
                    "metric": "出货量",
                    "value": "待核实",
                    "unit": "台",
                    "evidence_id": f"ev_{section_id}",
                    "source_url": "https://example.test/source",
                }],
            }
            self.content_provenance[agent_id] = _Provenance(
                source_key=agent_id,
                section_target=section_id,
            )


def _intent():
    from src.core.intent_types import TaskComplexity

    return SimpleNamespace(
        complexity=TaskComplexity.MULTI,
        requires_primary_data=False,
        used_fallback=False,
        forensic_mode=False,
    )


def _six_chapter_structure():
    dependencies = {
        "section_2": ["section_0"],
        "section_3": ["section_0"],
        "section_4": ["section_1"],
    }
    sections = [
        SectionSpec(
            section_id=f"section_{index}",
            section_name=name,
            section_role=SectionRole.ANALYSIS,
            content_dependency=dependencies.get(f"section_{index}", []),
        )
        for index, name in enumerate(CHAPTERS)
    ]
    content_dependencies = [
        ContentDependency(from_section=source, to_section=target, dependency_type="analysis")
        for target, sources in dependencies.items()
        for source in sources
    ]
    # Deliberately invalid: dependent chapters appear before their upstream
    # chapters. The routing adapter must repair and re-audit this locally.
    bad_layers = [["section_2", "section_3", "section_4"], ["section_0", "section_1", "section_5"]]
    return TaskStructure(
        task_id="smartphone-6-chapter-e2e",
        topic=TOPIC,
        sections=sections,
        dependencies=content_dependencies,
        parallel_groups=bad_layers,
        total_estimated_agents=len(sections),
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smartphone_six_chapter_full_routing_to_report():
    structure = _six_chapter_structure()
    adapter = IntelligentRoutingAdapter(use_llm=False, enable_content_lock=False)
    adapter._analyze_intent = lambda *_args, **_kwargs: _intent()
    adapter._analyze_structure = lambda *_args, **_kwargs: structure

    result = adapter.analyze(
        TOPIC,
        {"topic": TOPIC, "aspects": CHAPTERS},
        TOPIC,
    )

    assert result.dag_audit.passed is True
    assert len(result.task_structure.sections) == 6
    assert len(result.dag_review_history) == 2
    assert result.dag_review_history[0]["passed"] is False
    assert result.dag_review_history[1]["passed"] is True
    assert result.dag_document["document_type"] == "intelligent_routing_dag"
    assert len(result.dag_document["sections"]) == 6

    # The plan actually handed to the scheduler must contain only executable
    # Agent IDs, and all six chapter agents must be schedulable.
    specs = [spec for phase_specs in result.decomposition_plan.phases.values() for spec in phase_specs]
    agents = [SimpleNamespace(agent_id=spec.agent_id) for spec in specs]
    batches = ExecutionScheduler().schedule_from_decomposition(result.decomposition_plan, agents)
    scheduled = {agent_id for batch in batches for agent_id in batch}
    assert scheduled == {spec.agent_id for spec in specs}

    chapter_specs = [spec for spec in specs if getattr(spec, "output_keys", [])]
    section_ids = [spec.output_keys[0] for spec in chapter_specs]
    aggregation = _Aggregation(section_ids, [spec.agent_id for spec in chapter_specs])
    writer = AsyncMock()

    async def write_chapter(request):
        chapter_id = request.chapter_spec["section_id"]
        return ChapterWriteOutput(
            chapter_id=chapter_id,
            title=request.chapter_spec["section_name"],
            content=f"### {request.chapter_spec['section_name']}\n基于可追溯证据的分析。",
        )

    writer.write.side_effect = write_chapter
    reviewer = AsyncMock()
    reviewer.review.return_value = ChapterReviewOutput(passed=True, score=90)
    global_reviewer = AsyncMock()
    global_reviewer.review.return_value = ReviewOutput(overall_score=90)
    report_orchestrator = ReportOrchestrator(
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        prompt_manager=PromptManager(),
    )

    task_structure = {
        "topic": TOPIC,
        "sections": [section.to_dict() for section in result.task_structure.sections],
    }
    report = await report_orchestrator.generate_report(
        task_structure=task_structure,
        framework_config={"name": "中国智能手机行业分析"},
        aggregated_result=aggregation,
        topic=TOPIC,
    )

    assert len(report["sections"]) == 6
    assert [section["id"] for section in report["sections"]] == section_ids
    assert all(section.get("content") for section in report["sections"])
    assert report["sources"]
    assert writer.write.await_count == 6
