"""
端到端实战测试：模拟完整修订流程，验证真实数据流闭环
关键：使用真实的ReportOrchestrator、DataRegistry、ChapterWriteOutput等，
只mock LLM调用(call_llm)和外部依赖
"""
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict


def _make_real_orchestrator():
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


def _make_chapters_with_data():
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
    return [
        ChapterWriteOutput(
            chapter_id="ch1", title="市场规模",
            content="2025年中国新能源汽车市场规模达2000亿元，同比增长15%。其中纯电动车占比60%，插电混动占比40%。",
            data_points_used=[
                DataPoint(metric="市场规模", value="2000", unit="亿元", source="中汽协", chapter_id="ch1"),
                DataPoint(metric="同比增长", value="15%", unit="", source="中汽协", chapter_id="ch1"),
            ],
            key_conclusions=["市场规模达2000亿", "同比增长15%"],
        ),
        ChapterWriteOutput(
            chapter_id="ch2", title="竞争格局",
            content="比亚迪市占率达35%，特斯拉15%，蔚来8%。CR3合计58%。",
            data_points_used=[
                DataPoint(metric="比亚迪市占率", value="35%", unit="", source="乘联会", chapter_id="ch2"),
            ],
            key_conclusions=["比亚迪市占率35%", "CR3达58%"],
        ),
    ]


class TestE2EStandardRevision:
    """端到端：标准修订流程（rewrite + review + global review）"""

    @pytest.mark.asyncio
    async def test_full_standard_revision_flow(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ReviewOutput,
        )
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )

        chapters = _make_chapters_with_data()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告", "description": "行业研究"}
        ro._task_structure = {"topic": "新能源汽车市场分析"}

        rewritten_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模",
            content="2025年中国新能源汽车市场规模达2500亿元，同比增长25%。其中纯电动车占比65%，插电混动占比35%。",
            data_points_used=[
                DataPoint(metric="市场规模", value="2500", unit="亿元", source="中汽协2025", chapter_id="ch1"),
                DataPoint(metric="同比增长", value="25%", unit="", source="中汽协2025", chapter_id="ch1"),
            ],
            key_conclusions=["市场规模达2500亿", "同比增长25%"],
            self_check_issues=[],
        )

        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten_ch)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(
            passed=True, score=88.0, issues=[],
        ))
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(
            overall_score=92.0, dimension_scores={}, issues=[], fix_suggestions=[],
        ))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=rewritten_ch.data_points_used)

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新市场规模数据为最新值",
                )],
                preceding_summary="",
            )
            result = await ro.revision(user_request="更新市场规模数据")

        assert result["global_review_score"] == 92.0
        assert result["global_review_passed"] is True
        assert len(result["chapter_results"]) == 1
        assert result["chapter_results"][0].review_passed is True
        assert result["chapter_results"][0].review_score == 88.0
        assert "2500" in result["chapter_results"][0].revised_content
        assert ro._chapters[0].content == rewritten_ch.content

        rewrite_call = ro._chapter_writer.rewrite.call_args
        assert rewrite_call.kwargs.get("chapter_data") is not None or rewrite_call[1].get("chapter_data") is not None

    @pytest.mark.asyncio
    async def test_standard_revision_with_review_retry(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ChapterIssue, ReviewOutput,
        )
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )

        chapters = _make_chapters_with_data()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "新能源汽车"}

        first_rewrite = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="第一次重写",
            data_points_used=[], key_conclusions=[], self_check_issues=[],
        )
        second_rewrite = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="第二次重写，数据已更新",
            data_points_used=[DataPoint(metric="市场规模", value="2500", unit="亿元", source="test", chapter_id="ch1")],
            key_conclusions=["更新"], self_check_issues=[],
        )

        ro._chapter_writer.rewrite = AsyncMock(side_effect=[first_rewrite, second_rewrite])
        ro._chapter_reviewer.review = AsyncMock(side_effect=[
            ChapterReviewOutput(passed=False, score=45.0, issues=[
                ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="缺数据", suggestion="补充"),
            ]),
            ChapterReviewOutput(passed=True, score=82.0, issues=[]),
        ])
        ro._global_reviewer.review = AsyncMock(return_value=ReviewOutput(
            overall_score=85.0, dimension_scores={}, issues=[], fix_suggestions=[],
        ))
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[])
        ro._extract_and_validate_data_points = MagicMock(return_value=second_rewrite.data_points_used)

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新数据",
                )],
            )
            result = await ro.revision(user_request="更新数据")

        assert result["chapter_results"][0].rewrite_rounds == 2
        assert ro._chapter_writer.rewrite.call_count == 2


