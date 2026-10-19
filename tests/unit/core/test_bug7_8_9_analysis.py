"""
测试验证 BUG 7、8、9 的存在 — 先写测试证明 BUG，再修复
"""
import pytest
from unittest.mock import MagicMock
from typing import List

from src.core.dynamic_orchestrator import (
    DynamicPhaseOrchestrator, PhaseType, ExecutionPlan, AgentSpec, ExecutionPhase
)
from src.core.task_structure import TaskStructure, SectionSpec, SectionRole, ContentDependency
from src.core.semantic_intent import DeepIntentResult
from src.core.decomposition.strategies import DecompositionPlan
from src.core.intent_types import TaskComplexity


# Helper
def make_intent(complexity="multi", requires_survey=False):
    intent = MagicMock(spec=DeepIntentResult)
    intent.complexity = TaskComplexity.MULTI
    intent.requires_primary_data = requires_survey
    intent.recommended_skills = []
    intent.domain_context = {}
    return intent


# =============================================================================
# BUG 7: to_decomposition_plan() 读取 spec.dependencies（永远是 []）
#        正确值在 spec.config["resolved_dependencies"] 中
# =============================================================================

class TestBug7_DependenciesField:
    """验证 to_decomposition_plan() 依赖字段读取位置错误"""

    def test_create_phase_writes_deps_to_config_not_spec(self):
        """_create_phase 将依赖写入 config['resolved_dependencies']，而非 spec.dependencies"""
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B"], can_parallel=True),
        ]
        orchestrator = DynamicPhaseOrchestrator()
        phase = orchestrator._create_phase("phase_1", PhaseType.ANALYSIS, sections,
                                           MagicMock(), "test", parallel=True)

        for spec in phase.agent_specs:
            # 1) spec.dependencies 永远是 []（从未被写入）
            assert spec.dependencies == [], \
                f"spec.dependencies should be [], got {spec.dependencies}"
            # 2) 但 config["resolved_dependencies"] 有正确数据
            if "agent_1" in spec.agent_id:
                # C → depends on B
                assert len(spec.config.get("resolved_dependencies", [])) > 0, \
                    f"C should have deps in config, got {spec.config.get('resolved_dependencies')}"

    def test_to_decomposition_plan_propagates_deps_correctly(self):
        """验证 BUG 7 修复: to_decomposition_plan 从 config['resolved_dependencies'] 读取依赖"""
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B"], can_parallel=True),
        ]
        deps = [
            ContentDependency(from_section="B", to_section="C", dependency_type="analysis"),
        ]
        ts = MagicMock(spec=TaskStructure)
        ts.sections = sections
        ts.dependencies = deps
        ts.parallel_groups = [["B"], ["C"]]
        ts.topic = "test"
        ts.task_id = "test_task"

        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        decomp_plan = plan.to_decomposition_plan()

        # 收集 agent_id → dependencies 映射
        agent_deps = {}
        for phase, specs in decomp_plan.phases.items():
            for spec in specs:
                agent_deps[spec.agent_id] = spec.dependencies

        # B agent (phase_1_agent_0) → 无依赖
        assert "phase_1_agent_0" in agent_deps, f"Missing phase_1_agent_0, keys={list(agent_deps.keys())}"
        assert agent_deps["phase_1_agent_0"] == [], \
            f"B should have no deps, got {agent_deps['phase_1_agent_0']}"

        # C agent (phase_2_agent_0) → 依赖 phase_1_agent_0 (跨 phase 解析)
        assert "phase_2_agent_0" in agent_deps, f"Missing phase_2_agent_0, keys={list(agent_deps.keys())}"
        assert agent_deps["phase_2_agent_0"] == ["phase_1_agent_0"], \
            f"C should depend on phase_1_agent_0, got {agent_deps['phase_2_agent_0']}"

    def test_to_decomposition_plan_uses_config_deps(self):
        """验证 BUG 7 修复: to_decomposition_plan 从 config 取 deps 而非 spec.dependencies"""
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                        content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B"], can_parallel=True),
            SectionSpec(section_id="D", section_name="D", section_role=SectionRole.ANALYSIS,
                        content_dependency=["B", "C"], can_parallel=True),
        ]
        ts = MagicMock(spec=TaskStructure)
        ts.sections = sections
        ts.dependencies = []
        ts.parallel_groups = [["B", "C", "D"]]
        ts.topic = "test"
        ts.task_id = "test_task"

        orchestrator = DynamicPhaseOrchestrator()
        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        decomp_plan = plan.to_decomposition_plan()

        agent_deps = {}
        for phase, specs in decomp_plan.phases.items():
            for spec in specs:
                agent_deps[spec.agent_id] = spec.dependencies

        # B analysis agent (phase_2): depends on DC agent (phase_1)
        b_analysis = [k for k in agent_deps if k.startswith("phase_2") and "agent_0" in k]
        assert len(b_analysis) == 1, f"Expected 1 B analysis agent, got {b_analysis}"
        assert len(agent_deps[b_analysis[0]]) >= 1, \
            f"B analysis should depend on DC, got {agent_deps[b_analysis[0]]}"

        # C analysis agent (phase_2): depends on B's DC + B's analysis
        c_analysis = [k for k in agent_deps if k.startswith("phase_2") and "agent_1" in k]
        assert len(c_analysis) == 1, f"Expected 1 C analysis agent, got {c_analysis}"
        assert len(agent_deps[c_analysis[0]]) > 0, \
            f"C analysis should have deps, got empty"

        # D analysis agent (phase_2): depends on B + C
        d_analysis = [k for k in agent_deps if k.startswith("phase_2") and "agent_2" in k]
        assert len(d_analysis) == 1, f"Expected 1 D analysis agent, got {d_analysis}"
        assert len(agent_deps[d_analysis[0]]) >= 2, \
            f"D analysis should have 2+ deps, got {agent_deps[d_analysis[0]]}"


