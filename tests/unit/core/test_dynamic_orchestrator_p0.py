"""
DynamicPhaseOrchestrator P0 修复验证测试
"""
import pytest
from src.core.dynamic_orchestrator import (
    DynamicPhaseOrchestrator,
    PhaseType,
    ContentLockRule,
)
from src.core.task_structure import (
    TaskStructure,
    SectionSpec,
    SectionRole,
    ContentDependency,
)
from src.core.semantic_intent import DeepIntentResult
from src.core.intent_types import TaskComplexity
from unittest.mock import MagicMock


def make_intent(complexity="multi", requires_survey=False):
    intent = MagicMock(spec=DeepIntentResult)
    intent.complexity = TaskComplexity.MULTI
    intent.requires_primary_data = requires_survey
    intent.recommended_skills = []
    intent.domain_context = {}
    return intent


def make_structure(sections, dependencies=None):
    ts = MagicMock(spec=TaskStructure)
    ts.sections = sections
    ts.dependencies = dependencies or []
    ts.parallel_groups = [[]]  # placeholder, will be overridden
    ts.topic = "test"
    ts.task_id = "test_task"
    return ts


# ─── Test 1: A,B,C,D,E,F DAG 场景 ───────────────────────

class TestDAGScenarioABCDEF:
    """核心场景：B,D独立→C依赖B→E依赖B,D→A,F依赖全部"""

    @pytest.fixture
    def sections(self):
        return [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="D", section_name="D", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B"], can_parallel=True),
            SectionSpec(section_id="E", section_name="E", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B", "D"], can_parallel=True),
            SectionSpec(section_id="A", section_name="A", section_role=SectionRole.SYNTHESIS,
                        content_dependency=["B", "C", "D", "E"], can_parallel=True),
            SectionSpec(section_id="F", section_name="F", section_role=SectionRole.SYNTHESIS,
                        content_dependency=["B", "C", "D", "E"], can_parallel=True),
        ]

    @pytest.fixture
    def dependencies(self, sections):
        sid = {s.section_name: s.section_id for s in sections}
        return [
            ContentDependency(from_section=sid["B"], to_section=sid["C"], dependency_type="analysis"),
            ContentDependency(from_section=sid["B"], to_section=sid["E"], dependency_type="analysis"),
            ContentDependency(from_section=sid["D"], to_section=sid["E"], dependency_type="analysis"),
            ContentDependency(from_section=sid["C"], to_section=sid["A"], dependency_type="synthesis"),
            ContentDependency(from_section=sid["E"], to_section=sid["A"], dependency_type="synthesis"),
            ContentDependency(from_section=sid["C"], to_section=sid["F"], dependency_type="synthesis"),
            ContentDependency(from_section=sid["E"], to_section=sid["F"], dependency_type="synthesis"),
        ]

    @pytest.fixture
    def ts(self, sections, dependencies):
        ts = make_structure(sections, dependencies)
        # parallel_groups = 3 layers
        ts.parallel_groups = [
            ["B", "D"],
            ["C", "E"],
            ["A", "F"],
        ]
        return ts

    def test_phase_count(self, ts):
        """验证生成 3 个 DAG phase + 1 个 REPORT phase = 4"""
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        dag_phases = [p for p in plan.phases if p.phase_type != PhaseType.REPORT]
        assert len(dag_phases) == 3

    def test_phase_order(self, ts):
        """验证 phase 顺序 = B,D → C,E → A,F"""
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        dag_phases = [p for p in plan.phases if p.phase_type != PhaseType.REPORT]
        assert dag_phases[0].section_ids == ["B", "D"], f"Got {dag_phases[0].section_ids}"
        assert dag_phases[1].section_ids == ["C", "E"], f"Got {dag_phases[1].section_ids}"
        assert dag_phases[2].section_ids == ["A", "F"], f"Got {dag_phases[2].section_ids}"

    def test_depends_on_chain(self, ts):
        """验证 depends_on = [[], [phase1], [phase2]]"""
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)

        dag_phases = [p for p in plan.phases if p.phase_type != PhaseType.REPORT]
        assert dag_phases[0].depends_on == [], f"Phase 0 should have no deps, got {dag_phases[0].depends_on}"
        assert dag_phases[1].depends_on == [dag_phases[0].phase_id], f"Phase 1 should depend on Phase 0"
        assert dag_phases[2].depends_on == [dag_phases[1].phase_id], f"Phase 2 should depend on Phase 1"

    def test_report_phase_depends_on_last_dag_phase(self, ts):
        """验证 REPORT phase 依赖最后一个 DAG phase"""
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        dag_phases = [p for p in plan.phases if p.phase_type != PhaseType.REPORT]
        report_phase = [p for p in plan.phases if p.phase_type == PhaseType.REPORT][0]
        assert report_phase.depends_on == [dag_phases[-1].phase_id]

    def test_content_lock_rules(self, ts):
        """验证 ContentLockRules 包含真实依赖"""
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)

        # C 依赖 B
        c_rules = [r for r in plan.content_lock_rules if r.target_section == "C"]
        assert len(c_rules) == 1
        assert "B" in c_rules[0].required_sections

        # E 依赖 B, D
        e_rules = [r for r in plan.content_lock_rules if r.target_section == "E"]
        assert len(e_rules) == 1
        assert "B" in e_rules[0].required_sections
        assert "D" in e_rules[0].required_sections

        # A 依赖 C, E（有 content_dependency）
        a_rules = [r for r in plan.content_lock_rules if r.target_section == "A"]
        assert len(a_rules) == 1
        assert len(a_rules[0].required_sections) >= 2

        # B 无依赖 → 无规则
        b_rules = [r for r in plan.content_lock_rules if r.target_section == "B"]
        assert len(b_rules) == 0


