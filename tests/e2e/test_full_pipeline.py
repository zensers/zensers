# -*- coding: utf-8 -*-
"""
Full pipeline end-to-end test: User Request → Report Generation

Validates the complete data flow through all system stages:
  1. User input → Dialogue → Topic identification
  2. Framework generation & confirmation
  3. Execution launch → Orchestrator dispatch
  4. Agent results → ResultAggregator → Section mapping
  5. Sections → ContentOrchestrator → HTML report
  6. HTML → QualityCheckAgent → Score & issues
  7. Full chain integration with cancel/pause

Mock strategy: patch at the skill/LLM boundary so orchestration logic runs real.
"""

import pytest
import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime


FIXTURE_TOPIC = "中国新能源汽车市场"
FIXTURE_SECTIONS = ["市场规模与增长", "竞争格局", "政策环境", "技术趋势"]
FIXTURE_FRAMEWORK_TREE = [
    {"name": "市场规模与增长", "sub_sections": [
        {"name": "整体市场规模", "points": ["营收规模", "增长率"]},
        {"name": "细分市场", "points": []},
    ]},
    {"name": "竞争格局", "sub_sections": [
        {"name": "主要厂商", "points": ["市场份额"]},
        {"name": "新进入者", "points": []},
    ]},
    {"name": "政策环境", "sub_sections": []},
    {"name": "技术趋势", "sub_sections": []},
]


def _make_llm_response(action="continue_chat", message="", topic=None,
                       directions=None, framework_sections=None,
                       framework_tree=None, suggestions=None, tool_call=None):
    return json.dumps({
        "message": message or "好的，我来帮您研究。",
        "action": action,
        "topic": topic,
        "directions": directions or [],
        "framework_sections": framework_sections,
        "framework_tree": framework_tree,
        "clarification_questions": [],
        "identified_aspects": framework_sections or [],
        "is_composite": False,
        "suggestions": suggestions or [],
        "inject_ops": [],
        "complexity": "single",
        "research_types": [],
        "hidden_requirements": [],
        "tool_call": tool_call,
    }, ensure_ascii=False)


def _make_session(session_id="test_ses_001", mode="chat", topic=None,
                  directions=None, framework=None, framework_tree=None,
                  language="zh"):
    from src.core.dialogue.state_machine import ConversationStateMachine
    sm = ConversationStateMachine(research_id=session_id)
    context = {
        "topic": topic,
        "directions": directions or [],
        "framework": framework,
        "details": {},
    }
    if framework_tree:
        context["_framework_tree"] = framework_tree
    return {
        "user_input": FIXTURE_TOPIC,
        "user_id": "test_user",
        "state_machine": sm,
        "created_at": datetime.now(),
        "current_step": 0,
        "mode": mode,
        "llm_config": {"model": "test-model", "max_tokens": 2048},
        "language": language,
        "_session_id": session_id,
        "conversation_history": [],
        "research_context": context,
    }


def _make_agent_results(sections):
    results = {}
    for i, section in enumerate(sections):
        agent_id = f"data_collection_{section}"
        results[agent_id] = {
            "success": True,
            "content": f"## {section}\n这是{section}的详细研究内容。包含市场数据、趋势分析和专家观点。数据来源可靠，分析深入全面。本文探讨了该领域的最新发展动态，并对未来趋势进行了预测。内容长度充足，覆盖了多个维度的信息。",
            "section_target": section,
            "agent_id": agent_id,
        }
    for i, section in enumerate(sections):
        agent_id = f"analysis_{section}"
        results[agent_id] = {
            "success": True,
            "content": f"## {section}深度分析\n基于数据收集结果，对{section}进行了深度分析。分析结论显示该领域具有显著增长潜力。关键发现包括：市场持续扩张、技术创新驱动、政策支持力度加大。综合评估认为前景乐观。",
            "section_target": section,
            "agent_id": agent_id,
        }
    return results


def _make_section_details(framework_tree):
    if not framework_tree:
        return []
    details = []
    for node in framework_tree:
        sub_sections = node.get("sub_sections", [])
        details.append({
            "id": node["name"].lower().replace(" ", "_"),
            "name": node["name"],
            "content": node["name"],
            "sub_sections": [{"name": s["name"], "points": s.get("points", [])} for s in sub_sections],
        })
    return details


def _make_research_result_dict(sections, content_prefix="研究内容"):
    return {
        "title": FIXTURE_TOPIC,
        "sections": [
            {
                "id": f"s{i+1}",
                "title": s,
                "content": f"## {s}\n{s}{content_prefix}。详细的分析和数据支撑，包含多个来源的交叉验证。市场数据显示持续增长趋势，行业专家观点一致看好。本节内容详实，数据丰富，分析深入。",
                "order": i,
                "type": "body",
                "subsections": [],
                "charts": [],
                "points": [],
            }
            for i, s in enumerate(sections)
        ],
        "key_findings": [f"{s}领域呈现显著增长" for s in sections],
        "data_points": [
            {"metric": f"{s}增长率", "value": "15.3%", "unit": "%"}
            for s in sections
        ],
    }


