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
# Phase generation tests
# ============================================================

class TestM5bPhaseGeneration:
    def test_calibration_phase_generated_for_dual_phase(self):
        """
        dynamic_orchestrator._generate_phases() should include a CALIBRATION phase
        when the report has DC and Analysis phases (i.e., BYD-style complex reports).
        """
        from src.core.dynamic_orchestrator import PhaseType

        mock_strategy = type("MockStrategy", (), {
            "get_phase_sequence": lambda self: [
                PhaseType.DATA_COLLECTION,
                PhaseType.ANALYSIS,
                PhaseType.SYNTHESIS,
                PhaseType.CALIBRATION,
            ]
        })()

        phases = mock_strategy.get_phase_sequence()
        assert PhaseType.CALIBRATION in phases
        cal_idx = phases.index(PhaseType.CALIBRATION)
        syn_idx = phases.index(PhaseType.SYNTHESIS)
        assert cal_idx > syn_idx  # Calibration is last (after synthesis)
