import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime


def _make_api():
    from src.api.research_api import ResearchAPI
    with patch("src.api.research_api.ResearchOrchestrator"), \
         patch("src.api.research_api.PreviewGenerator"), \
         patch("src.api.research_api.ConversationToolSet"):
        api = ResearchAPI()
    api._revision_task = None
    api._executor_tasks = {}
    api._revision_locks = {}
    return api


def _make_session_with_report():
    return {
        "research_result": {
            "status": "completed",
            "report": {
                "sections": [
                    {"id": "ch1", "title": "市场规模", "content": "市场规模达2000亿元"},
                ],
                "topic": "新能源汽车",
            },
        },
        "research_context": {
            "topic": "新能源汽车",
            "directions": ["市场分析"],
            "framework": {},
        },
        "quality_state": {
            "phase": "reviewing",
            "section_scores": {},
        },
        "output_type": "industry_report",
    }


class TestHandleV2RevisionPreconditions:
    @pytest.mark.asyncio
    async def test_returns_error_when_session_not_found(self):
        api = _make_api()
        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = None
            result = await api._handle_v2_revision("bad_id", {})
        assert result.get("error_code") == "SESSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_message_when_research_not_completed(self):
        api = _make_api()
        session = _make_session_with_report()
        session["research_result"]["status"] = "running"
        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            result = await api._handle_v2_revision("sid", {})
        assert "尚未生成完成" in str(result) or result.get("error_code")

    @pytest.mark.asyncio
    async def test_returns_message_when_no_sections(self):
        api = _make_api()
        session = _make_session_with_report()
        session["research_result"]["report"]["sections"] = []
        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            result = await api._handle_v2_revision("sid", {})
        assert "为空" in str(result) or result.get("error_code")


class TestHandleV2RevisionIntegration:
    @pytest.mark.asyncio
    async def test_calls_orchestrator_revision_and_writes_back(self):
        api = _make_api()
        session = _make_session_with_report()

        mock_ro = MagicMock()
        mock_ro.revision = AsyncMock(return_value={
            "chapter_results": [],
            "global_review_score": 90.0,
            "global_review_passed": True,
            "data_registry_snapshot": {"metrics": {}},
        })
        mock_ro._chapters = [MagicMock(chapter_id="ch1", title="市场规模", content="修订后", key_conclusions=[])]
        mock_ro._data_registry = MagicMock()
        mock_ro._data_registry.to_snapshot.return_value = {"metrics": {}}

        mock_pm = MagicMock()

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch("src.agents.fixed_agents.report_upgrade.orchestrator.ReportOrchestrator", return_value=mock_ro) as MockRO, \
             patch("src.agents.fixed_agents.report_upgrade.chapter_writer.ChapterWriter", return_value=MagicMock()) as MockCW, \
             patch("src.agents.fixed_agents.report_upgrade.chapter_reviewer.ChapterReviewAgent", return_value=MagicMock()) as MockCRA, \
             patch("src.agents.fixed_agents.report_upgrade.global_reviewer.GlobalReviewAgent", return_value=MagicMock()) as MockGRA, \
             patch("src.agents.fixed_agents.report_upgrade.data_repair.DataRepairAgent", return_value=MagicMock()) as MockDRA, \
             patch("src.agents.fixed_agents.report_upgrade.data_repair.ConflictResolver", return_value=MagicMock()) as MockCR, \
             patch("src.agents.fixed_agents.report_upgrade.prompt_manager.PromptManager", return_value=mock_pm), \
             patch.object(api, "_apply_revision_to_session") as mock_apply, \
             patch.object(api, "_regenerate_from_revision", new_callable=AsyncMock) as mock_regen, \
             patch.object(api, "_post_revision_recheck", new_callable=AsyncMock) as mock_recheck, \
             patch.object(api, "_chat_response", return_value={"status": "ok"}):

            mock_ps.path.return_value.exists.return_value = True
            mock_lock = MagicMock()
            mock_lock.__aenter__ = AsyncMock(return_value=None)
            mock_lock.__aexit__ = AsyncMock(return_value=None)
            api._get_quality_lock = MagicMock(return_value=mock_lock)

            sm.get.return_value = session
            api._orchestrator = MagicMock()
            api._orchestrator._skill_registry = MagicMock()
            api._orchestrator._skill_registry.get.return_value = None

            result = await api._handle_v2_revision("sid", {"adjustment": "修改市场规模"})

            mock_ro.revision.assert_called_once()
            call_kwargs = mock_ro.revision.call_args
            assert call_kwargs.kwargs.get("user_request") == "修改市场规模" or \
                   (call_kwargs[0] and call_kwargs[0][0] == "修改市场规模")
            mock_apply.assert_called_once()
            mock_regen.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_import_error(self):
        api = _make_api()
        session = _make_session_with_report()

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch.dict("sys.modules", {"src.agents.fixed_agents.report_upgrade.orchestrator": None}), \
             patch.object(api, "_run_v2_revision_fallback", new_callable=AsyncMock, return_value={"status": "fallback"}) as mock_fallback:

            mock_ps.path.return_value.exists.return_value = True
            mock_lock = MagicMock()
            mock_lock.__aenter__ = AsyncMock(return_value=None)
            mock_lock.__aexit__ = AsyncMock(return_value=None)
            api._get_quality_lock = MagicMock(return_value=mock_lock)

            sm.get.return_value = session
            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})
            assert result.get("status") == "fallback"

    @pytest.mark.asyncio
    async def test_rollback_on_revision_exception(self):
        api = _make_api()
        session = _make_session_with_report()

        mock_ro = MagicMock()
        mock_ro.revision = AsyncMock(side_effect=RuntimeError("revision failed"))
        mock_pm = MagicMock()

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch("src.agents.fixed_agents.report_upgrade.orchestrator.ReportOrchestrator", return_value=mock_ro), \
             patch("src.agents.fixed_agents.report_upgrade.chapter_writer.ChapterWriter", return_value=MagicMock()), \
             patch("src.agents.fixed_agents.report_upgrade.chapter_reviewer.ChapterReviewAgent", return_value=MagicMock()), \
             patch("src.agents.fixed_agents.report_upgrade.global_reviewer.GlobalReviewAgent", return_value=MagicMock()), \
             patch("src.agents.fixed_agents.report_upgrade.data_repair.DataRepairAgent", return_value=MagicMock()), \
             patch("src.agents.fixed_agents.report_upgrade.data_repair.ConflictResolver", return_value=MagicMock()), \
             patch("src.agents.fixed_agents.report_upgrade.prompt_manager.PromptManager", return_value=mock_pm), \
             patch.object(api, "_rollback_revising_issues") as mock_rollback, \
             patch.object(api, "_chat_response", return_value={"status": "error"}):

            mock_ps.path.return_value.exists.return_value = True
            mock_lock = MagicMock()
            mock_lock.__aenter__ = AsyncMock(return_value=None)
            mock_lock.__aexit__ = AsyncMock(return_value=None)
            api._get_quality_lock = MagicMock(return_value=mock_lock)

            sm.get.return_value = session
            api._orchestrator = MagicMock()
            api._orchestrator._skill_registry = MagicMock()
            api._orchestrator._skill_registry.get.return_value = None

            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})
            mock_rollback.assert_called_once()


