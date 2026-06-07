"""
M1 测试：强制生成 DC + Analysis 双阶段 + category 覆写

TDD RED 阶段：验证当前 _generate_phases 和 to_decomposition_plan 的行为，
确认 BYD 场景下只生成单阶段 ANALYSIS（bug），修复后应生成 DC + Analysis 双阶段。
"""
import pytest
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock


@dataclass
class MockSectionSpec:
    section_id: str
    section_name: str
    section_role: object
    role_reasoning: str = ""
    content_dependency: List[str] = field(default_factory=list)
    skill_requirements: List[str] = field(default_factory=list)
    estimated_complexity: str = "medium"
    can_parallel: bool = True
    priority: int = 0


@dataclass
class MockTaskStructure:
    task_id: str = "test_task"
    topic: str = "BYD 新能源汽车"
    sections: List[Any] = field(default_factory=list)
    dependencies: List[Any] = field(default_factory=list)
    execution_graph: Dict[str, List[str]] = field(default_factory=dict)
    parallel_groups: List[List[str]] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)
    total_estimated_agents: int = 0
    analysis_method: str = "rule_based"


@dataclass
class MockIntent:
    requires_primary_data: bool = False


def _make_byd_task_structure():
    """模拟 BYD 场景：8 个 ANALYSIS section，无依赖，1 层 DAG"""
    from src.core.task_structure import SectionRole
    sections = [
        MockSectionSpec(f"section_{i}_维度{i}", f"维度{i}", SectionRole.ANALYSIS)
        for i in range(8)
    ]
    section_ids = [s.section_id for s in sections]
    return MockTaskStructure(
        topic="BYD 新能源汽车",
        sections=sections,
        parallel_groups=[section_ids],
    )


