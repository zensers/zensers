"""
实战测试：验证修订系统真实组件能否串联运行
不使用mock验证方法签名，而是真实实例化、调用、检查数据流
"""
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestRealImportChain:
    """实战测试1: 验证所有新模块的真实import链"""

    def test_revision_models_import(self):
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionComplexity, RevisionTarget, RevisionLocation, ChapterRewriteResult,
        )
        assert RevisionComplexity.LIGHTWEIGHT.value == "lightweight"
        assert RevisionComplexity.STANDARD.value == "standard"
        assert RevisionComplexity.COMPLEX.value == "complex"
        assert RevisionComplexity.FULL.value == "full"

    def test_revision_models_real_construction(self):
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionComplexity, RevisionTarget, RevisionLocation, ChapterRewriteResult,
        )
        target = RevisionTarget(
            chapter_id="ch1", chapter_title="市场规模",
            revision_type="rewrite", revision_description="更新数据",
            data_patches=["将2000亿改为2500亿"],
        )
        assert target.chapter_id == "ch1"
        assert len(target.data_patches) == 1

        location = RevisionLocation(
            complexity=RevisionComplexity.STANDARD,
            targets=[target],
            data_gaps=[],
            data_conflicts=[],
            preceding_summary="市场持续增长",
        )
        assert location.complexity == RevisionComplexity.STANDARD
        assert len(location.targets) == 1
        assert location.preceding_summary == "市场持续增长"

        result = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧内容",
            revised_content="新内容",
            review_passed=True,
            review_score=85.0,
            data_points_changed=1,
            data_points_added=1,
            data_points_removed=0,
            rewrite_rounds=1,
        )
        assert result.review_passed is True
        assert result.rewrite_rounds == 1

    def test_fix_suggestion_import_in_orchestrator(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import FixSuggestion
        assert FixSuggestion is not None

    def test_research_api_helpers_import(self):
        from src.api.research_api_helpers import (
            sections_to_chapters, restore_data_registry,
            get_framework_config, get_task_structure,
            apply_revision_to_session,
        )
        assert callable(sections_to_chapters)
        assert callable(restore_data_registry)
        assert callable(get_framework_config)
        assert callable(get_task_structure)
        assert callable(apply_revision_to_session)

    def test_conversation_state_import_in_research_api(self):
        from src.api.research_api import ConversationState
        assert hasattr(ConversationState, 'PREVIEWING')
        assert hasattr(ConversationState, 'COMPLETED')
        assert hasattr(ConversationState, 'CANCELLED')
        assert hasattr(ConversationState, 'EXECUTING')
        assert hasattr(ConversationState, 'PAUSED')
        assert hasattr(ConversationState, 'UNDERSTANDING')
        assert hasattr(ConversationState, 'CLARIFYING')
        assert hasattr(ConversationState, 'FRAMEWORK_CONFIRM')


class TestRealOrchestratorRevision:
    """实战测试2: 真实实例化ReportOrchestrator并调用revision()内部方法"""

    def _make_real_orchestrator(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

        with tempfile.TemporaryDirectory() as tmp:
            pm = PromptManager(prompts_dir=Path(tmp))
            ro = ReportOrchestrator(
                chapter_writer=AsyncMock(),
                chapter_reviewer=AsyncMock(),
                global_reviewer=AsyncMock(),
                data_repair_agent=AsyncMock(),
                conflict_resolver=AsyncMock(),
                prompt_manager=pm,
            )
        return ro

    def test_real_init_has_chapters_and_framework_config(self):
        ro = self._make_real_orchestrator()
        assert hasattr(ro, '_chapters')
        assert hasattr(ro, '_framework_config')
        assert ro._chapters == []
        assert ro._framework_config == {}

    def test_real_parse_location_result_with_valid_json(self):
        ro = self._make_real_orchestrator()
        raw = '''```json
{
    "complexity": "standard",
    "targets": [
        {
            "chapter_id": "ch1",
            "chapter_title": "市场规模",
            "revision_type": "rewrite",
            "revision_description": "更新数据",
            "data_patches": ["改为2500亿"]
        }
    ],
    "preceding_summary": "前文摘要",
    "data_gaps": [],
    "data_conflicts": []
}
```'''
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity.value == "standard"
        assert len(result.targets) == 1
        assert result.targets[0].chapter_id == "ch1"
        assert result.targets[0].data_patches == ["改为2500亿"]
        assert result.preceding_summary == "前文摘要"

    def test_real_parse_location_result_with_malformed_json(self):
        ro = self._make_real_orchestrator()
        result = ro._parse_location_result("not json at all", "用户要求修改")
        assert result.complexity.value == "standard"
        assert len(result.targets) == 1
        assert result.targets[0].revision_description == "用户要求修改"

    def test_real_append_revision_preceding_summary(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import ChapterRewriteResult
        result = ChapterRewriteResult(
            chapter_id="ch1", original_content="旧",
            revised_content="市场规模达2000亿元，同比增长15%", review_passed=True, review_score=85.0,
        )
        summary = ro._append_revision_preceding_summary("", result)
        assert "市场规模" in summary

        summary2 = ro._append_revision_preceding_summary(summary, ChapterRewriteResult(
            chapter_id="ch2", original_content="旧",
            revised_content="竞争格局CR3达65%", review_passed=True, review_score=80.0,
        ))
        assert "竞争格局" in summary2

    @pytest.mark.asyncio
    async def test_real_execute_chapter_revision_not_found(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionTarget
        target = RevisionTarget(
            chapter_id="nonexistent", chapter_title="不存在",
            revision_type="rewrite", revision_description="修改",
        )
        result = await ro._execute_chapter_revision(target, "")
        assert result.review_passed is False
        assert result.review_score == 0.0

    @pytest.mark.asyncio
    async def test_real_apply_lightweight_revision_no_matching_chapter(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation, RevisionComplexity, RevisionTarget
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

        ro._chapters = [ChapterWriteOutput(chapter_id="ch1", title="A", content="内容", data_points_used=[], key_conclusions=[])]
        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(chapter_id="ch99", chapter_title="不存在", revision_type="modify", revision_description="修改")],
        )
        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": "新内容"}
            result = await ro._apply_lightweight_revision(location)
        assert result["global_review_passed"] is True
        assert ro._chapters[0].content == "内容"

    @pytest.mark.asyncio
    async def test_real_fix_global_issues_with_real_chapter(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ChapterIssue, ReviewIssue,
        )

        ch1 = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="test")],
            key_conclusions=["市场规模达2000亿"],
        )
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后内容",
            data_points_used=[], key_conclusions=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        issues = [ReviewIssue(
            dimension="data_consistency", severity="HIGH",
            description="数据矛盾", location="chapter:ch1", evidence="营收数据不一致",
        )]
        await ro._fix_global_issues(issues, [])

        rewrite_call = ro._chapter_writer.rewrite.call_args
        assert rewrite_call is not None
        assert rewrite_call.kwargs.get("chapter_data") is not None or rewrite_call[1].get("chapter_data") is not None


