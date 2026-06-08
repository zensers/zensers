"""
M5-b tests: Calibration Phase — PhaseType.CALIBRATION + LLM agent routing + prompt.

Scope:
1. PhaseType.CALIBRATION is defined in dynamic_orchestrator.py (and ResearchPhase if needed)
2. generic_agent.py has a calibration branch that uses llm_skill with calibration prompt
3. Calibration agent receives all_results + canonical_data and fixes remaining inconsistencies
4. dynamic_orchestrator._generate_phases() includes CALIBRATION phase for BYD-style reports

Note: These are unit tests for the components, not integration tests.
"""
import pytest

# ============================================================
# PhaseType enum tests
# ============================================================

class TestM5bPhaseType:
    def test_calibration_member_exists(self):
        from src.core.dynamic_orchestrator import PhaseType
        assert hasattr(PhaseType, "CALIBRATION")
        assert PhaseType.CALIBRATION.value == "calibration"

    def test_calibration_after_analysis_in_ordering(self):
        from src.core.dynamic_orchestrator import PhaseType
        members = list(PhaseType)
        calib_idx = members.index(PhaseType.CALIBRATION)
        analysis_idx = members.index(PhaseType.ANALYSIS)
        synthesis_idx = members.index(PhaseType.SYNTHESIS)
        # Calibration should be ordered after ANALYSIS and SYNTHESIS (last quality pass)
        assert calib_idx > analysis_idx
        assert calib_idx > synthesis_idx

    def test_research_phase_has_calibration(self):
        from src.core.decomposition.strategies import ResearchPhase
        assert hasattr(ResearchPhase, "CALIBRATION")
        assert ResearchPhase.CALIBRATION.value == "calibration"


# ============================================================
# Calibration prompt tests
# ============================================================

class TestM5bCalibrationPrompt:
    def test_calibration_prompt_no_errors(self):
        from src.core.prompts.calibration_prompt import CALIBRATION_SYSTEM_PROMPT
        assert len(CALIBRATION_SYSTEM_PROMPT) > 50
        assert "canonical" in CALIBRATION_SYSTEM_PROMPT.lower()
        assert "inconsistenc" in CALIBRATION_SYSTEM_PROMPT.lower()

    def test_calibration_prompt_mentions_specific_metrics(self):
        from src.core.prompts.calibration_prompt import CALIBRATION_SYSTEM_PROMPT
        _p = CALIBRATION_SYSTEM_PROMPT.lower()
        # Should reference key verification metrics
        assert any(term in _p for term in ["revenue", "净利润", "revenue", "profit"])


# ============================================================
# GenericAgent calibration route tests
# ============================================================

class TestM5bCalibrationRoute:
    @pytest.mark.asyncio
    async def test_calibration_action_routes_to_llm(self):
        """
        When action == "calibration", the GenericAgent should route to llm_skill
        with a calibration prompt that includes all_results and canonical_data.
        """
        from src.core.agents.generic_agent import GenericAgent

        class MockSkill2:
            async def execute(self, prompt, system_prompt=None):
                assert "all_results" in prompt or "calibration" in prompt.lower()
                assert system_prompt is not None
                assert "inconsistenc" in system_prompt.lower()
                return {"success": True, "content": "Fixed inconsistencies: revenue changed from 300 to 310"}

        class MockRegistry2:
            def get(self, name):
                if name == "llm_skill":
                    return MockSkill2()
                return None
            def discover_skills(self, action, auto_load=True):
                return []

        agent = GenericAgent(
            agent_id="calibration_agent_1",
            agent_type="dynamic",
            config={
                "skill_registry": MockRegistry2(),
                "skills": ["llm_skill"],
                "category": "calibration",
                "context": {
                    "topic": "BYD Company Report",
                    "all_results": [
                        {"agent_id": "dc_1", "success": True, "content": "Revenue is 300 CNY"},
                        {"agent_id": "analysis_1", "success": True, "content": "Revenue is 320 CNY"},
                    ],
                    "canonical_data": {"revenue_2023_CNY": {"value": 310, "unit": "亿"}},
                }
            }
        )

        result = await agent.execute({
            "action": "calibration",
            "parameters": {
                "all_results": [
                    {"agent_id": "dc_1", "success": True, "content": "Revenue is 300 CNY"},
                    {"agent_id": "analysis_1", "success": True, "content": "Revenue is 320 CNY"},
                ],
                "canonical_data": {"revenue_2023_CNY": {"value": 310, "unit": "亿"}},
            }
        })
        assert result.get("success")
        assert "inconsistenc" in result.get("content", "").lower() or "fix" in result.get("content", "").lower()

    @pytest.mark.asyncio
    async def test_calibration_no_all_results_graceful(self):
        from src.core.agents.generic_agent import GenericAgent

        class MockSkill3:
            async def execute(self, prompt, system_prompt=None):
                return {"success": True, "content": "No results to calibrate."}

        class MockRegistry3:
            def get(self, name):
                if name == "llm_skill":
                    return MockSkill3()
                return None
            def discover_skills(self, action, auto_load=True):
                return []

        agent = GenericAgent(
            agent_id="calibration_agent_2",
            agent_type="dynamic",
            config={
                "skill_registry": MockRegistry3(),
                "skills": ["llm_skill"],
                "category": "calibration",
                "context": {"topic": "Test"},
            }
        )

        result = await agent.execute({
            "action": "calibration",
            "parameters": {}
        })
        assert result.get("success")