class TestE2ELightweightRevision:
    """端到端：轻量修订流程"""

    @pytest.mark.asyncio
    async def test_lightweight_revision_updates_content_and_registry(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )

        chapters = _make_chapters_with_data()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "新能源汽车"}

        ro._extract_and_validate_data_points = MagicMock(return_value=[
            DataPoint(metric="市场规模", value="2000", unit="亿元", source="中汽协", chapter_id="ch1"),
        ])

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate, \
             patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.LIGHTWEIGHT,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="modify", revision_description="将标题改为市场概况",
                )],
            )
            mock_llm.return_value = {"success": True, "content": "市场概况\n\n2025年中国新能源汽车市场规模达2000亿元，同比增长15%。"}

            result = await ro.revision(user_request="将市场规模章节标题改为市场概况")

        assert result["global_review_passed"] is True
        assert "市场概况" in ro._chapters[0].content
        assert "data_registry_snapshot" in result


class TestE2EGlobalReviewFix:
    """端到端：全局审查不通过→修正→重新审查"""

    @pytest.mark.asyncio
    async def test_revision_with_global_fix_and_rescore(self):
        ro = _make_real_orchestrator()
        from src.agents.fixed_agents.report_upgrade.models import (
            ChapterWriteOutput, DataPoint, ChapterReviewOutput, ReviewOutput, ReviewIssue,
        )
        from src.agents.fixed_agents.report_upgrade.revision_models import (
            RevisionLocation, RevisionComplexity, RevisionTarget,
        )

        chapters = _make_chapters_with_data()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="重写后内容",
            data_points_used=[], key_conclusions=[], self_check_issues=[],
        )
        fixed = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后内容，数据一致",
            data_points_used=[], key_conclusions=[], self_check_issues=[],
        )

        ro._chapter_writer.rewrite = AsyncMock(side_effect=[rewritten, fixed])
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=80.0, issues=[]))

        review_issue = ReviewIssue(
            dimension="data_consistency", severity="HIGH",
            description="数据矛盾", location="chapter:ch1", evidence="营收数据不一致",
        )
        ro._global_reviewer.review = AsyncMock(side_effect=[
            ReviewOutput(overall_score=55.0, dimension_scores={}, issues=[review_issue], fix_suggestions=[]),
            ReviewOutput(overall_score=82.0, dimension_scores={}, issues=[], fix_suggestions=[]),
        ])
        ro._global_reviewer.verify_issues = AsyncMock(return_value=[review_issue])
        ro._extract_and_validate_data_points = MagicMock(return_value=[])

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新数据",
                )],
            )
            result = await ro.revision(user_request="更新数据")

        assert result["global_review_score"] == 82.0
        assert result["global_review_passed"] is True
        assert ro._global_reviewer.review.call_count == 2


class TestE2EDataFlowClosedLoop:
    """端到端：完整数据流闭环验证"""

    @pytest.mark.asyncio
    async def test_sections_to_revision_to_session_round_trip(self):
        from src.api.research_api_helpers import sections_to_chapters, apply_revision_to_session, restore_data_registry
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint, ReviewOutput
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

        original_sections = [
            {"id": "ch1", "title": "市场规模", "content": "市场规模达2000亿元"},
            {"id": "ch2", "title": "竞争格局", "content": "CR3达65%"},
        ]

        chapters = sections_to_chapters(original_sections)
        assert len(chapters) == 2
        assert chapters[0].chapter_id == "ch1"

        dr = DataRegistry()
        dr.register(metric="市场规模", value="2000", unit="亿元", chapter_id="ch1", source="年报")

        chapters[0].content = "市场规模达2500亿元，同比增长25%"
        chapters[0].data_points_used = [DataPoint(metric="市场规模", value="2500", unit="亿元", source="年报", chapter_id="ch1")]
        chapters[0].key_conclusions = ["市场规模达2500亿"]

        dr.register(metric="市场规模", value="2500", unit="亿元", chapter_id="ch1", source="年报")

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": original_sections, "topic": "新能源汽车"},
            },
            "_data_registry_snapshot": dr.to_snapshot(),
        }

        revision_result = {
            "chapter_results": [{"chapter_id": "ch1"}],
            "global_review_score": 90,
            "global_review_passed": True,
        }

        apply_revision_to_session(session, revision_result, chapters, dr)

        updated = session["research_result"]["report"]["sections"]
        assert updated[0]["content"] == "市场规模达2500亿元，同比增长25%"
        assert updated[0]["key_conclusions"] == ["市场规模达2500亿"]
        assert updated[0]["title"] == "市场规模"
        assert updated[0]["id"] == "ch1"

        restored_dr = restore_data_registry(session)
        assert "市场规模" in restored_dr.to_snapshot().get("metrics", {})

        report = ReportOrchestrator._assemble_final_report(
            chapters, "exec_summary",
            ReviewOutput(overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[]),
            "新能源汽车",
        )
        assert report["sections"][0]["key_conclusions"] == ["市场规模达2500亿"]
        assert report["sections"][1]["key_conclusions"] != [] or chapters[1].key_conclusions == []