# =============================================================================
# BUG 8: _create_agents_from_plan() 不传递 section_id 到 agent context
#        导致 agent.section_id = "" → 内容锁 fallback 到 agent_id
# =============================================================================

class TestBug8_SectionIdNotSet:
    """验证 agent.section_id = "" 导致 _get_section_id_from_agent 返回 agent_id"""

    def test_output_keys_contain_section_id(self):
        """验证 spec.section_ids 包含 section_id，可用于设置 agent.section_id"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, AgentSpec as DynamicAgentSpec, ExecutionPhase

        # 构造一个 ExecutionPhase，其中 agent 有 section_ids
        sections = [
            SectionSpec(section_id="section_0_core_financial", section_name="core_financial",
                        section_role=SectionRole.ANALYSIS),
        ]
        orchestrator = DynamicPhaseOrchestrator()
        phase = orchestrator._create_phase("phase_1", PhaseType.ANALYSIS, sections,
                                           MagicMock(), "test", parallel=True)

        # spec.section_ids 包含正确的 section_id
        spec = phase.agent_specs[0]
        assert spec.section_ids == ["section_0_core_financial"], \
            f"section_ids should contain section_id, got {spec.section_ids}"

        # to_decomposition_plan 将其映射到 output_keys
        ts = MagicMock(spec=TaskStructure)
        ts.sections = sections
        ts.dependencies = []
        ts.parallel_groups = [["section_0_core_financial"]]
        ts.topic = "test"
        ts.task_id = "test_task"

        intent = make_intent()
        plan = orchestrator.plan(ts, intent)
        decomp_plan = plan.to_decomposition_plan()

        # 验证 non-report, non-calibration agent 的 output_keys 包含 section_id
        found = False
        for phase_type, specs in decomp_plan.phases.items():
            for spec in specs:
                if spec.agent_type in ("report_generation", "calibration"):
                    continue
                found = True
                assert "section_0_core_financial" in spec.output_keys, \
                    f"output_keys should contain section_id, got {spec.output_keys}"
                assert spec.output_keys[0] == "section_0_core_financial", \
                    f"BUG 8 fix: expected section_0_core_financial, got {spec.output_keys[0]}"

        assert found, "No non-report agents found in decomposition plan"

    def test_empty_section_id_causes_fallback_to_agent_id(self):
        """验证 engine._get_section_id_from_agent 在 section_id='' 时回退到 agent_id"""
        # 模拟有 section_id 属性但为空的 agent
        class MockAgent:
            agent_id = "phase_2_agent_6"
            section_id = ""

        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = MagicMock(spec=ExecutionEngine)

        # 使用实际的 _get_section_id_from_agent 逻辑
        def get_section_id_from_agent(agent):
            if hasattr(agent, 'section_id') and agent.section_id:
                return agent.section_id
            return agent.agent_id

        agent = MockAgent()
        result = get_section_id_from_agent(agent)

        # section_id="" → falsy → 返回 agent_id
        assert result == "phase_2_agent_6", \
            f"BUG 8: expected 'phase_2_agent_6' (agent_id fallback), got '{result}'"

    def test_content_lock_cannot_find_agent_id_as_section(self):
        """内容锁注册表存的是 section_id，传 agent_id 时走 not-registered 宽松路径"""
        from src.core.content_lock import ContentLockManager, SectionState
        from src.core.dynamic_orchestrator import ContentLockRule

        # 模拟一个 ContentLockManager，只有 section_id 注册表
        ts = MagicMock(spec=TaskStructure)
        ts.sections = [
            MagicMock(section_id="section_0_core_financial"),
        ]
        ts.dependencies = []

        plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=ts,
            phases=[],
            content_lock_rules=[],
        )

        lock_manager = ContentLockManager(plan)

        # 用 agent_id 查询 — 不在注册表中，走宽松策略 (允许执行)
        can_exec, reason = lock_manager.can_execute("phase_2_agent_6")
        assert can_exec, "Unregistered section_id should be allowed (permissive)"
        assert "not registered" in reason.lower(), \
            f"Expected 'not registered' reason, got: {reason}"

        # 用正确的 section_id 查询 — 能找到且可执行
        can_exec, reason = lock_manager.can_execute("section_0_core_financial")
        assert can_exec, \
            f"Should be able to execute with correct section_id, but got: {reason}"


# =============================================================================
# BUG 9: await list — validate_section 是同步方法，await 抛 TypeError
# =============================================================================

class TestBug9_AwaitOnSyncMethod:
    """验证 validate_section 是同步方法，await 会失败"""

    def test_validate_section_is_not_async(self):
        """validate_section 不是 async 方法，直接返回 list"""
        from src.core.data.canonical_registry import CanonicalDataRegistry

        registry = CanonicalDataRegistry()
        result = registry.validate_section("test content", [])

        assert isinstance(result, list), \
            f"Expected list, got {type(result)}"

        import asyncio
        assert not asyncio.iscoroutine(result), \
            f"validate_section should not return a coroutine"

    def test_await_validate_section_raises_typeerror(self):
        """await validate_section() 抛 TypeError: object list can't be used in 'await' expression"""
        import asyncio

        async def bad_await():
            from src.core.data.canonical_registry import CanonicalDataRegistry
            registry = CanonicalDataRegistry()
            # BUG: await 同步方法！
            result = await registry.validate_section("test", [])
            return result

        with pytest.raises(TypeError) as excinfo:
            asyncio.run(bad_await())

        assert "can't be used in 'await'" in str(excinfo.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