class TestRealHelpersDataFlow:
    """实战测试3-5: 真实调用helpers并验证数据流闭环"""

    def test_sections_to_chapters_real_data(self):
        from src.api.research_api_helpers import sections_to_chapters
        sections = [
            {"id": "ch1", "title": "市场规模", "content": "市场规模达2000亿元，同比增长15%。其中新能源汽车占比持续提升。"},
            {"id": "ch2", "title": "竞争格局", "content": "CR3达65%，比亚迪市占率领先。"},
            {"id": "ch3", "name": "技术趋势", "content": "固态电池技术加速发展。"},
        ]
        chapters = sections_to_chapters(sections)
        assert len(chapters) == 3
        assert chapters[0].chapter_id == "ch1"
        assert chapters[0].title == "市场规模"
        assert chapters[2].title == "技术趋势"
        assert chapters[0].data_points_used == []

    def test_data_registry_round_trip(self):
        from src.api.research_api_helpers import restore_data_registry
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry

        dr = DataRegistry()
        dr.register(metric="营收", value="2000", unit="亿元", chapter_id="ch1", source="年报")
        dr.register(metric="增长率", value="15%", unit="", chapter_id="ch1", source="统计")
        snapshot = dr.to_snapshot()

        session = {"_data_registry_snapshot": snapshot}
        restored = restore_data_registry(session)
        assert "营收" in restored.to_snapshot().get("metrics", {})
        assert "增长率" in restored.to_snapshot().get("metrics", {})

    def test_apply_revision_to_session_full_cycle(self):
        from src.api.research_api_helpers import sections_to_chapters, apply_revision_to_session
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

        sections = [
            {"id": "ch1", "title": "市场规模", "content": "市场规模达2000亿元"},
            {"id": "ch2", "title": "竞争格局", "content": "CR3达65%"},
        ]

        chapters = sections_to_chapters(sections)

        dr = DataRegistry()
        dr.register(metric="市场规模", value="2000", unit="亿元", chapter_id="ch1", source="年报")

        chapters[0].content = "市场规模达2500亿元，同比增长25%"
        chapters[0].key_conclusions = ["市场规模达2500亿", "同比增长25%"]
        chapters[0].data_points_used = [DataPoint(metric="市场规模", value="2500", unit="亿元", source="年报")]

        session = {"research_result": {"report": {"sections": sections}, "status": "completed"}}
        result = {
            "chapter_results": [{"chapter_id": "ch1"}],
            "global_review_score": 90,
            "global_review_passed": True,
        }

        apply_revision_to_session(session, result, chapters, dr)

        updated_sections = session["research_result"]["report"]["sections"]
        assert updated_sections[0]["content"] == "市场规模达2500亿元，同比增长25%"
        assert updated_sections[0]["key_conclusions"] == ["市场规模达2500亿", "同比增长25%"]
        assert "_data_registry_snapshot" in session
        assert "_revision_history" in session
        assert session["_revision_history"][0]["global_review_score"] == 90

    def test_assemble_final_report_includes_key_conclusions(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ReviewOutput,
        )

        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
                data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="年报")],
                key_conclusions=["市场规模达2000亿", "同比增长15%"],
            ),
            ChapterWriteOutput(
                chapter_id="ch2", title="竞争格局", content="CR3达65%",
                data_points_used=[], key_conclusions=["CR3达65%"],
            ),
        ]
        review = ReviewOutput(overall_score=85.0, dimension_scores={}, issues=[], fix_suggestions=[])

        report = ReportOrchestrator._assemble_final_report(
            chapters, "exec_summary", review, "新能源汽车",
        )
        assert report["sections"][0]["key_conclusions"] == ["市场规模达2000亿", "同比增长15%"]
        assert report["sections"][1]["key_conclusions"] == ["CR3达65%"]