# ============================================================================
# Stage 1: User Input → Topic Identification → Framework Entry
# ============================================================================

class TestStage1UserInputToFramework:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._knowledge_manager = None
        api._preview_generator = MagicMock()
        api._tool_set = MagicMock()
        api._revision_locks = {}
        api._revision_task = None
        api._executor_tasks = {}
        api._session_locks = {}
        api._pending_clarifications = {}
        api._clarification_responses = {}
        api._loop_cancel_flags = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._dream_mode_running = False
        return api

    @pytest.mark.asyncio
    async def test_chat_mode_identifies_topic_and_enters_framework(self, api):
        llm_json = _make_llm_response(
            action="enter_framework",
            message="我来帮您研究新能源汽车市场。",
            topic=FIXTURE_TOPIC,
            directions=["市场规模", "竞争格局"],
            framework_sections=FIXTURE_SECTIONS,
            framework_tree=FIXTURE_FRAMEWORK_TREE,
        )
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json, "model": "test"}

        session = _make_session(topic=None, mode="chat")
        session_id = "test_ses_001"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.core.progress_streamer.ProgressStreamer"):
                    result = await api._handle_chat_mode(session_id, FIXTURE_TOPIC)

        assert result is not None
        assert "action" in result or "mode" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_llm_converse_parses_json_and_updates_context(self, api):
        llm_json = _make_llm_response(
            action="continue_chat",
            message="新能源汽车市场目前增长迅速。",
            topic=FIXTURE_TOPIC,
            directions=["市场规模", "技术趋势"],
        )
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json, "model": "test"}

        session = _make_session(topic=None, mode="chat")
        session_id = "test_ses_002"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.core.progress_streamer.ProgressStreamer"):
                    result = await api._llm_converse(session_id, "新能源汽车市场怎么样？")

        assert result["action"] == "continue_chat"
        assert result["topic"] == FIXTURE_TOPIC
        assert "市场规模" in result.get("directions", [])


# ============================================================================
# Stage 2: Framework Generation & Confirmation
# ============================================================================

class TestStage2FrameworkConfirmation:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._knowledge_manager = None
        api._preview_generator = MagicMock()
        api._tool_set = MagicMock()
        api._revision_locks = {}
        api._revision_task = None
        api._executor_tasks = {}
        api._session_locks = {}
        api._pending_clarifications = {}
        api._clarification_responses = {}
        api._loop_cancel_flags = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._dream_mode_running = False
        return api

    @pytest.mark.asyncio
    async def test_enter_framework_builds_framework_from_tree(self, api):
        session = _make_session(
            topic=FIXTURE_TOPIC,
            mode="chat",
            directions=["市场规模", "竞争格局"],
            framework_tree=FIXTURE_FRAMEWORK_TREE,
        )
        session_id = "test_ses_010"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                mock_cm.return_value.is_cancelled.return_value = False
                result = await api._enter_framework_mode(session_id, "深度研究")

        assert result["mode"] == "framework"
        framework = result.get("framework", {})
        assert framework is not None
        sections = framework.get("sections", [])
        assert len(sections) >= 4, f"Expected >=4 sections, got {sections}"
        assert framework.get("sections_tree") is not None

    @pytest.mark.asyncio
    async def test_enter_framework_idempotent(self, api):
        existing_fw = {
            "topic": FIXTURE_TOPIC,
            "sections": FIXTURE_SECTIONS,
            "output_type": "industry_report",
            "depth": "standard",
            "region": "China",
            "time_range": "Last 3 years",
        }
        session = _make_session(
            topic=FIXTURE_TOPIC,
            mode="framework",
            framework=existing_fw,
        )
        session_id = "test_ses_011"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                mock_cm.return_value.is_cancelled.return_value = False
                result = await api._enter_framework_mode(session_id, "confirm")

        assert result["mode"] == "framework"
        assert result["framework"]["sections"] == FIXTURE_SECTIONS


# ============================================================================
# Stage 3: Framework → Execution Launch
# ============================================================================