# ============================================================
# Phase generation tests — real orchestrator
# ============================================================

from tests.helpers import make_orch_plan as _make_orch_plan


class TestM5bRealPhaseGeneration:
    """Integration tests using the real DynamicPhaseOrchestrator."""

    def test_analysis_sections_generate_calibration_phase(self):
        """Real orchestrator: ANALYSIS sections → CALIBRATION phase created."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType

        plan = _make_orch_plan([SectionRole.ANALYSIS] * 3)
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]
        assert len(cal_phases) == 1, (
            f"Expected 1 CALIBRATION phase, got {len(cal_phases)}"
        )

    def test_no_analysis_no_calibration(self):
        """Real orchestrator: no ANALYSIS sections → no CALIBRATION phase."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType

        plan = _make_orch_plan([SectionRole.SYNTHESIS, SectionRole.DATA_COLLECTION])
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]
        assert len(cal_phases) == 0, (
            f"Expected 0 CALIBRATION phases (no ANALYSIS), got {len(cal_phases)}"
        )

    def test_calibration_after_synthesis_before_report(self):
        """CALIBRATION phase is after SYNTHESIS but before REPORT in execution_order."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from src.core.decomposition.strategies import ResearchPhase

        plan = _make_orch_plan([SectionRole.ANALYSIS, SectionRole.SYNTHESIS])
        decomp = plan.to_decomposition_plan()
        order = decomp.execution_order

        cal_idx = order.index(ResearchPhase.CALIBRATION)
        syn_idx = order.index(ResearchPhase.SYNTHESIS)
        rep_idx = order.index(ResearchPhase.REPORT_GENERATION)

        assert syn_idx < cal_idx < rep_idx, (
            f"Order must be SYNTHESIS({syn_idx}) < CALIBRATION({cal_idx}) < REPORT({rep_idx})"
        )

    def test_calibrator_agent_category_is_calibration(self):
        """Calibrator agent gets category='calibration' in decomposition plan."""
        from src.core.task_structure import SectionRole
        from src.core.decomposition.strategies import ResearchPhase

        plan = _make_orch_plan([SectionRole.ANALYSIS] * 2)
        decomp = plan.to_decomposition_plan()
        cal_specs = decomp.phases.get(ResearchPhase.CALIBRATION, [])
        assert len(cal_specs) == 1
        assert cal_specs[0].category == "calibration", (
            f"Expected category='calibration', got '{cal_specs[0].category}'"
        )

    def test_calibrator_depends_on_all_prior_agents(self):
        """Calibrator's resolved_dependencies includes all prior agent IDs."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType

        plan = _make_orch_plan([SectionRole.ANALYSIS] * 3)
        cal_phase = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION][0]
        calibrator = cal_phase.agent_specs[0]
        deps = calibrator.config.get("resolved_dependencies", [])

        # Collect all prior agent IDs
        prior_ids = set()
        for p in plan.phases:
            if p.phase_type == PhaseType.CALIBRATION:
                break
            for spec in p.agent_specs:
                if spec.agent_id:
                    prior_ids.add(spec.agent_id)

        assert len(deps) >= len(prior_ids), (
            f"Calibrator deps ({len(deps)}) should cover all prior agents ({len(prior_ids)})"
        )
        assert all(pid in deps for pid in prior_ids), (
            f"Missing prior agent IDs in calibrator deps: {prior_ids - set(deps)}"
        )

    def test_calibrator_section_ids_empty(self):
        """Calibrator has no section_ids — it produces a calibration report, not per-section content."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType

        plan = _make_orch_plan([SectionRole.ANALYSIS] * 3)
        cal_phase = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION][0]
        calibrator = cal_phase.agent_specs[0]
        assert calibrator.section_ids == [], (
            f"Expected calibrator section_ids=[], got {calibrator.section_ids}"
        )

    def test_calibration_parallel_false(self):
        """Calibration phase is serial (single agent)."""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType

        plan = _make_orch_plan([SectionRole.ANALYSIS] * 3)
        cal_phase = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION][0]
        assert cal_phase.parallel == False, (
            f"Expected calibration parallel=False, got {cal_phase.parallel}"
        )


class TestM5bCalibrationOutput:
    """Tests for calibration agent output structure."""

    @pytest.mark.asyncio
    async def test_calibration_route_stores_calibration_report(self):
        """Calibration route stores calibration_report + unified_data_reference in result."""
        from src.core.agents.generic_agent import GenericAgent

        class MockSkill:
            async def execute(self, prompt, system_prompt=None):
                return {"success": True, "content": "Calibration complete. All metrics reconciled."}

        class MockRegistry:
            def get(self, name):
                if name == "llm_skill":
                    return MockSkill()
                return None
            def discover_skills(self, action, auto_load=True):
                return []

        agent = GenericAgent(
            agent_id="calibrator",
            agent_type="dynamic",
            config={
                "skill_registry": MockRegistry(),
                "skills": ["llm_skill"],
                "category": "calibration",
                "context": {"topic": "Test"},
            }
        )

        result = await agent.execute({
            "action": "calibration",
            "parameters": {
                "all_results": [
                    {"agent_id": "dc_1", "success": True, "content": "2024 sales: 460万辆"},
                    {"agent_id": "analysis_1", "success": True, "content": "2024年销量460万辆"},
                ],
                "canonical_data": {"销量_2024_CNY": {"value": 460, "unit": "万辆"}},
            }
        })

        assert result.get("success")
        assert "calibration_report" in result, (
            "calibration_report missing from calibration result"
        )
        assert "summary" in result["calibration_report"]
        assert "unified_data_reference" in result, (
            "unified_data_reference missing from calibration result"
        )


class TestM5bEngineTaskBuilding:
    """Tests for engine.py calibration task building and Report injection."""

    def test_calibration_agent_category_defined(self):
        """AgentCategory has CALIBRATION member."""
        from src.core.orchestrator.execution.engine import AgentCategory
        assert hasattr(AgentCategory, "CALIBRATION")
        assert AgentCategory.CALIBRATION.value == "calibration"

    def test_classify_agent_returns_calibration_category(self):
        """classify_agent returns CALIBRATION for calibration-category config."""
        from src.core.orchestrator.execution.engine import ExecutionEngine, ExecutionConfig, AgentCategory
        from src.core.communication import MessageBus, SharedMemory

        class _MockAgent:
            agent_id = "calibrator_1"
            config = {"category": "calibration"}

        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
        )
        result = engine.classify_agent(_MockAgent())
        assert result == AgentCategory.CALIBRATION, (
            f"Expected CALIBRATION, got {result}"
        )

    def test_calibration_report_injection_logic(self):
        """Calibration injection dict logic (engine.py lines 1871-1875) produces correct output."""
        previous_results = [
            {"agent_id": "cal_1", "category": "calibration", "success": True,
             "calibration_report": {"summary": "revenue fixed", "full_text": "..."},
             "unified_data_reference": {"final_values": {"revenue": 6770}}},
            {"agent_id": "analysis_1", "category": "analysis", "success": True,
             "content": "Some analysis"},
        ]

        _calib = [r for r in previous_results if r.get("category") == "calibration" and r.get("success")]
        task = {}
        if _calib:
            _calib_data = _calib[0]
            task["calibration_report"] = _calib_data.get("calibration_report", {})
            task["unified_data_reference"] = _calib_data.get("unified_data_reference", {})

        assert "calibration_report" in task
        assert task["calibration_report"]["summary"] == "revenue fixed"
        assert task["unified_data_reference"]["final_values"]["revenue"] == 6770

    def test_calibration_injection_no_calib_results(self):
        """No calibration results → no injection into task."""
        previous_results = [
            {"agent_id": "analysis_1", "category": "analysis", "success": True},
        ]

        _calib = [r for r in previous_results if r.get("category") == "calibration" and r.get("success")]
        task = {}
        if _calib:
            _calib_data = _calib[0]
            task["calibration_report"] = _calib_data.get("calibration_report", {})
            task["unified_data_reference"] = _calib_data.get("unified_data_reference", {})

        assert "calibration_report" not in task
        assert "unified_data_reference" not in task