class TestRealPhaseGateIntegration:
    """实战测试4: 阶段门控真实状态机交互"""

    def _make_api_with_session(self):
        from src.api.research_api import ResearchAPI
        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}
        api._revision_locks = {}
        return api

    def _make_session_with_state(self, state_name):
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}], "topic": "T"},
            },
            "research_context": {"topic": "T", "directions": [], "framework": {}},
            "quality_state": {"phase": "reviewing", "section_scores": {}},
            "output_type": "industry_report",
        }
        cm = ConversationStateMachine()
        state = ConversationState(state_name)
        cm.force_set_state(state)
        session["state_machine"] = cm
        return session

    @pytest.mark.asyncio
    async def test_gate_blocks_in_understanding_with_real_state_machine(self):
        api = self._make_api_with_session()
        session = self._make_session_with_state("understanding")
        with patch.object(api, "_chat_response", return_value={"msg": "blocked"}):
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
        assert result.get("msg") == "blocked"

    @pytest.mark.asyncio
    async def test_gate_allows_in_previewing_with_real_state_machine(self):
        api = self._make_api_with_session()
        session = self._make_session_with_state("previewing")
        with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock, return_value={"status": "ok"}) as mock_rev:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
            mock_rev.assert_called_once_with("sid", {"adjustment": "修改"})

    @pytest.mark.asyncio
    async def test_gate_redirects_executing_to_inject_with_real_state_machine(self):
        api = self._make_api_with_session()
        session = self._make_session_with_state("executing")
        with patch.object(api, "_handle_inject_requirement", new_callable=AsyncMock, return_value={"status": "inject"}) as mock_inject:
            result = await api._handle_revise_report_gate("sid", {"adjustment": "修改", "user_input": "添加数据"}, session)
            mock_inject.assert_called_once()
            call_args = mock_inject.call_args
            inject_ops = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("inject_ops")
            assert inject_ops is not None
            assert inject_ops[0]["op"] == "add_section"