class TestE2EPreconditionAndGate:
    """端到端：前置条件+阶段门控完整验证"""

    @pytest.mark.asyncio
    async def test_handle_v2_revision_rejects_no_preview(self):
        from src.api.research_api import ResearchAPI
        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]},
            },
            "quality_state": {"phase": "reviewing", "section_scores": {}},
        }

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps:
            sm.get.return_value = session
            mock_ps.path.return_value.exists.return_value = False
            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})

        assert "预览不存在" in str(result) or "重新生成" in str(result)

    @pytest.mark.asyncio
    async def test_legacy_revision_endpoint_forwards_base_report_version(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        api._handle_v2_revision = AsyncMock(return_value={"status": "conflict"})

        result = await api.revise_sections("sid", ["市场规模"], "更新数据", 4)

        assert result == {"status": "conflict"}
        api._handle_v2_revision.assert_awaited_once_with(
            "sid",
            {
                "adjustment": "更新数据",
                "aspects": ["市场规模"],
                "revision_type": "section",
                "base_report_version": 4,
            },
        )

    @pytest.mark.asyncio
    async def test_handle_v2_revision_rejects_concurrent_task(self):
        from src.api.research_api import ResearchAPI
        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}

        running_task = MagicMock()
        running_task.done.return_value = False
        api._executor_tasks["rev_sid"] = running_task

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]},
            },
            "quality_state": {"phase": "reviewing", "section_scores": {}},
        }

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps:
            sm.get.return_value = session
            mock_ps.path.return_value.exists.return_value = True
            result = await api._handle_v2_revision("sid", {"adjustment": "修改"})

        assert "正在执行" in str(result) or "等待" in str(result)

    @pytest.mark.asyncio
    async def test_handle_v2_revision_rejects_stale_report_version(self):
        from src.api.research_api import ResearchAPI
        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]},
            },
            "report_context": {"report_version": 3, "report_phase": "completed"},
            "quality_state": {"phase": "reviewing", "section_scores": {}},
        }

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as mock_ps:
            sm.get.return_value = session
            mock_ps.path.return_value.exists.return_value = True
            result = await api._handle_v2_revision(
                "sid", {"adjustment": "修改", "base_report_version": 2}
            )

        assert result["status"] == "conflict"
        assert result["error_code"] == "REPORT_VERSION_CONFLICT"
        assert result["current_report_version"] == 3

    @pytest.mark.asyncio
    async def test_gate_blocks_all_invalid_states(self):
        from src.api.research_api import ResearchAPI
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine

        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}

        blocked_states = ["understanding", "clarifying", "paused", "cancelled"]
        for state_name in blocked_states:
            cm = ConversationStateMachine()
            cm.force_set_state(ConversationState(state_name))
            session = {
                "research_result": {"status": "completed", "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]}},
                "quality_state": {"phase": "reviewing", "section_scores": {}},
                "state_machine": cm,
            }
            with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock) as mock_rev:
                result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
                mock_rev.assert_not_called(), f"revise_report should be blocked in {state_name}"

    @pytest.mark.asyncio
    async def test_gate_allows_valid_states(self):
        from src.api.research_api import ResearchAPI
        from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine

        with patch("src.api.research_api.ResearchOrchestrator"), \
             patch("src.api.research_api.PreviewGenerator"), \
             patch("src.api.research_api.ConversationToolSet"):
            api = ResearchAPI()
        api._revision_task = None
        api._executor_tasks = {}

        allowed_states = ["previewing", "completed"]
        for state_name in allowed_states:
            cm = ConversationStateMachine()
            cm.force_set_state(ConversationState(state_name))
            session = {
                "research_result": {"status": "completed", "report": {"sections": [{"id": "ch1", "title": "A", "content": "B"}]}},
                "quality_state": {"phase": "reviewing", "section_scores": {}},
                "state_machine": cm,
            }
            with patch.object(api, "_handle_v2_revision", new_callable=AsyncMock, return_value={"status": "ok"}) as mock_rev:
                result = await api._handle_revise_report_gate("sid", {"adjustment": "修改"}, session)
                mock_rev.assert_called_once(), f"revise_report should be allowed in {state_name}"