class TestStage3ExecutionLaunch:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._knowledge_manager = None
        api._preview_generator = MagicMock()
        api._tool_set = MagicMock()
        api._revision_locks = {}
        api._revision_task = None
        api._executor_tasks = {}
        api._session_locks = {}
        api._pending_clarifications = {}
        api._clarification_responses = {}
        api._loop_cancel_flags = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._dream_mode_running = False
        return api

    @pytest.mark.asyncio
    async def test_start_execution_builds_plan_and_launches_task(self, api):
        framework = {
            "topic": FIXTURE_TOPIC,
            "sections": FIXTURE_SECTIONS,
            "output_type": "industry_report",
            "depth": "standard",
            "region": "China",
            "time_range": "Last 3 years",
            "sections_tree": FIXTURE_FRAMEWORK_TREE,
        }
        session = _make_session(
            topic=FIXTURE_TOPIC,
            mode="framework",
            framework=framework,
        )
        session_id = "test_ses_020"

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={"status": "completed"})

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.api.research_executor.get_executor", return_value=mock_executor):
                with patch("src.core.progress_streamer.ProgressStreamer"):
                    with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                        mock_cm.return_value.is_paused.return_value = False
                        with patch("src.api.research_api.asyncio") as mock_aio:
                            mock_aio.create_task = MagicMock(return_value=MagicMock())
                            result = await api._start_execution(session_id)

        assert result["status"] == "running"
        assert result["mode"] == "research"
        plan = result.get("final_plan", {})
        assert plan.get("topic") == FIXTURE_TOPIC
        assert plan.get("aspects") == FIXTURE_SECTIONS
        assert plan.get("sections_tree") == FIXTURE_FRAMEWORK_TREE
        assert len(plan.get("section_details", [])) > 0

    @pytest.mark.asyncio
    async def test_start_execution_rejects_empty_topic(self, api):
        session = _make_session(topic=None, mode="framework", framework={"sections": FIXTURE_SECTIONS})
        session_id = "test_ses_021"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            result = await api._start_execution(session_id)

        assert "error" in result
        assert result.get("error_code") == "EMPTY_TOPIC"

    @pytest.mark.asyncio
    async def test_start_execution_rejects_empty_sections(self, api):
        session = _make_session(
            topic=FIXTURE_TOPIC,
            mode="framework",
            framework={"sections": []},
        )
        session_id = "test_ses_022"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            result = await api._start_execution(session_id)

        assert "error" in result
        assert result.get("error_code") == "EMPTY_SECTIONS"


# ============================================================================
# Stage 4: Agent Results → ResultAggregator → Section Mapping
# ============================================================================

