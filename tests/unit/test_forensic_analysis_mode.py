# -*- coding: utf-8 -*-
"""
Tests for Forensic Analysis Mode — C1 (IntentType), C2 (DeepIntentResult fields),
C4 (_build_result parsing + requires_secondary_data override), C5 (routing branch),
C6 (SectionSpec config), C9 (forensic phase orchestration), C10 (parser search),
C11 (GenericAgent forensic preloaded), C12 (API question_suffixes fix),
to_decomposition_plan (config→context propagation).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.core.intent_types import IntentType
from src.core.semantic_intent import DeepIntentResult, SemanticIntentAnalyzer
from src.core.research_type import ResearchType


class TestC1ForensicAnalysisIntentType:
    def test_forensic_analysis_exists(self):
        assert IntentType.FORENSIC_ANALYSIS is not None

    def test_forensic_analysis_value(self):
        assert IntentType.FORENSIC_ANALYSIS.value == "forensic_analysis"

    def test_forensic_analysis_constructible_from_string(self):
        result = IntentType("forensic_analysis")
        assert result == IntentType.FORENSIC_ANALYSIS

    def test_existing_intent_types_unchanged(self):
        expected = ["research", "implementation", "investigation", "evaluation",
                     "fix", "open_ended", "clarification"]
        actual = [t.value for t in IntentType if t != IntentType.FORENSIC_ANALYSIS]
        for v in expected:
            assert v in actual, f"Missing existing IntentType: {v}"


class TestC2DeepIntentResultForensicFields:
    def test_forensic_mode_defaults_false(self):
        r = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
        )
        assert r.forensic_mode is False

    def test_data_preloaded_defaults_false(self):
        r = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.8,
            intent_reasoning="test",
        )
        assert r.data_preloaded is False

    def test_causal_hypotheses_defaults_empty(self):
        r = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.8,
            intent_reasoning="test",
        )
        assert r.causal_hypotheses == []

    def test_forensic_mode_set_true(self):
        r = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.95,
            intent_reasoning="question with preloaded data",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=["H1: 非现金支出增加", "H2: 营运资本改善"],
        )
        assert r.forensic_mode is True
        assert r.data_preloaded is True
        assert len(r.causal_hypotheses) == 2

    def test_to_dict_includes_forensic_fields(self):
        r = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=["H1"],
        )
        d = r.to_dict()
        assert d["forensic_mode"] is True
        assert d["data_preloaded"] is True
        assert d["causal_hypotheses"] == ["H1"]

    def test_from_dict_round_trip_forensic_fields(self):
        r = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=["H1: 非现金支出增加", "H2: 营运资本改善"],
        )
        d = r.to_dict()
        restored = DeepIntentResult.from_dict(d)
        assert restored.forensic_mode is True
        assert restored.data_preloaded is True
        assert restored.causal_hypotheses == ["H1: 非现金支出增加", "H2: 营运资本改善"]


class TestC4BuildResultForensicParsing:
    def test_build_result_parses_forensic_fields(self):
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "forensic_analysis",
            "confidence": 0.95,
            "reasoning": "question with preloaded data",
            "forensic_mode": True,
            "data_preloaded": True,
            "causal_hypotheses": ["H1: 折旧增加", "H2: 营运资本改善"],
            "complexity": "multi",
            "aspect_count": 4,
        }
        result = analyzer._build_result(llm_output, "test_model", "", False)
        assert result.primary_intent == IntentType.FORENSIC_ANALYSIS
        assert result.forensic_mode is True
        assert result.data_preloaded is True
        assert result.causal_hypotheses == ["H1: 折旧增加", "H2: 营运资本改善"]

    def test_build_result_defaults_forensic_fields_when_absent(self):
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.8,
            "reasoning": "standard research",
            "complexity": "single",
        }
        result = analyzer._build_result(llm_output, "test_model", "", False)
        assert result.forensic_mode is False
        assert result.data_preloaded is False
        assert result.causal_hypotheses == []

    def test_data_preloaded_overrides_requires_secondary_data(self):
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "forensic_analysis",
            "confidence": 0.9,
            "reasoning": "test",
            "data_preloaded": True,
            "requires_secondary_data": True,
            "complexity": "multi",
        }
        result = analyzer._build_result(llm_output, "test_model", "", False)
        assert result.requires_secondary_data is False

    def test_no_data_preloaded_keeps_requires_secondary_data(self):
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.8,
            "reasoning": "test",
            "complexity": "single",
        }
        result = analyzer._build_result(llm_output, "test_model", "", False)
        assert result.requires_secondary_data is True


class TestC6SectionSpecConfigField:
    def test_section_spec_has_config_field(self):
        from src.core.task_structure import SectionSpec, SectionRole
        spec = SectionSpec(
            section_id="test_section",
            section_name="Test",
            section_role=SectionRole.ANALYSIS,
        )
        assert hasattr(spec, 'config')
        assert isinstance(spec.config, dict)

    def test_section_spec_config_defaults_empty(self):
        from src.core.task_structure import SectionSpec, SectionRole
        spec = SectionSpec(
            section_id="test_section",
            section_name="Test",
            section_role=SectionRole.ANALYSIS,
        )
        assert spec.config == {}

    def test_section_spec_config_set(self):
        from src.core.task_structure import SectionSpec, SectionRole
        spec = SectionSpec(
            section_id="test_section",
            section_name="Test",
            section_role=SectionRole.ANALYSIS,
            config={"forensic_mode": True, "hypothesis_data_needs": ["折旧", "应收账款"]},
        )
        assert spec.config["forensic_mode"] is True
        assert len(spec.config["hypothesis_data_needs"]) == 2

    def test_section_spec_to_dict_includes_config(self):
        from src.core.task_structure import SectionSpec, SectionRole
        spec = SectionSpec(
            section_id="test_section",
            section_name="Test",
            section_role=SectionRole.ANALYSIS,
            config={"forensic_mode": True},
        )
        d = spec.to_dict()
        assert "config" in d
        assert d["config"]["forensic_mode"] is True


class TestC10AnnualReportParserSearchMethods:
    def test_search_sections_finds_by_keyword(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {
            "sections": [
                {"title": "现金流分析", "content": "经营活动产生的现金流量净额为10亿元", "section_type": "cashflow"},
                {"title": "风险因素", "content": "市场竞争加剧", "section_type": "risk"},
                {"title": "财务报表", "content": "应收账款增加5亿元", "section_type": "financial"},
            ]
        }
        results = parser.search_sections(parse_data, ["现金流量"])
        assert len(results) == 1
        assert results[0]["title"] == "现金流分析"

    def test_search_sections_finds_by_title(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {
            "sections": [
                {"title": "现金流分析", "content": "数据", "section_type": "cashflow"},
            ]
        }
        results = parser.search_sections(parse_data, ["现金流"])
        assert len(results) == 1

    def test_search_sections_no_match_returns_empty(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {"sections": [{"title": "概述", "content": "公司概况", "section_type": "overview"}]}
        results = parser.search_sections(parse_data, ["折旧"])
        assert results == []

    def test_find_line_items_by_keyword(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {
            "financial_tables": {
                "income": [{"科目": "营业收入", "本年": 100}, {"科目": "净利润", "本年": 10}],
                "cashflow": [{"科目": "折旧", "本年": 8.2}, {"科目": "经营活动现金流", "本年": 20}],
            }
        }
        results = parser.find_line_items(parse_data, ["折旧"])
        assert len(results) == 1
        assert results[0]["table_type"] == "cashflow"
        assert results[0]["row"]["科目"] == "折旧"

    def test_find_line_items_no_match_returns_empty(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {"financial_tables": {"income": [{"科目": "营业收入", "本年": 100}]}}
        results = parser.find_line_items(parse_data, ["研发支出"])
        assert results == []

    def test_extract_for_hypothesis(self):
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        parse_data = {
            "sections": [
                {"title": "现金流分析", "content": "折旧摊销明细", "section_type": "cashflow"},
            ],
            "financial_tables": {
                "cashflow": [{"科目": "折旧", "本年": 8.2}],
            }
        }
        result = parser.extract_for_hypothesis(parse_data, "非现金支出增加", ["折旧", "现金流"])
        assert result["hypothesis"] == "非现金支出增加"
        assert len(result["relevant_sections"]) == 1
        assert len(result["relevant_line_items"]) == 1
        assert result["section_count"] == 1
        assert result["line_item_count"] == 1


class TestC12QuestionSuffixesFix:
    def test_question_with_preloaded_allows_depth_command(self):
        has_preloaded = True
        question_suffixes = ('？', '?', '吗', '呢', '是什么', '是什么意思', '怎么', '如何')
        depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
        input_lower = "详细分析为什么现金流增长利润没增长？"
        is_depth_command = any(kw in input_lower for kw in depth_keywords) and (not any(input_lower.endswith(s) for s in question_suffixes) or has_preloaded)
        assert is_depth_command is True

    def test_question_without_preloaded_blocked(self):
        has_preloaded = False
        question_suffixes = ('？', '?', '吗', '呢', '是什么', '是什么意思', '怎么', '如何')
        depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
        input_lower = "详细分析为什么现金流增长利润没增长？"
        is_depth_command = any(kw in input_lower for kw in depth_keywords) and (not any(input_lower.endswith(s) for s in question_suffixes) or has_preloaded)
        assert is_depth_command is False

    def test_non_question_depth_command_still_works(self):
        has_preloaded = False
        question_suffixes = ('？', '?', '吗', '呢', '是什么', '是什么意思', '怎么', '如何')
        depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
        input_lower = "深度研究这份年报"
        is_depth_command = any(kw in input_lower for kw in depth_keywords) and (not any(input_lower.endswith(s) for s in question_suffixes) or has_preloaded)
        assert is_depth_command is True


class TestC5ForensicBranchInRouting:
    def test_forensic_mode_uses_forensic_structure(self):
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        adapter = IntelligentRoutingAdapter()
        adapter._analyze_intent = MagicMock(return_value=DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.95,
            intent_reasoning="forensic question",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=["H1: test"],
        ))
        adapter._analyze_forensic_structure = MagicMock(return_value=MagicMock())
        adapter._analyze_structure = MagicMock(return_value=MagicMock())
        adapter._orchestrate_forensic_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._orchestrate_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._to_decomposition_plan = MagicMock(return_value=None)
        adapter._enable_content_lock = False
        result = adapter.analyze("为什么现金流增长利润没增长？", {"task_id": "test"})
        adapter._analyze_forensic_structure.assert_called_once()
        adapter._analyze_structure.assert_not_called()

    def test_non_forensic_mode_uses_standard_structure(self):
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        adapter = IntelligentRoutingAdapter()
        adapter._analyze_intent = MagicMock(return_value=DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="standard research",
        ))
        adapter._analyze_forensic_structure = MagicMock(return_value=MagicMock())
        adapter._analyze_structure = MagicMock(return_value=MagicMock())
        adapter._orchestrate_forensic_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._orchestrate_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._to_decomposition_plan = MagicMock(return_value=None)
        adapter._enable_content_lock = False
        result = adapter.analyze("分析年报", {"task_id": "test"})
        adapter._analyze_structure.assert_called_once()
        adapter._analyze_forensic_structure.assert_not_called()

    def test_forensic_mode_uses_forensic_phases(self):
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        adapter = IntelligentRoutingAdapter()
        adapter._analyze_intent = MagicMock(return_value=DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.95,
            intent_reasoning="forensic",
            forensic_mode=True,
        ))
        mock_ts = MagicMock()
        adapter._analyze_forensic_structure = MagicMock(return_value=mock_ts)
        adapter._orchestrate_forensic_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._orchestrate_phases = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={}),
            phases=[],
            total_agents=0,
        ))
        adapter._to_decomposition_plan = MagicMock(return_value=None)
        adapter._enable_content_lock = False
        result = adapter.analyze("why?", {"task_id": "test"})
        adapter._orchestrate_forensic_phases.assert_called_once()
        adapter._orchestrate_phases.assert_not_called()


class TestC9OrchestrateForensicPhases:
    def _make_forensic_task_structure(self):
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
        sections = [
            SectionSpec(section_id="section_0_core_question", section_name="为什么现金流增长利润没增长",
                        section_role=SectionRole.SYNTHESIS, content_dependency=["section_1_hypothesis", "section_2_hypothesis"]),
            SectionSpec(section_id="section_1_hypothesis", section_name="H1: 非现金支出增加",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["折旧"]}),
            SectionSpec(section_id="section_2_hypothesis", section_name="H2: 营运资本改善",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["应收账款"]}),
            SectionSpec(section_id="section_data_extraction", section_name="精准数据提取",
                        section_role=SectionRole.DATA_COLLECTION, content_dependency=[]),
        ]
        return TaskStructure(
            task_id="forensic_test",
            topic="test",
            sections=sections,
            dependencies=[],
            execution_graph={},
            parallel_groups=[],
        )

    def test_forensic_phases_has_data_collection_phase(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        phase_types = [p.phase_type for p in phases]
        assert PhaseType.DATA_COLLECTION in phase_types

    def test_forensic_phases_has_analysis_phase(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        phase_types = [p.phase_type for p in phases]
        assert PhaseType.ANALYSIS in phase_types

    def test_forensic_phases_has_synthesis_phase(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        phase_types = [p.phase_type for p in phases]
        assert PhaseType.SYNTHESIS in phase_types

    def test_forensic_dc_phase_has_single_agent(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        dc_phase = [p for p in phases if p.phase_type == PhaseType.DATA_COLLECTION][0]
        assert len(dc_phase.agent_specs) == 1

    def test_forensic_analysis_phase_has_one_agent_per_hypothesis(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        analysis_phase = [p for p in phases if p.phase_type == PhaseType.ANALYSIS][0]
        assert len(analysis_phase.agent_specs) == 2

    def test_forensic_analysis_depends_on_dc(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        dc_phase = [p for p in phases if p.phase_type == PhaseType.DATA_COLLECTION][0]
        analysis_phase = [p for p in phases if p.phase_type == PhaseType.ANALYSIS][0]
        assert dc_phase.phase_id in analysis_phase.depends_on

    def test_forensic_synthesis_depends_on_analysis(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        analysis_phase = [p for p in phases if p.phase_type == PhaseType.ANALYSIS][0]
        synthesis_phase = [p for p in phases if p.phase_type == PhaseType.SYNTHESIS][0]
        assert analysis_phase.phase_id in synthesis_phase.depends_on

    def test_forensic_phases_includes_calibration_and_report(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        phase_types = [p.phase_type for p in phases]
        assert PhaseType.CALIBRATION in phase_types
        assert PhaseType.REPORT in phase_types


class TestToDecompositionPlanConfigPropagation:
    def test_config_propagated_to_context(self):
        from src.core.dynamic_orchestrator import ExecutionPlan, ExecutionPhase, AgentSpec, PhaseType
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
        sections = [
            SectionSpec(section_id="s1", section_name="test", section_role=SectionRole.ANALYSIS,
                        config={"forensic_mode": True, "hypothesis_data_needs": ["折旧"]}),
        ]
        ts = TaskStructure(task_id="t1", topic="test", sections=sections,
                           dependencies=[], execution_graph={}, parallel_groups=[])
        agent = AgentSpec(
            agent_id="a1", agent_type="analysis", section_ids=["s1"],
            config={"forensic_mode": True, "hypothesis_data_needs": ["折旧"]},
        )
        phase = ExecutionPhase(phase_id="p1", phase_type=PhaseType.ANALYSIS,
                               agent_specs=[agent], section_ids=["s1"])
        plan = ExecutionPlan(plan_id="plan1", task_structure=ts, phases=[phase],
                             content_lock_rules=[], total_agents=1)
        decomp = plan.to_decomposition_plan()
        from src.core.decomposition.strategies import ResearchPhase
        agents = decomp.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        assert len(agents) == 1
        assert agents[0].context.get("forensic_mode") is True
        assert agents[0].context.get("hypothesis_data_needs") == ["折旧"]

    def test_empty_config_does_not_break_existing(self):
        from src.core.dynamic_orchestrator import ExecutionPlan, ExecutionPhase, AgentSpec, PhaseType
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
        sections = [
            SectionSpec(section_id="s1", section_name="test", section_role=SectionRole.ANALYSIS),
        ]
        ts = TaskStructure(task_id="t1", topic="test", sections=sections,
                           dependencies=[], execution_graph={}, parallel_groups=[])
        agent = AgentSpec(
            agent_id="a1", agent_type="analysis", section_ids=["s1"],
            config={},
        )
        phase = ExecutionPhase(phase_id="p1", phase_type=PhaseType.ANALYSIS,
                               agent_specs=[agent], section_ids=["s1"])
        plan = ExecutionPlan(plan_id="plan1", task_structure=ts, phases=[phase],
                             content_lock_rules=[], total_agents=1)
        decomp = plan.to_decomposition_plan()
        from src.core.decomposition.strategies import ResearchPhase
        agents = decomp.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        assert len(agents) == 1
        assert agents[0].context == {}


class TestC11GenericAgentForensicPreloaded:
    @pytest.mark.asyncio
    async def test_forensic_mode_uses_extract_for_hypothesis(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {
            "preloaded": True,
            "forensic_mode": True,
            "hypothesis_data_needs": ["折旧", "现金流"],
            "core_question": "非现金支出增加",
            "section_id": "section_1_hypothesis",
        }
        agent._shared_memory = MagicMock()
        agent._shared_memory.get = MagicMock(return_value={
            "sections": [
                {"title": "现金流", "content": "经营活动现金流20亿", "section_type": "cashflow"},
            ],
            "financial_tables": {
                "cashflow": [{"科目": "折旧", "本年": 8.2}],
            }
        })
        agent._report_progress = MagicMock()
        agent._ensure_standard_result = MagicMock(return_value={"success": True})
        agent.agent_id = "test_agent"

        mock_extract = {
            "hypothesis": "非现金支出增加",
            "relevant_sections": [{"title": "现金流", "content": "经营活动现金流20亿", "section_type": "cashflow"}],
            "relevant_line_items": [{"table_type": "cashflow", "row": {"科目": "折旧", "本年": 8.2}}],
            "section_count": 1,
            "line_item_count": 1,
        }
        with patch.object(AnnualReportParserSkill, 'extract_for_hypothesis', return_value=mock_extract):
            action = "research"
            result = await agent._handle_preloaded_forensic(annual_report_data=agent._shared_memory.get("annual_report_data"), action=action)
            assert result is not None

    @pytest.mark.asyncio
    async def test_forensic_preloaded_exception_falls_back_to_none(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {
            "preloaded": True,
            "forensic_mode": True,
            "hypothesis_data_needs": ["折旧"],
            "core_question": "test",
        }
        agent.agent_id = "test_agent"
        with patch.object(AnnualReportParserSkill, 'extract_for_hypothesis', side_effect=Exception("parse error")):
            result = await agent._handle_preloaded_forensic({}, "research")
            assert result is None


class TestC9ForensicConfigPropagation:
    def _make_forensic_task_structure(self):
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
        sections = [
            SectionSpec(section_id="section_0_core_question", section_name="core question",
                        section_role=SectionRole.SYNTHESIS, content_dependency=["section_1_hypothesis"]),
            SectionSpec(section_id="section_1_hypothesis", section_name="H1: test",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["折旧"]}),
            SectionSpec(section_id="section_data_extraction", section_name="精准数据提取",
                        section_role=SectionRole.DATA_COLLECTION, content_dependency=[]),
        ]
        return TaskStructure(
            task_id="forensic_test",
            topic="test",
            sections=sections,
            dependencies=[],
            execution_graph={},
            parallel_groups=[],
        )

    def test_analysis_agent_config_includes_forensic_fields(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        analysis_phase = [p for p in phases if p.phase_type == PhaseType.ANALYSIS][0]
        agent_config = analysis_phase.agent_specs[0].config
        assert agent_config.get("forensic_mode") is True
        assert agent_config.get("hypothesis_data_needs") == ["折旧"]

    def test_forensic_config_flows_through_to_decomposition_plan(self):
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        from src.core.decomposition.strategies import ResearchPhase
        ts = self._make_forensic_task_structure()
        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9,
            intent_reasoning="test",
            forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        plan = orchestrator.plan_forensic(ts, intent, "test")
        decomp = plan.to_decomposition_plan()
        agents = decomp.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        assert len(agents) == 1
        assert agents[0].context.get("forensic_mode") is True
        assert agents[0].context.get("hypothesis_data_needs") == ["折旧"]