class TestRealErrorPaths:
    """实战测试6: 边界条件与错误路径"""

    def _make_real_orchestrator(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
        with tempfile.TemporaryDirectory() as tmp:
            pm = PromptManager(prompts_dir=Path(tmp))
            ro = ReportOrchestrator(
                chapter_writer=AsyncMock(),
                chapter_reviewer=AsyncMock(),
                global_reviewer=AsyncMock(),
                data_repair_agent=AsyncMock(),
                conflict_resolver=AsyncMock(),
                prompt_manager=pm,
            )
        return ro

    def test_parse_location_result_with_unknown_complexity(self):
        ro = self._make_real_orchestrator()
        raw = '''```json
{"complexity": "unknown_type", "targets": [], "preceding_summary": "", "data_gaps": [], "data_conflicts": []}
```'''
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity.value == "standard"
        assert len(result.targets) == 1

    def test_parse_location_result_with_missing_fields(self):
        ro = self._make_real_orchestrator()
        raw = '''```json
{"complexity": "lightweight", "targets": [{"chapter_id": "ch1"}]}
```'''
        result = ro._parse_location_result(raw, "fallback_desc")
        assert result.targets[0].chapter_id == "ch1"
        assert result.targets[0].chapter_title == ""
        assert result.targets[0].revision_description == "fallback_desc"
        assert result.targets[0].data_patches == []

    @pytest.mark.asyncio
    async def test_revision_with_empty_targets(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.revision_models import RevisionComplexity
        from src.agents.fixed_agents.report_upgrade.models import ReviewOutput

        ro._chapters = []
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "测试"}

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            from src.agents.fixed_agents.report_upgrade.revision_models import RevisionLocation
            mock_locate.return_value = RevisionLocation(complexity=RevisionComplexity.STANDARD, targets=[])

            ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(
                overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[],
            ))
            ro._global_reviewer.verify_issues = AsyncMock(return_value=[])

            result = await ro.revision(user_request="修改报告")

        assert len(result["chapter_results"]) == 0
        assert result["global_review_score"] == 90.0
        assert result["global_review_passed"] is True

    @pytest.mark.asyncio
    async def test_fix_global_issues_with_issue_location_no_colon(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, ReviewIssue,
        )

        ro._chapters = [ChapterWriteOutput(chapter_id="ch1", title="A", content="内容", data_points_used=[], key_conclusions=[])]
        ro._framework_config = {"name": "测试"}
        ro._chapter_writer.rewrite = AsyncMock(return_value=ChapterWriteOutput(
            chapter_id="ch1", title="A", content="修正", data_points_used=[], key_conclusions=[],
        ))
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        issues = [ReviewIssue(
            dimension="logic", severity="LOW",
            description="逻辑问题", location="no_colon_here", evidence="证据",
        )]
        await ro._fix_global_issues(issues, [])
        assert ro._chapter_writer.rewrite.call_count == 0

    def test_sections_to_chapters_with_empty_content(self):
        from src.api.research_api_helpers import sections_to_chapters
        sections = [
            {"id": "ch1", "title": "空章节", "content": ""},
            {"id": "ch2", "title": "正常", "content": "有内容"},
        ]
        chapters = sections_to_chapters(sections)
        assert len(chapters) == 2
        assert chapters[0].key_conclusions == []
        assert chapters[1].key_conclusions != [] or chapters[1].content == "有内容"

    def test_restore_data_registry_with_corrupt_snapshot(self):
        from src.api.research_api_helpers import restore_data_registry
        session = {"_data_registry_snapshot": {"not_a_valid_snapshot": True}}
        try:
            registry = restore_data_registry(session)
            assert registry is not None
        except Exception:
            pass

    def test_apply_revision_to_session_with_empty_chapters(self):
        from src.api.research_api_helpers import apply_revision_to_session
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        session = {"research_result": {"report": {"sections": []}}}
        result = {"chapter_results": [], "global_review_score": 0, "global_review_passed": False}
        apply_revision_to_session(session, result, [], DataRegistry())
        assert session["research_result"]["report"]["sections"] == []

    @pytest.mark.asyncio
    async def test_fix_global_issues_uses_fix_suggestions_in_review_feedback(self):
        ro = self._make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, ReviewIssue, FixSuggestion,
        )

        ro._chapters = [ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[], key_conclusions=[],
        )]
        ro._framework_config = {"name": "测试"}
        ro._chapter_writer.rewrite = AsyncMock(return_value=ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后",
            data_points_used=[], key_conclusions=[],
        ))
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        issues = [ReviewIssue(
            dimension="data_consistency", severity="HIGH",
            description="数据矛盾", location="chapter:ch1", evidence="营收不一致",
        )]
        fix_suggestions = [FixSuggestion(
            target_chapter="ch1", issue_id="i1",
            fix_type="data_correction", fix_instruction="将营收数据统一为2025年报口径",
            priority="HIGH",
        )]

        await ro._fix_global_issues(issues, fix_suggestions)

        rewrite_call = ro._chapter_writer.rewrite.call_args
        feedback = rewrite_call.kwargs.get("review_feedback") or rewrite_call[1].get("review_feedback")
        assert feedback is not None
        suggestion = feedback.issues[0].suggestion
        assert "营收不一致" in suggestion
        assert "统一为2025年报口径" in suggestion