class TestHandleV2RevisionHelperWrappers:
    def test_sections_to_chapters_delegates(self):
        api = _make_api()
        sections = [{"id": "ch1", "title": "A", "content": "内容"}]
        result = api._sections_to_chapters(sections)
        assert len(result) == 1
        assert result[0].chapter_id == "ch1"

    def test_restore_data_registry_delegates(self):
        api = _make_api()
        session = {}
        result = api._restore_data_registry(session)
        assert result is not None

    def test_get_framework_config_delegates(self):
        api = _make_api()
        session = {"output_type": "industry_report"}
        result = api._get_framework_config(session)
        assert "name" in result

    def test_get_task_structure_delegates(self):
        api = _make_api()
        session = {"research_context": {"topic": "测试", "directions": []}}
        result = api._get_task_structure(session)
        assert result["topic"] == "测试"

    def test_apply_revision_to_session_delegates(self):
        api = _make_api()
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        session = {"research_result": {"report": {"sections": []}}}
        chapters = [ChapterWriteOutput(chapter_id="ch1", title="A", content="B", data_points_used=[], key_conclusions=[])]
        registry = DataRegistry()
        result = {"chapter_results": [], "global_review_score": 80, "global_review_passed": True}
        api._apply_revision_to_session(session, result, chapters, registry)
        assert session["research_result"]["report"]["sections"][0]["content"] == "B"


class TestPhaseGateLogic:
    @pytest.mark.asyncio
    async def test_blocks_revise_in_understanding_state(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        sm_mock = MagicMock()
        cm = ConversationStateMachine()
        session = _make_session_with_report()
        session["state_machine"] = cm
        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
        assert "请先完成研究" in str(result) or "完成研究" in str(result)

    @pytest.mark.asyncio
    async def test_blocks_revise_in_executing_state_redirects_to_inject(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        cm = ConversationStateMachine()
        cm.force_set_state(ConversationState.EXECUTING)
        session = _make_session_with_report()
        session["state_machine"] = cm
        with patch.object(api, "_handle_inject_requirement", new_callable=AsyncMock, return_value={"status": "inject"}) as mock_inject:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改", "user_input": "修改数据"}, session)
            mock_inject.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_revise_in_cancelled_state(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        cm = ConversationStateMachine()
        cm.force_set_state(ConversationState.CANCELLED)
        session = _make_session_with_report()
        session["state_machine"] = cm
        with patch.object(api, "_chat_response", return_value={"msg": "cancelled"}):
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
        assert "取消" in str(result) or "cancelled" in str(result).lower()

    @pytest.mark.asyncio
    async def test_allows_revise_in_previewing_state(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        cm = ConversationStateMachine()
        cm.force_set_state(ConversationState.PREVIEWING)
        session = _make_session_with_report()
        session["state_machine"] = cm
        with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock, return_value={"status": "ok"}) as mock_rev:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
            mock_rev.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_revise_in_completed_state(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        cm = ConversationStateMachine()
        cm.force_set_state(ConversationState.COMPLETED)
        session = _make_session_with_report()
        session["state_machine"] = cm
        with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock, return_value={"status": "ok"}) as mock_rev:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
            mock_rev.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_revise_without_conv_machine(self):
        api = _make_api()
        session = _make_session_with_report()
        with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock, return_value={"status": "ok"}) as mock_rev:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
            mock_rev.assert_called_once()


class TestPreconditionChecks:
    @pytest.mark.asyncio
    async def test_rejects_when_no_preview_exists(self):
        api = _make_api()
        session = _make_session_with_report()
        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps:
            sm.get.return_value = session
            mock_ps.path.return_value.exists.return_value = False
            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})
        assert "预览不存在" in str(result) or "重新生成" in str(result)

    @pytest.mark.asyncio
    async def test_rejects_when_concurrent_revision_running(self):
        api = _make_api()
        session = _make_session_with_report()
        running_task = MagicMock()
        running_task.done.return_value = False
        api._executor_tasks["rev_sid"] = running_task
        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps:
            sm.get.return_value = session
            mock_ps.path.return_value.exists.return_value = True
            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})
        assert "正在执行" in str(result) or "等待" in str(result)