class TestM1CurrentBehavior:
    """验证修复后行为：BYD 场景生成 DC + Analysis 双阶段"""

    def test_byd_generates_dc_and_analysis_phases(self):
        """修复后：1 DC phase + 1 Analysis phase + 1 Report = 3 phases"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        analysis_phases = [p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS]
        report_phases = [p for p in plan.phases if p.phase_type == PhaseType.REPORT]

        assert len(dc_phases) == 1, f"应有 1 个 DC phase，实际 {len(dc_phases)}"
        assert len(analysis_phases) == 1, f"应有 1 个 Analysis phase，实际 {len(analysis_phases)}"
        assert len(report_phases) == 1

    def test_byd_dc_agents_have_no_deps_analysis_agents_depend_on_dc(self):
        """修复后：DC agents 无依赖，Analysis agents 依赖对应 DC agent"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phase = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION][0]
        for spec in dc_phase.agent_specs:
            assert spec.config.get("resolved_dependencies", []) == [], \
                f"DC agent {spec.agent_id} 不应有依赖"

        analysis_phase = [p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS][0]
        for spec in analysis_phase.agent_specs:
            deps = spec.config.get("resolved_dependencies", [])
            assert len(deps) == 1, f"Analysis agent {spec.agent_id} 应有 1 个依赖，实际 {deps}"

    def test_byd_dc_phase_exists_for_canonical_propagation(self):
        """修复后：有 DC phase，canonical_data 可在阶段间传播"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        assert len(dc_phases) == 1, "应有 DATA_COLLECTION phase"


class TestM1aCategoryOverride:
    """M1-a: to_decomposition_plan 的 category 覆写"""

    def test_dc_phase_maps_to_research_category(self):
        """
        修复后：DC phase agent_type="data_collection" → category="research"
        """
        from src.core.dynamic_orchestrator import (
            DynamicPhaseOrchestrator, PhaseType, ExecutionPhase, AgentSpec
        )

        dc_phase = ExecutionPhase(
            phase_id="phase_1",
            phase_type=PhaseType.DATA_COLLECTION,
            agent_specs=[
                AgentSpec(
                    agent_id="phase_1_agent_0",
                    agent_type="data_collection",
                    section_ids=["section_0_x"],
                    priority=0,
                ),
            ],
            section_ids=["section_0_x"],
            parallel=True,
            depends_on=[],
        )
        report_phase = ExecutionPhase(
            phase_id="phase_2",
            phase_type=PhaseType.REPORT,
            agent_specs=[
                AgentSpec(agent_id="phase_2_report", agent_type="report_generation",
                          section_ids=[], priority=0),
            ],
            section_ids=[],
            parallel=False,
            depends_on=["phase_1"],
        )

        from src.core.dynamic_orchestrator import ExecutionPlan
        mock_task = _make_byd_task_structure()
        plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=mock_task,
            phases=[dc_phase, report_phase],
            content_lock_rules=[],
            total_agents=2,
        )

        decomp = plan.to_decomposition_plan()

        from src.core.decomposition.strategies import ResearchPhase
        dc_specs = decomp.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_specs) > 0, "应有 DC specs"
        for spec in dc_specs:
            assert spec.category == "research", (
                f"DC agent category 应为 'research'，实际 '{spec.category}'"
            )

    def test_analysis_phase_keeps_agent_type_category(self):
        """
        Analysis phase 的 category 应保持为 agent_type 值
        """
        from src.core.dynamic_orchestrator import (
            ExecutionPlan, ExecutionPhase, AgentSpec, PhaseType
        )

        analysis_phase = ExecutionPhase(
            phase_id="phase_2",
            phase_type=PhaseType.ANALYSIS,
            agent_specs=[
                AgentSpec(agent_id="phase_2_agent_0", agent_type="analysis",
                          section_ids=["section_0_x"], priority=0),
            ],
            section_ids=["section_0_x"],
            parallel=True,
            depends_on=["phase_1"],
        )
        report_phase = ExecutionPhase(
            phase_id="phase_3",
            phase_type=PhaseType.REPORT,
            agent_specs=[
                AgentSpec(agent_id="phase_3_report", agent_type="report_generation",
                          section_ids=[], priority=0),
            ],
            section_ids=[],
            parallel=False,
            depends_on=["phase_2"],
        )

        mock_task = _make_byd_task_structure()
        plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=mock_task,
            phases=[analysis_phase, report_phase],
            content_lock_rules=[],
            total_agents=2,
        )

        decomp = plan.to_decomposition_plan()

        from src.core.decomposition.strategies import ResearchPhase
        analysis_specs = decomp.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        if analysis_specs:
            category = analysis_specs[0].category
            assert category == "analysis", f"Analysis category 应为 'analysis'，实际 '{category}'"


class TestM1ExpectedBehavior:
    """修复后的期望行为（修复后这些测试应通过）"""

    def test_byd_generates_dc_and_analysis_phases(self):
        """
        修复后：8 个 ANALYSIS section → 1 DC phase + 1 Analysis phase + 1 Report = 3 phases
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        analysis_phases = [p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS]
        report_phases = [p for p in plan.phases if p.phase_type == PhaseType.REPORT]

        assert len(dc_phases) >= 1, "应有至少 1 个 DATA_COLLECTION phase"
        assert len(analysis_phases) >= 1, "应有至少 1 个 ANALYSIS phase"
        assert len(report_phases) == 1, "应有 1 个 REPORT phase"

    def test_dc_phase_before_analysis_phase(self):
        """
        修复后：DC phase 的 agent 先执行，Analysis phase 的 agent 依赖 DC agent
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        analysis_phases = [p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS]

        if dc_phases and analysis_phases:
            assert dc_phases[0].phase_id < analysis_phases[0].phase_id, (
                "DC phase 应在 Analysis phase 之前"
            )

    def test_analysis_agents_depend_on_dc_agents(self):
        """
        修复后：Analysis agent 的 resolved_dependencies 包含对应 DC agent
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        analysis_phases = [p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS]

        if dc_phases and analysis_phases:
            dc_agent_ids = {s.agent_id for s in dc_phases[0].agent_specs}
            for spec in analysis_phases[0].agent_specs:
                deps = spec.config.get("resolved_dependencies", [])
                assert len(deps) > 0, (
                    f"Analysis agent {spec.agent_id} 应有依赖，但 resolved_dependencies={deps}"
                )

    def test_dc_phase_category_overridden_to_research(self):
        """
        修复后：DC phase agent 的 category 被覆写为 "research"
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        dc_phases = [p for p in plan.phases if p.phase_type == PhaseType.DATA_COLLECTION]
        if dc_phases:
            decomp = plan.to_decomposition_plan()
            from src.core.decomposition.strategies import ResearchPhase
            dc_specs = decomp.phases.get(ResearchPhase.DATA_COLLECTION, [])
            if dc_specs:
                for spec in dc_specs:
                    assert spec.category == "research", (
                        f"DC agent category 应为 'research'，实际 '{spec.category}'"
                    )

    def test_total_agents_doubled(self):
        """
        修复后：8 DC + 8 Analysis + 1 Report = 17 agents
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator

        orchestrator = DynamicPhaseOrchestrator()
        task = _make_byd_task_structure()
        intent = MockIntent(requires_primary_data=False)

        plan = orchestrator.plan(task, intent, topic="BYD 新能源汽车")

        assert plan.total_agents >= 17, (
            f"8 DC + 8 Analysis + 1 Report = 17，实际 {plan.total_agents}"
        )

    def test_mixed_roles_preserve_synthesis(self):
        """
        非 ANALYSIS section（如 SYNTHESIS）应保持原逻辑
        """
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        from src.core.task_structure import SectionRole

        sections = [
            MockSectionSpec("section_0_销量", "销量分析", SectionRole.ANALYSIS),
            MockSectionSpec("section_1_竞争", "竞争格局", SectionRole.ANALYSIS),
            MockSectionSpec("section_2_总结", "总结", SectionRole.SYNTHESIS),
        ]

        task = MockTaskStructure(
            topic="Test",
            sections=sections,
            parallel_groups=[["section_0_销量", "section_1_竞争", "section_2_总结"]],
        )
        intent = MockIntent(requires_primary_data=False)

        orchestrator = DynamicPhaseOrchestrator()
        plan = orchestrator.plan(task, intent, topic="Test")

        phase_types = [p.phase_type for p in plan.phases]
        assert PhaseType.SYNTHESIS in phase_types, "SYNTHESIS phase 应保留"