# ─── Test 2: 空 parallel_groups fallback ─────────────────

class TestEmptyDAGFallback:
    """parallel_groups 为空时，所有 section 归入单层"""

    def test_fallback_single_layer(self):
        sections = [
            SectionSpec(section_id="X", section_name="X", section_role=SectionRole.ANALYSIS),
            SectionSpec(section_id="Y", section_name="Y", section_role=SectionRole.ANALYSIS),
        ]
        ts = make_structure(sections)
        ts.parallel_groups = []  # empty

        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        dag_phases = [p for p in plan.phases if p.phase_type != PhaseType.REPORT]
        assert len(dag_phases) == 1
        assert set(dag_phases[0].section_ids) == {"X", "Y"}


# ─── Test 3: 空 sections ─────────────────────────────────

class TestEmptySections:
    """sections 为空时，只生成 REPORT phase"""

    def test_only_report_phase(self):
        ts = make_structure([])
        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        assert len(plan.phases) == 1
        assert plan.phases[0].phase_type == PhaseType.REPORT


# ─── Test 4: 无 ContentLockRules 自动解锁 ────────────────

class TestNoLockRulesAutoUnlock:
    """无依赖的 section 不应生成 ContentLockRule"""

    def test_no_lock_rules_for_independent_sections(self):
        sections = [
            SectionSpec(section_id="P", section_name="P", section_role=SectionRole.ANALYSIS),
            SectionSpec(section_id="Q", section_name="Q", section_role=SectionRole.ANALYSIS),
        ]
        ts = make_structure(sections)
        ts.parallel_groups = [["P", "Q"]]

        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        assert len(plan.content_lock_rules) == 0


# ─── Test 5: SURVEY + DAG ────────────────────────────────

class TestSurveyIntegration:
    """SURVEY phase 在 DAG phases 之前"""

    def test_survey_before_dag(self):
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS),
        ]
        ts = make_structure(sections)
        ts.parallel_groups = [["B"]]
        intent = make_intent(requires_survey=True)

        orchestrator = DynamicPhaseOrchestrator()
        plan = orchestrator.plan(ts, intent)
        phase_types = [p.phase_type for p in plan.phases]
        assert phase_types[0] == PhaseType.SURVEY
        assert phase_types[1] == PhaseType.ANALYSIS
        assert phase_types[-1] == PhaseType.REPORT


# ─── Test 6: 角色分类 → PhaseType ────────────────────────

class TestRoleToPhaseType:
    """SectionRole → PhaseType 映射"""

    def test_role_mapping(self):
        orchestrator = DynamicPhaseOrchestrator()
        assert orchestrator._role_to_phase_type(SectionRole.ANALYSIS) == PhaseType.ANALYSIS
        assert orchestrator._role_to_phase_type(SectionRole.SYNTHESIS) == PhaseType.SYNTHESIS
        assert orchestrator._role_to_phase_type(SectionRole.DATA_COLLECTION) == PhaseType.DATA_COLLECTION
        assert orchestrator._role_to_phase_type(SectionRole.SUPPORTING) == PhaseType.DATA_COLLECTION


# ─── Test 7: ContentLockRule 去重 ────────────────────────

class TestContentLockRuleDedup:
    """content_dependency 与 ContentDependency 可能重叠，确保去重"""

    def test_dedup(self):
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B"], can_parallel=True),
        ]
        deps = [
            ContentDependency(from_section="B", to_section="C", dependency_type="analysis"),
        ]
        ts = make_structure(sections, deps)
        ts.parallel_groups = [["B"], ["C"]]

        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        c_rules = [r for r in plan.content_lock_rules if r.target_section == "C"]
        assert len(c_rules) == 1
        # "B" appears only once in required_sections
        assert c_rules[0].required_sections.count("B") == 1
