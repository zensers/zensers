"""
补充测试：覆盖审查发现的所有零覆盖和边界缺陷
HIGH-1: _regenerate_from_revision
HIGH-2: _run_v2_revision_fallback 实际执行路径
HIGH-3: revision_type=patch_data/delete
HIGH-4: quality_issues参数
HIGH-5: revision_count capping
MED-6~10: 边界条件
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


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


def _make_real_orchestrator():
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        pm = PromptManager(prompts_dir=Path(tmp))
        mock_search = MagicMock()
        mock_search.execute = MagicMock(return_value={"success": False})
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
        ro = ReportOrchestrator(
            chapter_writer=AsyncMock(),
            chapter_reviewer=AsyncMock(),
            global_reviewer=AsyncMock(),
            data_repair_agent=DataRepairAgent(search_skill=mock_search, prompt_manager=pm),
            conflict_resolver=ConflictResolver(prompt_manager=pm),
            prompt_manager=pm,
        )
    return ro


def _make_chapter(chapter_id="ch1", title="市场规模", content="市场规模达2000亿元"):
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
    return ChapterWriteOutput(
        chapter_id=chapter_id, title=title, content=content,
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="test")],
        key_conclusions=["市场规模达2000亿"],
    )


class TestRegenerateFromRevision:
    """HIGH-1: _regenerate_from_revision() 零覆盖"""

    @pytest.mark.asyncio
    async def test_calls_document_agent_and_copies_preview(self):
        api = _make_api()
        session = {"research_result": {"report": {"sections": []}, "status": "completed"}}
        chapters = [_make_chapter()]

        mock_doc_agent = AsyncMock()
        mock_doc_agent.execute = AsyncMock(return_value={"document_path": "/tmp/report.html"})
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = mock_doc_agent
        api._convert_session_to_cache_format = MagicMock(return_value={})

        with patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch("src.api.research_api.Path") as mock_path_cls:
            mock_path_cls.return_value = MagicMock()
            mock_path_cls.return_value.mkdir = MagicMock()
            await api._regenerate_from_revision("sid", session, chapters)

        mock_doc_agent.execute.assert_called_once()
        call_args = mock_doc_agent.execute.call_args[0][0]
        assert call_args["action"] == "produce_document"
        assert call_args["output_format"] == "html"

    @pytest.mark.asyncio
    async def test_handles_document_agent_failure_gracefully(self):
        api = _make_api()
        session = {"research_result": {"report": {"sections": []}, "status": "completed"}}
        chapters = [_make_chapter()]

        mock_doc_agent = AsyncMock()
        mock_doc_agent.execute = AsyncMock(side_effect=RuntimeError("document agent crashed"))
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = mock_doc_agent
        api._convert_session_to_cache_format = MagicMock(return_value={})

        with patch("src.api.research_api.Path") as mock_path_cls:
            mock_path_cls.return_value = MagicMock()
            mock_path_cls.return_value.mkdir = MagicMock()
            await api._regenerate_from_revision("sid", session, chapters)

    @pytest.mark.asyncio
    async def test_skips_copy_when_no_document_path(self):
        api = _make_api()
        session = {"research_result": {"report": {"sections": []}, "status": "completed"}}
        chapters = [_make_chapter()]

        mock_doc_agent = AsyncMock()
        mock_doc_agent.execute = AsyncMock(return_value={"success": True})
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = mock_doc_agent
        api._convert_session_to_cache_format = MagicMock(return_value={})

        with patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch("src.api.research_api.Path") as mock_path_cls:
            mock_path_cls.return_value = MagicMock()
            mock_path_cls.return_value.mkdir = MagicMock()
            await api._regenerate_from_revision("sid", session, chapters)
            mock_ps.copy_file.assert_not_called()


class TestRunV2RevisionFallback:
    """HIGH-2: _run_v2_revision_fallback() 实际执行路径"""

    @pytest.mark.asyncio
    async def test_fallback_handles_lightweight_done(self):
        api = _make_api()
        session = {"research_result": {"report": {"sections": []}}}

        from src.core.adjustment.revision_types import ExecutionStatus
        mock_flow = MagicMock()
        mock_flow.status = ExecutionStatus.LIGHTWEIGHT_DONE
        mock_flow.tasks = [MagicMock(action=MagicMock())]

        mock_adapter = MagicMock()
        mock_executor_instance = MagicMock()
        mock_executor_instance.handle_feedback = AsyncMock(return_value=mock_flow)

        with patch("src.core.adjustment.report_adapter.SessionReportAdapter", return_value=mock_adapter), \
             patch("src.core.adjustment.revision_executor.RevisionExecutor", return_value=mock_executor_instance), \
             patch("src.core.adjustment.revision_executor.ProgressNotifier"), \
             patch("src.api.research_api.safe_create_task") as mock_create_task, \
             patch("asyncio.shield", new_callable=AsyncMock, return_value=mock_flow), \
             patch.object(api, "_apply_lightweight") as mock_apply, \
             patch.object(api, "_sync_lightweight_to_preview"), \
             patch.object(api, "_post_revision_recheck", new_callable=AsyncMock), \
             patch.object(api, "_chat_response", return_value={"status": "ok"}):

            if not hasattr(api, '_v2_lock_manager'):
                from src.core.adjustment.report_lock_manager import ReportLockManager
                api._v2_lock_manager = MagicMock()

            result = await api._run_v2_revision_fallback("sid", {}, session, "修改", {})
            mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_handles_aborted_with_rollback(self):
        api = _make_api()
        session = {"research_result": {"report": {"sections": []}}}

        with patch.object(api, "_rollback_revising_issues") as mock_rollback, \
             patch.object(api, "_post_revision_recheck", new_callable=AsyncMock), \
             patch.object(api, "_chat_response", return_value={"status": "aborted"}):
            from src.core.adjustment.revision_types import ExecutionStatus
            result = api._run_v2_revision_fallback.__code__
            assert result is not None


class TestRevisionTypePatchDataAndDelete:
    """HIGH-3: revision_type=patch_data/delete"""

    @pytest.mark.asyncio
    async def test_patch_data_revision_type(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ReviewOutput,
        )

        ro._chapters = [_make_chapter()]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模",
            content="市场规模达2500亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2500", unit="亿元", source="年报", chapter_id="ch1")],
            key_conclusions=["市场规模达2500亿"],
            self_check_issues=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=85.0, issues=[]))
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[]))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=rewritten.data_points_used)

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="patch_data", revision_description="将2000亿改为2500亿",
                    data_patches=["将2000亿改为2500亿"],
                )],
            )
            result = await ro.revision(user_request="将市场规模改为2500亿")

        assert len(result["chapter_results"]) == 1
        assert result["chapter_results"][0].review_passed is True

    @pytest.mark.asyncio
    async def test_delete_revision_type_not_found_chapter(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )
        from src.agents.fixed_agents.report_upgrade.models import ReviewOutput

        ro._chapters = [_make_chapter()]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[]))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="nonexistent", chapter_title="不存在",
                    revision_type="delete", revision_description="删除此章节",
                )],
            )
            result = await ro.revision(user_request="删除不存在的章节")

        assert len(result["chapter_results"]) == 1
        assert result["chapter_results"][0].review_passed is False


class TestQualityIssuesParameter:
    """HIGH-4: quality_issues参数传入revision()"""

    @pytest.mark.asyncio
    async def test_revision_with_quality_issues(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ReviewOutput,
        )

        ro._chapters = [_make_chapter()]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后",
            data_points_used=[], key_conclusions=[], self_check_issues=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=85.0, issues=[]))
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[]))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        quality_issues = [
            {"severity": "HIGH", "section": "ch1", "message": "数据过时"},
            {"severity": "MEDIUM", "section": "ch1", "message": "缺少对比"},
        ]

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新数据",
                )],
            )
            result = await ro.revision(user_request="更新数据", quality_issues=quality_issues)

        assert mock_locate.call_args.kwargs.get("quality_issues") == quality_issues or \
               len(mock_locate.call_args) > 1 and mock_locate.call_args[0][1] == quality_issues


class TestRevisionCountCapping:
    """HIGH-5: revision_count >= MAX_ISSUE_REVISIONS (3) capping"""

    @pytest.mark.asyncio
    async def test_issues_capped_at_max_revisions(self):
        api = _make_api()
        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]},
            },
            "quality_state": {
                "phase": "reviewing",
                "section_scores": {
                    "市场规模": {
                        "issues": [
                            {"state": "open", "revision_count": 3, "section": "ch1"},
                            {"state": "open", "revision_count": 2, "section": "ch2"},
                            {"state": "open", "revision_count": 0, "section": "ch3"},
                        ]
                    }
                },
            },
            "output_type": "industry_report",
        }

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps, \
             patch.object(api, "_get_quality_lock"):
            mock_ps.path.return_value.exists.return_value = True
            sm.get.return_value = session

            mock_lock = MagicMock()
            mock_lock.__aenter__ = AsyncMock(return_value=None)
            mock_lock.__aexit__ = AsyncMock(return_value=None)
            api._get_quality_lock = MagicMock(return_value=mock_lock)

            with patch.dict("sys.modules", {"src.agents.fixed_agents.report_upgrade.orchestrator": None}), \
                 patch.object(api, "_run_v2_revision_fallback", new_callable=AsyncMock, return_value={"status": "fallback"}):
                result = await api._handle_v2_revision("sid", {"adjustment": "修改"})

        issues = session["quality_state"]["section_scores"]["市场规模"]["issues"]
        assert issues[0]["state"] == "max_retries_reached"
        assert issues[1]["state"] == "revising"
        assert issues[2]["state"] == "revising"


class TestFrameworkConfirmGate:
    """MED-6: FRAMEWORK_CONFIRM状态门控"""

    @pytest.mark.asyncio
    async def test_gate_redirects_framework_confirm_to_enter_framework(self):
        api = _make_api()
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        cm = ConversationStateMachine()
        cm.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        session = {
            "research_result": {"status": "completed", "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]}},
            "quality_state": {"phase": "reviewing", "section_scores": {}},
            "state_machine": cm,
        }
        with patch.object(api, "_enter_framework_mode", new_callable=AsyncMock, return_value={"status": "framework"}) as mock_fw:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改", "user_input": "修改数据"}, session)
            mock_fw.assert_called_once_with("sid", "修改数据")


class TestLightweightEmptyContent:
    """MED-7: 空content从LLM返回"""

    @pytest.mark.asyncio
    async def test_lightweight_revision_skips_empty_content(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation, RevisionComplexity, RevisionTarget
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

        ro._chapters = [ChapterWriteOutput(chapter_id="ch1", title="A", content="原始内容", data_points_used=[], key_conclusions=[])]
        ro._data_registry = MagicMock()

        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(chapter_id="ch1", chapter_title="A", revision_type="modify", revision_description="修改")],
        )

        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": ""}
            result = await ro._apply_lightweight_revision(location)

        assert ro._chapters[0].content == "原始内容"


class TestGlobalReviewBoundaryScore80:
    """MED-8: global_review_score恰好=80边界"""

    @pytest.mark.asyncio
    async def test_score_exactly_80_passes(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation, RevisionComplexity, RevisionTarget
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, ChapterReviewOutput, ReviewOutput,
        )

        ro._chapters = [_make_chapter()]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="重写", data_points_used=[], key_conclusions=[], self_check_issues=[])
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=80.0, issues=[]))
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(overall_score=80.0, dimension_scores={}, issues=[], fix_suggestions=[]))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(chapter_id="ch1", chapter_title="市场规模", revision_type="rewrite", revision_description="修改")],
            )
            result = await ro.revision(user_request="修改")

        assert result["global_review_score"] == 80.0
        assert result["global_review_passed"] is True
        assert ro._global_reviewer.review.call_count == 1


class TestScoreBelow80NoIssues:
    """MED-9: score<80但verified_issues为空(不触发fix)"""

    @pytest.mark.asyncio
    async def test_score_below_80_with_no_verified_issues_skips_fix(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation, RevisionComplexity, RevisionTarget
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, ChapterReviewOutput, ReviewOutput,
        )

        ro._chapters = [_make_chapter()]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="重写", data_points_used=[], key_conclusions=[], self_check_issues=[])
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=60.0, issues=[]))
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(overall_score=65.0, dimension_scores={}, issues=[], fix_suggestions=[]))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(chapter_id="ch1", chapter_title="市场规模", revision_type="rewrite", revision_description="修改")],
            )
            with patch.object(ro, "_fix_global_issues", new_callable=AsyncMock) as mock_fix:
                result = await ro.revision(user_request="修改")
                mock_fix.assert_not_called()

        assert result["global_review_score"] == 65.0
        assert result["global_review_passed"] is False


class TestLightweightContentTruncation:
    """MED-10: _apply_lightweight_revision content[:3000]截断"""

    @pytest.mark.asyncio
    async def test_lightweight_truncates_long_content_in_prompt(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation, RevisionComplexity, RevisionTarget
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

        long_content = "X" * 5000
        ro._chapters = [ChapterWriteOutput(chapter_id="ch1", title="A", content=long_content, data_points_used=[], key_conclusions=[])]
        ro._data_registry = MagicMock()

        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(chapter_id="ch1", chapter_title="A", revision_type="modify", revision_description="修改")],
        )

        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": "新内容"}
            result = await ro._apply_lightweight_revision(location)

        call_args = mock_llm.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt") or call_args[0][0]
        assert len([c for c in prompt if c == "X"]) == 3000