class TestStage4Aggregation:
    def test_aggregate_maps_results_to_framework_sections(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        aggregator = ResultAggregator()
        agent_results = _make_agent_results(FIXTURE_SECTIONS)
        section_details = _make_section_details(FIXTURE_FRAMEWORK_TREE)

        result = aggregator.aggregate(
            results=agent_results,
            metadata={"topic": FIXTURE_TOPIC},
            section_details=section_details,
        )

        assert result is not None
        assert result.data is not None
        sections = result.to_dict() if hasattr(result, "to_dict") else result.data
        assert len(result.section_details) > 0

    def test_aggregate_with_empty_results(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        aggregator = ResultAggregator()
        section_details = _make_section_details(FIXTURE_FRAMEWORK_TREE)

        result = aggregator.aggregate(
            results={},
            metadata={"topic": FIXTURE_TOPIC},
            section_details=section_details,
        )

        assert result is not None
        assert result.stats is not None

    def test_aggregate_preserves_provenance(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        aggregator = ResultAggregator()
        agent_results = _make_agent_results(FIXTURE_SECTIONS[:2])
        section_details = _make_section_details(FIXTURE_FRAMEWORK_TREE[:2])

        result = aggregator.aggregate(
            results=agent_results,
            section_details=section_details,
        )

        assert len(result.content_provenance) > 0, "Provenance should be tracked"


# ============================================================================
# Stage 5: Sections → ContentOrchestrator → HTML Report
# ============================================================================

class TestStage5ReportGeneration:
    def test_content_orchestrator_generates_html(self):
        from src.content.content_orchestrator import ContentOrchestrator
        co = ContentOrchestrator()
        research_result = _make_research_result_dict(FIXTURE_SECTIONS)

        html = co.transform_to_html(research_result, output_format="docx")

        assert html is not None
        assert len(html) > 100
        for section in FIXTURE_SECTIONS:
            assert section in html, f"Section '{section}' should appear in HTML output"

    def test_content_orchestrator_html_contains_key_findings(self):
        from src.content.content_orchestrator import ContentOrchestrator
        co = ContentOrchestrator()
        research_result = _make_research_result_dict(FIXTURE_SECTIONS)

        html = co.transform_to_html(research_result, output_format="docx")

        assert "key_findings" in html.lower() or "关键发现" in html or "findings" in html.lower()

    def test_content_orchestrator_handles_empty_sections(self):
        from src.content.content_orchestrator import ContentOrchestrator
        co = ContentOrchestrator()
        research_result = {"title": "Empty Report", "sections": [], "key_findings": []}

        html = co.transform_to_html(research_result, output_format="docx")

        assert html is not None
        assert len(html) > 0


# ============================================================================
# Stage 6: Quality Check
# ============================================================================

class TestStage6QualityCheck:
    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        agent = QualityCheckAgent(agent_id="qc_test", name="Quality Check", config={})
        return agent

    @pytest.mark.asyncio
    async def test_quality_check_on_valid_report(self, agent):
        report = _make_research_result_dict(FIXTURE_SECTIONS)
        report["word_count"] = 2000

        task_input = {
            "report": report,
            "html_content": "<html><body>Test report</body></html>",
        }

        with patch.object(agent, "_check_completeness", return_value={"passed": True, "issues": [], "suggestions": [], "word_count": 2000, "section_count": 4}):
            with patch.object(agent, "_check_accuracy", return_value={"passed": True, "issues": [], "suggestions": []}):
                with patch.object(agent, "_check_consistency", return_value={"passed": True, "issues": [], "suggestions": []}):
                    with patch.object(agent, "_check_format", return_value={"passed": True, "issues": [], "suggestions": []}):
                        with patch.object(agent, "_calculate_score", return_value=85.0):
                            with patch.object(agent, "check_by_sections", new_callable=AsyncMock, return_value={"section_results": {}, "overall_issues": [], "overall_score": 0}):
                                result = await agent.execute(task_input)

        assert result["success"] is True
        assert result["quality_score"] == 85.0

    @pytest.mark.asyncio
    async def test_quality_check_detects_issues(self, agent):
        report = {"title": "Thin Report", "sections": [{"id": "s1", "title": "X", "content": "short"}], "word_count": 10}

        task_input = {"report": report, "html_content": "<html><body>short</body></html>"}

        with patch.object(agent, "_check_completeness", return_value={"passed": False, "issues": [{"type": "completeness", "severity": "high", "message": "Too short"}], "suggestions": ["Add more content"], "word_count": 10, "section_count": 1}):
            with patch.object(agent, "_check_accuracy", return_value={"passed": True, "issues": [], "suggestions": []}):
                with patch.object(agent, "_check_consistency", return_value={"passed": True, "issues": [], "suggestions": []}):
                    with patch.object(agent, "_check_format", return_value={"passed": True, "issues": [], "suggestions": []}):
                        with patch.object(agent, "_calculate_score", return_value=25.0):
                            with patch.object(agent, "check_by_sections", new_callable=AsyncMock, return_value={"section_results": {}, "overall_issues": [], "overall_score": 0}):
                                result = await agent.execute(task_input)

        assert result["quality_score"] == 25.0
        assert len(result["issues"]) > 0
        assert any(i["severity"] == "high" for i in result["issues"])


# ============================================================================
# Stage 7: Full Pipeline Integration (Aggregation → HTML → Quality)
# ============================================================================

class TestStage7FullPipelineIntegration:
    def test_aggregation_to_html_pipeline(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        from src.content.content_orchestrator import ContentOrchestrator

        aggregator = ResultAggregator()
        agent_results = _make_agent_results(FIXTURE_SECTIONS)
        section_details = _make_section_details(FIXTURE_FRAMEWORK_TREE)

        agg_result = aggregator.aggregate(
            results=agent_results,
            metadata={"topic": FIXTURE_TOPIC},
            section_details=section_details,
        )

        assert agg_result is not None

        sections_data = agg_result.to_dict() if hasattr(agg_result, "to_dict") else agg_result.data
        research_result = {
            "title": FIXTURE_TOPIC,
            "sections": sections_data if isinstance(sections_data, list) else _make_research_result_dict(FIXTURE_SECTIONS)["sections"],
            "key_findings": [f"{s}领域呈现显著增长" for s in FIXTURE_SECTIONS],
            "data_points": [{"metric": f"{s}增长率", "value": "15.3%", "unit": "%"} for s in FIXTURE_SECTIONS],
        }

        co = ContentOrchestrator()
        html = co.transform_to_html(research_result, output_format="docx")

        assert html is not None
        assert len(html) > 500
        for s in FIXTURE_SECTIONS:
            assert s in html, f"Section '{s}' missing from HTML"

    @pytest.mark.asyncio
    async def test_aggregation_to_quality_pipeline(self):
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        aggregator = ResultAggregator()
        agent_results = _make_agent_results(FIXTURE_SECTIONS)
        section_details = _make_section_details(FIXTURE_FRAMEWORK_TREE)

        agg_result = aggregator.aggregate(
            results=agent_results,
            metadata={"topic": FIXTURE_TOPIC},
            section_details=section_details,
        )

        report = _make_research_result_dict(FIXTURE_SECTIONS, content_prefix="研究内容")
        report["word_count"] = 3000

        agent = QualityCheckAgent(agent_id="qc_test", name="Quality Check", config={})

        with patch.object(agent, "_check_completeness", return_value={"passed": True, "issues": [], "suggestions": [], "word_count": 3000, "section_count": 4}):
            with patch.object(agent, "_check_accuracy", return_value={"passed": True, "issues": [], "suggestions": []}):
                with patch.object(agent, "_check_consistency", return_value={"passed": True, "issues": [], "suggestions": []}):
                    with patch.object(agent, "_check_format", return_value={"passed": True, "issues": [], "suggestions": []}):
                        with patch.object(agent, "_calculate_score", return_value=82.0):
                            with patch.object(agent, "check_by_sections", new_callable=AsyncMock, return_value={"section_results": {}, "overall_issues": [], "overall_score": 0}):
                                qc_result = await agent.execute({"report": report, "html_content": "<html>test</html>"})

        assert qc_result["success"] is True
        assert qc_result["quality_score"] > 0


# ============================================================================
# State Machine Validation
# ============================================================================

class TestStateMachineFlow:
    def test_understanding_to_framework_transition(self):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        assert sm.current_state == ConversationState.UNDERSTANDING
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    def test_framework_to_executing_transition(self):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_executing_to_completed_transition(self):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.COMPLETED)
        assert sm.current_state == ConversationState.COMPLETED

    def test_executing_to_paused_to_resumed(self):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        assert sm.current_state == ConversationState.PAUSED
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_invalid_transition_raises(self):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        with pytest.raises(Exception):
            sm.transition(ConversationState.COMPLETED)


# ============================================================================
# Cross-Stage Data Integrity
# ============================================================================

class TestDataIntegrityAcrossStages:
    def test_section_details_match_framework_tree(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        details = api._build_section_details_from_tree(FIXTURE_FRAMEWORK_TREE)

        assert len(details) == len(FIXTURE_FRAMEWORK_TREE)
        for i, detail in enumerate(details):
            assert detail["name"] == FIXTURE_FRAMEWORK_TREE[i]["name"]
            expected_subs = FIXTURE_FRAMEWORK_TREE[i].get("sub_sections", [])
            assert len(detail["sub_sections"]) == len(expected_subs)

    def test_final_plan_section_details_consistency(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        details = api._build_section_details_from_tree(FIXTURE_FRAMEWORK_TREE)

        section_names_in_details = [d["name"] for d in details]
        section_names_in_tree = [n["name"] for n in FIXTURE_FRAMEWORK_TREE]

        assert section_names_in_details == section_names_in_tree

    def test_build_response_preserves_all_fields(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        parsed = {
            "message": "test",
            "action": "continue_chat",
            "topic": "topic",
            "directions": ["d1"],
            "framework_sections": ["s1"],
            "framework_tree": [{"name": "s1", "sub_sections": []}],
            "clarification_questions": ["q1"],
            "identified_aspects": ["a1"],
            "is_composite": True,
            "suggestions": ["sug1"],
            "inject_ops": [{"op": "add_section"}],
            "complexity": "composite",
            "research_types": ["industry"],
            "hidden_requirements": ["r1"],
        }
        result = api._build_response(parsed, None, "note_text")

        assert result["action"] == "continue_chat"
        assert result["topic"] == "topic"
        assert result["framework_tree"] == [{"name": "s1", "sub_sections": []}]
        assert result["_note"] == "note_text"
        assert result["is_composite"] is True


# ============================================================================
# Prompt Construction: Every f-string must render without ValueError
# ============================================================================

class TestAllPromptsRender:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._knowledge_manager = None
        api._preview_generator = MagicMock()
        api._tool_set = MagicMock()
        api._tool_set.TOOL_DEFINITIONS = []
        api._revision_locks = {}
        api._revision_task = None
        api._executor_tasks = {}
        api._session_locks = {}
        api._pending_clarifications = {}
        api._clarification_responses = {}
        api._loop_cancel_flags = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._dream_mode_running = False
        return api

    @pytest.mark.asyncio
    async def test_llm_framework_modify_prompt_renders(self, api):
        session = _make_session(
            topic="比亚迪财务分析",
            mode="framework",
            framework={"sections": ["营收", "利润"], "sections_tree": [
                {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度数据"]}]},
            ]},
        )
        session_id = "test_prompt_001"
        llm_json = json.dumps({"action": "confirm", "message": "OK", "new_sections": None})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._llm_framework_modify(session_id, "确认开始")

        assert result is not None
        assert result["action"] == "confirm"

    @pytest.mark.asyncio
    async def test_llm_framework_modify_with_modify_action(self, api):
        session = _make_session(
            topic="新能源汽车",
            mode="framework",
            framework={"sections": ["市场"], "sections_tree": [
                {"name": "市场", "sub_sections": [{"name": "规模", "points": ["销量"]}]},
            ]},
        )
        session_id = "test_prompt_002"
        llm_json = json.dumps({"action": "modify", "message": "已修改", "new_sections": ["市场", "技术"]})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._llm_framework_modify(session_id, "加一个技术章节")

        assert result["action"] == "modify"
        assert len(result["new_sections"]) == 2

    @pytest.mark.asyncio
    async def test_llm_framework_modify_no_tree(self, api):
        session = _make_session(
            topic="测试主题",
            mode="framework",
            framework={"sections": ["A", "B"]},
        )
        session_id = "test_prompt_003"
        llm_json = json.dumps({"action": "confirm", "message": "OK", "new_sections": None})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._llm_framework_modify(session_id, "确认")

        assert result["action"] == "confirm"

    @pytest.mark.asyncio
    async def test_handle_framework_mode_confirm(self, api):
        session = _make_session(
            topic="比亚迪",
            mode="framework",
            framework={"sections": ["营收", "利润"], "output_type": "industry_report", "depth": "standard"},
        )
        session_id = "test_prompt_010"
        llm_json = json.dumps({"action": "confirm", "message": "OK", "new_sections": None})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={"status": "completed"})

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    with patch("src.api.research_executor.get_executor", return_value=mock_executor):
                        with patch("src.core.progress_streamer.ProgressStreamer"):
                            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                                mock_cm.return_value.is_paused.return_value = False
                                with patch("src.api.research_api.asyncio") as mock_aio:
                                    mock_aio.create_task = MagicMock(return_value=MagicMock())
                                    result = await api._handle_framework_mode(session_id, "确认开始")

        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_framework_mode_cancel(self, api):
        session = _make_session(
            topic="测试",
            mode="framework",
            framework={"sections": ["A"]},
        )
        session_id = "test_prompt_011"
        llm_json = json.dumps({"action": "cancel", "message": "已取消", "new_sections": None})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._handle_framework_mode(session_id, "取消")

        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_framework_mode_modify(self, api):
        session = _make_session(
            topic="测试",
            mode="framework",
            framework={"sections": ["A"], "output_type": "industry_report", "depth": "standard"},
        )
        session_id = "test_prompt_012"
        llm_json = json.dumps({"action": "modify", "message": "已修改", "new_sections": ["A", "B"], "new_framework_tree": None})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._handle_framework_mode(session_id, "加一个B章节")

        assert result is not None
        fw = session.get("research_context", {}).get("framework", {})
        assert "B" in fw.get("sections", [])

    @pytest.mark.asyncio
    async def test_infer_framework_sections_prompt_renders(self, api):
        session = _make_session(topic="AI market", mode="framework")
        session["conversation_history"] = [{"role": "user", "content": "Tell me about AI"}]
        session_id = "test_prompt_020"

        llm_json = '["Market Size", "Competition"]'
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._infer_framework_sections_from_conversation(session_id)

        assert result is not None

    def test_build_initial_prompt_renders(self, api):
        prompt = api._build_initial_prompt(
            current_date="2026-06-19",
            current_time="20:00:00",
            current_year=2026,
            history_text="User: hello",
            context_summary="Topic: test",
            dialogue_context="",
            paused_context="",
            sections_context="",
            post_research_hint="",
            tools_section="",
            domain_guard="",
            user_input="test input",
            research_running_ctx="",
        )
        assert "2026-06-19" in prompt
        assert "test input" in prompt

    def test_build_followup_prompt_renders(self, api):
        prompt = api._build_followup_prompt(
            accumulated_context="tool result data",
            tool_history=[{"iteration": 1, "name": "web_search"}],
            original_input="test query",
            history_text="User: hello",
            dialogue_context="",
        )
        assert "web_search" in prompt

    @pytest.mark.asyncio
    async def test_retry_json_only_prompt_renders(self, api):
        llm_json = json.dumps({"action": "continue_chat", "message": "OK"})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.config.settings.settings") as mock_settings:
            mock_settings.llm.model = "test"
            mock_settings.llm.max_tokens = 1024
            result = await api._retry_json_only(
                mock_llm, "system prompt", {"model": "test"}, "test_prompt_030"
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_llm_converse_full_prompt_renders(self, api):
        llm_json = json.dumps({"action": "continue_chat", "message": "OK", "topic": None, "directions": []})
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        session = _make_session(topic=None, mode="chat")
        session_id = "test_prompt_040"

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                    mock_cm.return_value.is_paused.return_value = False
                    with patch("src.core.session_streamer.SessionStreamer"):
                        result = await api._llm_converse(session_id, "你好")

        assert result["action"] == "continue_chat"


# ============================================================================
# Bug Fix: _build_initial_prompt context_summary was literal text, not variable
# ============================================================================

class TestBuildInitialPromptBugFix:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_context_summary_is_interpolated_not_literal(self, api):
        prompt = api._build_initial_prompt(
            current_date="2026-06-19", current_time="20:00:00", current_year=2026,
            history_text="", context_summary="Confirmed research topic: BYD",
            dialogue_context="", paused_context="", sections_context="",
            post_research_hint="", tools_section="", domain_guard="",
            user_input="test", research_running_ctx="",
        )
        assert "Confirmed research topic: BYD" in prompt
        assert "context_summary(" not in prompt, "literal 'context_summary(' must not appear"

    def test_context_summary_fallback_when_empty(self, api):
        prompt = api._build_initial_prompt(
            current_date="2026-06-19", current_time="20:00:00", current_year=2026,
            history_text="", context_summary="",
            dialogue_context="", paused_context="", sections_context="",
            post_research_hint="", tools_section="", domain_guard="",
            user_input="test", research_running_ctx="",
        )
        assert "Research topic not yet confirmed" in prompt


# ============================================================================
# Bug Fix: handle_quality_action must return dict, never None
# ============================================================================

class TestHandleQualityActionReturnsDict:
    def test_returns_error_dict_when_no_quality_state(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._session_locks = {}
        mock_request = MagicMock()
        mock_request.session_id = "test_qa_001"
        mock_request.action = "accept"
        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = _make_session(mode="research")
            with patch.object(api, "_get_quality_lock", return_value=MagicMock()):
                result = asyncio.get_event_loop().run_until_complete(api.handle_quality_action(mock_request))
        assert isinstance(result, dict), "Must always return dict, never None"
        assert "error" in result

    def test_returns_error_dict_when_no_sections(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._session_locks = {}
        mock_request = MagicMock()
        mock_request.session_id = "test_qa_002"
        mock_request.action = "accept"
        session = _make_session(mode="research")
        session["quality_state"] = {"phase": "reviewing"}
        session["research_result"] = {"status": "completed", "report": {"sections": []}}
        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            lock = MagicMock()
            lock.__aenter__ = AsyncMock(return_value=None)
            lock.__aexit__ = AsyncMock(return_value=None)
            with patch.object(api, "_get_quality_lock", return_value=lock):
                result = asyncio.get_event_loop().run_until_complete(api.handle_quality_action(mock_request))
        assert isinstance(result, dict)


# ============================================================================
# Bug Fix: _on_sse_disconnect stores task reference
# ============================================================================

class TestSSEDisconnectTaskStorage:
    def test_disconnect_stores_task_reference(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._background_tasks = {}

        session = _make_session(mode="research")
        session["research_result"] = {"status": "running"}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.api.research_api.asyncio") as mock_aio:
                mock_task = MagicMock()
                mock_aio.create_task.return_value = mock_task
                api._on_sse_disconnect("test_sse_001")

        assert mock_aio.create_task.called
        assert len(api._background_tasks) > 0, "Task reference must be stored"


# ============================================================================
# Coverage: _extract_json_from_llm_content (all branches)
# ============================================================================

class TestExtractJsonFromLlmContent:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_json_in_code_fence(self, api):
        result = api._extract_json_from_llm_content('```json\n{"action": "ok"}\n```')
        assert result == '{"action": "ok"}'

    def test_raw_json_object(self, api):
        result = api._extract_json_from_llm_content('{"action": "ok", "message": "hi"}')
        assert result is not None
        assert '"action"' in result

    def test_json_with_think_tags(self, api):
        result = api._extract_json_from_llm_content('<think>reasoning</think>\n{"action": "ok"}')
        assert result is not None

    def test_json_embedded_in_text(self, api):
        result = api._extract_json_from_llm_content('Here is the result:\n{"action": "ok"}\nEnd.')
        assert result is not None

    def test_no_json_returns_none(self, api):
        result = api._extract_json_from_llm_content("Just plain text with no JSON.")
        assert result is None

    def test_nested_braces(self, api):
        result = api._extract_json_from_llm_content('{"outer": {"inner": "value"}}')
        assert result is not None


# ============================================================================
# Coverage: _validate_action_for_state
# ============================================================================

class TestValidateActionForState:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_continue_chat_in_understanding(self, api):
        from src.core.dialogue.state_machine import ConversationStateMachine
        sm = ConversationStateMachine(research_id="test")
        result = api._validate_action_for_state("continue_chat", sm, "hello")
        assert result == "continue_chat"

    def test_enter_framework_allowed_in_understanding(self, api):
        from src.core.dialogue.state_machine import ConversationStateMachine
        sm = ConversationStateMachine(research_id="test")
        result = api._validate_action_for_state("enter_framework", sm, "deep research")
        assert result == "enter_framework"

    def test_heavy_action_downgraded_in_executing(self, api):
        from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        result = api._validate_action_for_state("modify_research", sm, "casual chat")
        assert result != "modify_research", "Heavy action should be downgraded in EXECUTING"


# ============================================================================
# Coverage: _should_start_execution
# ============================================================================

class TestShouldStartExecution:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_true_when_framework_and_confirm(self, api):
        result = api._should_start_execution("confirm start", "framework", {"framework": {"sections": ["A"]}}, "test")
        assert result is True

    def test_false_when_no_framework(self, api):
        result = api._should_start_execution("confirm start", "framework", {"framework": None}, "test")
        assert result is False

    def test_false_when_not_framework_mode(self, api):
        result = api._should_start_execution("confirm start", "chat", {"framework": {"sections": ["A"]}}, "test")
        assert result is False


# ============================================================================
# sections_tree integrity: must never be silently lost
# ============================================================================

class TestSectionsTreePreservation:
    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._knowledge_manager = None
        api._preview_generator = MagicMock()
        api._tool_set = MagicMock()
        api._tool_set.TOOL_DEFINITIONS = []
        api._revision_locks = {}
        api._revision_task = None
        api._executor_tasks = {}
        api._session_locks = {}
        api._pending_clarifications = {}
        api._clarification_responses = {}
        api._loop_cancel_flags = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._dream_mode_running = False
        return api

    @pytest.mark.asyncio
    async def test_llm_framework_modify_returns_new_framework_tree(self, api):
        session = _make_session(
            topic="比亚迪财务分析",
            mode="framework",
            framework={"sections": ["营收", "利润"], "sections_tree": [
                {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度数据"]}]},
                {"name": "利润", "sub_sections": [{"name": "毛利", "points": []}]},
            ]},
        )
        session_id = "test_tree_001"

        new_tree = [
            {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度数据"]}, {"name": "海外营收", "points": []}]},
            {"name": "利润", "sub_sections": [{"name": "毛利", "points": []}]},
        ]
        llm_json = json.dumps({
            "action": "modify",
            "message": "已添加海外营收",
            "new_sections": ["营收", "利润"],
            "new_framework_tree": new_tree,
        })
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._llm_framework_modify(session_id, "加一个海外营收")

        assert result["new_framework_tree"] is not None, "new_framework_tree must be returned from _llm_framework_modify"
        assert len(result["new_framework_tree"]) == 2
        assert len(result["new_framework_tree"][0]["sub_sections"]) == 2

    @pytest.mark.asyncio
    async def test_modify_preserves_tree_when_sections_match(self, api):
        session = _make_session(
            topic="比亚迪",
            mode="framework",
            framework={
                "sections": ["营收", "利润"],
                "sections_tree": [
                    {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度"]}]},
                    {"name": "利润", "sub_sections": [{"name": "毛利", "points": []}]},
                ],
            },
        )
        session_id = "test_tree_002"

        llm_json = json.dumps({
            "action": "modify",
            "message": "OK",
            "new_sections": ["营收", "利润"],
            "new_framework_tree": None,
        })
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._handle_framework_mode(session_id, "确认")

        fw = session["research_context"].get("framework", {})
        assert fw.get("sections_tree") is not None, "sections_tree must be preserved when sections match"
        assert len(fw["sections_tree"]) == 2
        assert fw["sections_tree"][0]["sub_sections"][0]["name"] == "国内营收"

    @pytest.mark.asyncio
    async def test_modify_preserves_subtree_for_matching_sections(self, api):
        session = _make_session(
            topic="比亚迪",
            mode="framework",
            framework={
                "sections": ["营收", "利润"],
                "sections_tree": [
                    {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度"]}]},
                    {"name": "利润", "sub_sections": [{"name": "毛利", "points": []}]},
                ],
            },
        )
        session_id = "test_tree_003"

        llm_json = json.dumps({
            "action": "modify",
            "message": "OK",
            "new_sections": ["营收", "利润", "现金流"],
            "new_framework_tree": None,
        })
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    result = await api._handle_framework_mode(session_id, "加一个现金流")

        fw = session["research_context"].get("framework", {})
        tree = fw.get("sections_tree")
        assert tree is not None, "sections_tree must be preserved even when new sections added"
        assert len(tree) == 3
        matched = [s for s in tree if s.get("name") == "营收"]
        assert len(matched) == 1 and len(matched[0]["sub_sections"]) == 1, "Existing sub-tree must be preserved for matching sections"
        new_sec = [s for s in tree if s.get("name") == "现金流"]
        assert len(new_sec) == 1, "New section must be added to tree"

    @pytest.mark.asyncio
    async def test_confirm_preserves_tree(self, api):
        session = _make_session(
            topic="比亚迪",
            mode="framework",
            framework={
                "sections": ["营收", "利润"],
                "sections_tree": [
                    {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度"]}]},
                ],
                "output_type": "industry_report",
                "depth": "standard",
            },
        )
        session_id = "test_tree_004"

        llm_json = json.dumps({
            "action": "confirm",
            "message": "确认",
            "new_sections": None,
            "new_framework_tree": None,
        })
        mock_llm = AsyncMock()
        mock_llm.execute.return_value = {"success": True, "content": llm_json}

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={"status": "completed"})

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.skills.llm_skill.LLMSkill", return_value=mock_llm):
                with patch("src.config.settings.settings") as mock_settings:
                    mock_settings.llm.model = "test"
                    mock_settings.llm.max_tokens = 1024
                    with patch("src.api.research_executor.get_executor", return_value=mock_executor):
                        with patch("src.core.progress_streamer.ProgressStreamer"):
                            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                                mock_cm.return_value.is_paused.return_value = False
                                result = await api._handle_framework_mode(session_id, "确认开始研究")

        fw = session["research_context"].get("framework", {})
        assert fw.get("sections_tree") is not None, "sections_tree must survive confirm path"

    @pytest.mark.asyncio
    async def test_start_execution_includes_tree_in_plan(self, api):
        tree = [
            {"name": "营收", "sub_sections": [{"name": "国内营收", "points": ["季度数据"]}]},
            {"name": "利润", "sub_sections": []},
        ]
        framework = {
            "topic": "比亚迪",
            "sections": ["营收", "利润"],
            "output_type": "industry_report",
            "depth": "standard",
            "region": "China",
            "time_range": "Last 3 years",
            "sections_tree": tree,
        }
        session = _make_session(topic="比亚迪", mode="framework", framework=framework)
        session_id = "test_tree_005"

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={"status": "completed"})

        with patch("src.api.research_api.session_manager") as mock_sm:
            mock_sm.get.return_value = session
            with patch("src.api.research_executor.get_executor", return_value=mock_executor):
                with patch("src.core.progress_streamer.ProgressStreamer"):
                    with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as mock_cm:
                        mock_cm.return_value.is_paused.return_value = False
                        result = await api._start_execution(session_id)

        plan = result.get("final_plan", {})
        assert plan.get("sections_tree") is not None, "final_plan must include sections_tree"
        assert plan["sections_tree"][0]["sub_sections"][0]["name"] == "国内营收"
        assert len(plan.get("section_details", [])) > 0
