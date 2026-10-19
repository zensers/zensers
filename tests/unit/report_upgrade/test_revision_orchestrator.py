import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.fixed_agents.report_upgrade.revision_models import (
    RevisionComplexity,
    RevisionTarget,
    RevisionLocation,
    ChapterRewriteResult,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput, ChapterReviewOutput, ChapterIssue, ChapterReviewInput,
    DataPoint, ReviewInput, ReviewOutput, ReviewIssue,
)


def _make_minimal_orchestrator():
    from unittest.mock import AsyncMock
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    import tempfile
    from pathlib import Path

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


class TestParseLocationResult:
    def test_parse_valid_json(self):
        ro = _make_minimal_orchestrator()
        raw = '''```json
{
    "complexity": "standard",
    "targets": [
        {
            "chapter_id": "ch1",
            "chapter_title": "市场规模",
            "revision_type": "rewrite",
            "revision_description": "修改市场规模数据",
            "data_patches": ["将2000亿改为2500亿"]
        }
    ],
    "preceding_summary": "市场持续增长",
    "data_gaps": [{"chapter_id": "ch1", "metric": "CR3", "context": "缺失"}],
    "data_conflicts": []
}
```'''
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity == RevisionComplexity.STANDARD
        assert len(result.targets) == 1
        assert result.targets[0].chapter_id == "ch1"
        assert result.targets[0].chapter_title == "市场规模"
        assert result.targets[0].revision_type == "rewrite"
        assert result.targets[0].revision_description == "修改市场规模数据"
        assert len(result.targets[0].data_patches) == 1
        assert len(result.data_gaps) == 1
        assert result.preceding_summary == "市场持续增长"

    def test_parse_lightweight(self):
        ro = _make_minimal_orchestrator()
        raw = '''```json
{
    "complexity": "lightweight",
    "targets": [
        {
            "chapter_id": "ch1",
            "chapter_title": "A",
            "revision_type": "modify",
            "revision_description": "改标题",
            "data_patches": []
        }
    ],
    "preceding_summary": "",
    "data_gaps": [],
    "data_conflicts": []
}
```'''
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity == RevisionComplexity.LIGHTWEIGHT

    def test_parse_complex_with_multiple_targets(self):
        ro = _make_minimal_orchestrator()
        raw = '''```json
{
    "complexity": "complex",
    "targets": [
        {"chapter_id": "ch1", "chapter_title": "A", "revision_type": "rewrite", "revision_description": "改A", "data_patches": []},
        {"chapter_id": "ch2", "chapter_title": "B", "revision_type": "rewrite", "revision_description": "改B", "data_patches": []}
    ],
    "preceding_summary": "",
    "data_gaps": [],
    "data_conflicts": []
}
```'''
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity == RevisionComplexity.COMPLEX
        assert len(result.targets) == 2

    def test_parse_invalid_json_returns_fallback(self):
        ro = _make_minimal_orchestrator()
        raw = "this is not json at all"
        result = ro._parse_location_result(raw, "用户要求修改市场数据")
        assert result.complexity == RevisionComplexity.STANDARD
        assert len(result.targets) == 1
        assert result.targets[0].revision_description == "用户要求修改市场数据"
        assert result.targets[0].chapter_id == ""

    def test_parse_json_without_code_block_returns_fallback(self):
        ro = _make_minimal_orchestrator()
        raw = '{"complexity": "standard", "targets": []}'
        result = ro._parse_location_result(raw, "fallback")
        assert result.complexity == RevisionComplexity.STANDARD
        assert len(result.targets) == 1

    def test_parse_partial_json_uses_defaults(self):
        ro = _make_minimal_orchestrator()
        raw = '''```json
{
    "complexity": "standard",
    "targets": [
        {"chapter_id": "ch1"}
    ]
}
```'''
        result = ro._parse_location_result(raw, "fallback_desc")
        assert len(result.targets) == 1
        assert result.targets[0].chapter_id == "ch1"
        assert result.targets[0].revision_description == "fallback_desc"

    def test_parse_empty_targets_returns_fallback(self):
        ro = _make_minimal_orchestrator()
        raw = '''```json
{
    "complexity": "standard",
    "targets": [],
    "preceding_summary": "",
    "data_gaps": [],
    "data_conflicts": []
}
```'''
        result = ro._parse_location_result(raw, "用户要求")
        assert len(result.targets) == 0


class TestAppendRevisionPrecedingSummary:
    def test_empty_current_with_revised_content(self):
        ro = _make_minimal_orchestrator()
        result = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧",
            revised_content="市场规模达2000亿元，同比增长15%",
            review_passed=True,
            review_score=85.0,
        )
        summary = ro._append_revision_preceding_summary("", result)
        assert "市场规模达2000亿元" in summary

    def test_appends_to_existing_summary(self):
        ro = _make_minimal_orchestrator()
        result = ChapterRewriteResult(
            chapter_id="ch2",
            original_content="旧",
            revised_content="竞争格局CR3达65%",
            review_passed=True,
            review_score=80.0,
        )
        current = "前文：行业处于快速成长期"
        summary = ro._append_revision_preceding_summary(current, result)
        assert "前文" in summary
        assert "竞争格局" in summary

    def test_empty_revised_content_preserves_current(self):
        ro = _make_minimal_orchestrator()
        result = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧",
            revised_content="",
            review_passed=False,
            review_score=0.0,
        )
        current = "前文结论"
        summary = ro._append_revision_preceding_summary(current, result)
        assert summary == "前文结论"

    def test_truncates_long_summary_to_max_length(self):
        ro = _make_minimal_orchestrator()
        ro._MAX_PRECEDING_SUMMARY_LENGTH = 100
        long_current = "A" * 200
        result = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧",
            revised_content="新增内容" + "B" * 50,
            review_passed=True,
            review_score=85.0,
        )
        summary = ro._append_revision_preceding_summary(long_current, result)
        assert len(summary) <= 100


def _make_chapter(chapter_id="ch1", title="市场规模", content="市场规模达2000亿元"):
    return ChapterWriteOutput(
        chapter_id=chapter_id, title=title, content=content,
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="test")],
        key_conclusions=["市场规模达2000亿"],
    )


class TestExecuteChapterRevision:
    @pytest.mark.asyncio
    async def test_chapter_not_found_returns_failed_result(self):
        ro = _make_minimal_orchestrator()
        ro._chapters = [_make_chapter("ch1")]
        target = RevisionTarget(
            chapter_id="nonexistent", chapter_title="不存在",
            revision_type="rewrite", revision_description="修改",
        )
        result = await ro._execute_chapter_revision(target, "")
        assert result.chapter_id == "nonexistent"
        assert result.review_passed is False
        assert result.review_score == 0.0

    @pytest.mark.asyncio
    async def test_rewrite_passes_on_first_review(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模",
            content="市场规模达2500亿元，同比增长25%",
            data_points_used=[DataPoint(metric="市场规模", value="2500", unit="亿元", source="test")],
            key_conclusions=["市场规模达2500亿"],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten_ch)
        ro._chapter_reviewer.review = AsyncMock(return_value=ChapterReviewOutput(passed=True, score=85.0, issues=[]))

        target = RevisionTarget(
            chapter_id="ch1", chapter_title="市场规模",
            revision_type="rewrite", revision_description="更新市场规模数据",
        )
        result = await ro._execute_chapter_revision(target, "")
        assert result.review_passed is True
        assert result.review_score == 85.0
        assert "2500" in result.revised_content
        assert ro._chapters[0].content == rewritten_ch.content

    @pytest.mark.asyncio
    async def test_rewrite_retries_on_review_failure(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        rewritten_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2500亿元",
            data_points_used=[], key_conclusions=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten_ch)

        review_fail = ChapterReviewOutput(
            passed=False, score=40.0,
            issues=[ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="缺数据", suggestion="补充")],
        )
        review_pass = ChapterReviewOutput(passed=True, score=80.0, issues=[])
        ro._chapter_reviewer.review = AsyncMock(side_effect=[review_fail, review_pass])

        target = RevisionTarget(
            chapter_id="ch1", chapter_title="市场规模",
            revision_type="rewrite", revision_description="更新数据",
        )
        result = await ro._execute_chapter_revision(target, "")
        assert result.rewrite_rounds == 2
        assert ro._chapter_writer.rewrite.call_count == 2


class TestFixGlobalIssues:
    @pytest.mark.asyncio
    async def test_converts_review_issue_to_chapter_issue(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后内容",
            data_points_used=[], key_conclusions=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)

        issues = [ReviewIssue(
            dimension="data_consistency", severity="HIGH",
            description="数据矛盾", location="chapter:ch1",
            evidence="营收数据不一致",
        )]
        fix_suggestions = []

        await ro._fix_global_issues(issues, fix_suggestions)
        assert ro._chapter_writer.rewrite.call_count == 1
        call_args = ro._chapter_writer.rewrite.call_args
        feedback = call_args.kwargs.get("review_feedback") or call_args[1].get("review_feedback")
        assert feedback is not None
        assert len(feedback.issues) == 1
        assert feedback.issues[0].category == "data_consistency"
        assert feedback.issues[0].suggestion == "营收数据不一致"

    @pytest.mark.asyncio
    async def test_skips_chapter_not_found(self):
        ro = _make_minimal_orchestrator()
        ro._chapters = [_make_chapter("ch1")]
        ro._framework_config = {"name": "测试"}

        issues = [ReviewIssue(
            dimension="logic", severity="MEDIUM",
            description="逻辑问题", location="chapter:ch99",
            evidence="证据",
        )]
        await ro._fix_global_issues(issues, [])
        assert ro._chapter_writer.rewrite.call_count == 0

    @pytest.mark.asyncio
    async def test_limits_to_five_issues(self):
        ro = _make_minimal_orchestrator()
        for i in range(8):
            ro._chapters.append(_make_chapter(f"ch{i}", title=f"章节{i}"))
        ro._framework_config = {"name": "测试"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch0", title="A", content="修正",
            data_points_used=[], key_conclusions=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)

        issues = [ReviewIssue(
            dimension="data", severity="HIGH",
            description=f"问题{i}", location=f"chapter:ch{i}",
            evidence=f"证据{i}",
        ) for i in range(8)]

        await ro._fix_global_issues(issues, [])
        assert ro._chapter_writer.rewrite.call_count <= 5

    @pytest.mark.asyncio
    async def test_updates_chapters_on_fix(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1", content="旧内容")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}

        rewritten = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="修正后内容",
            data_points_used=[], key_conclusions=[],
        )
        ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten)

        issues = [ReviewIssue(
            dimension="data", severity="HIGH",
            description="问题", location="chapter:ch1",
            evidence="证据",
        )]
        await ro._fix_global_issues(issues, [])
        assert ro._chapters[0].content == "修正后内容"


class TestApplyLightweightRevision:
    @pytest.mark.asyncio
    async def test_lightweight_modifies_content(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1", content="原标题：市场规模分析")
        ro._chapters = [ch1]

        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(
                chapter_id="ch1", chapter_title="市场规模",
                revision_type="modify", revision_description="将标题改为竞争格局",
            )],
        )

        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm",
                    new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": "原标题：竞争格局分析"}
            result = await ro._apply_lightweight_revision(location)

        assert result["global_review_passed"] is True
        assert "data_registry_snapshot" in result
        assert ro._chapters[0].content == "原标题：竞争格局分析"

    @pytest.mark.asyncio
    async def test_lightweight_skips_nonexistent_chapter(self):
        ro = _make_minimal_orchestrator()
        ro._chapters = [_make_chapter("ch1")]

        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(
                chapter_id="ch99", chapter_title="不存在",
                revision_type="modify", revision_description="修改",
            )],
        )

        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm",
                    new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": "新内容"}
            result = await ro._apply_lightweight_revision(location)

        assert mock_llm.call_count == 0
        assert result["global_review_passed"] is True

    @pytest.mark.asyncio
    async def test_lightweight_handles_llm_failure(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1", content="原始内容")
        ro._chapters = [ch1]

        location = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(
                chapter_id="ch1", chapter_title="A",
                revision_type="modify", revision_description="修改",
            )],
        )

        with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm",
                    new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": False}
            result = await ro._apply_lightweight_revision(location)

        assert ro._chapters[0].content == "原始内容"


class TestRevisionIntegration:
    @pytest.mark.asyncio
    async def test_lightweight_revision_path(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1", content="原始内容")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.LIGHTWEIGHT,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="modify", revision_description="修改标题",
                )],
            )
            with patch("src.agents.fixed_agents.report_upgrade.orchestrator.call_llm",
                        new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = {"success": True, "content": "修改后内容"}
                result = await ro.revision(user_request="修改标题")

        assert result["global_review_passed"] is True
        assert ro._chapters[0].content == "修改后内容"

    @pytest.mark.asyncio
    async def test_standard_revision_with_global_review_pass(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新数据",
                )],
            )

            rewritten_ch = ChapterWriteOutput(
                chapter_id="ch1", title="市场规模", content="市场规模达2500亿元",
                data_points_used=[DataPoint(metric="市场规模", value="2500", unit="亿元", source="test")],
                key_conclusions=["市场规模达2500亿"],
            )
            ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten_ch)
            ro._chapter_reviewer.review = AsyncMock(
                return_value=ChapterReviewOutput(passed=True, score=85.0, issues=[])
            )
            ro._global_reviewer.review = AsyncMock(
                return_value=ReviewOutput(overall_score=90.0, dimension_scores={}, issues=[], fix_suggestions=[])
            )
            ro._global_reviewer.verify_issues = AsyncMock(return_value=[])

            result = await ro.revision(user_request="更新市场规模数据")

        assert result["global_review_score"] == 90.0
        assert result["global_review_passed"] is True
        assert len(result["chapter_results"]) == 1
        assert result["chapter_results"][0].review_passed is True

    @pytest.mark.asyncio
    async def test_standard_revision_with_global_review_fail_triggers_fix(self):
        ro = _make_minimal_orchestrator()
        ch1 = _make_chapter("ch1")
        ro._chapters = [ch1]
        ro._framework_config = {"name": "测试"}
        ro._task_structure = {"topic": "新能源汽车"}

        with patch.object(ro, "_locate_revision_target", new_callable=AsyncMock) as mock_locate:
            mock_locate.return_value = RevisionLocation(
                complexity=RevisionComplexity.STANDARD,
                targets=[RevisionTarget(
                    chapter_id="ch1", chapter_title="市场规模",
                    revision_type="rewrite", revision_description="更新数据",
                )],
            )

            rewritten_ch = ChapterWriteOutput(
                chapter_id="ch1", title="市场规模", content="市场规模达2500亿元",
                data_points_used=[], key_conclusions=[],
            )
            ro._chapter_writer.rewrite = AsyncMock(return_value=rewritten_ch)
            ro._chapter_reviewer.review = AsyncMock(
                return_value=ChapterReviewOutput(passed=True, score=80.0, issues=[])
            )

            review_issue = ReviewIssue(
                dimension="data_consistency", severity="HIGH",
                description="数据矛盾", location="chapter:ch1", evidence="证据",
            )
            ro._global_reviewer.review = AsyncMock(
                side_effect=[
                    ReviewOutput(overall_score=60.0, dimension_scores={}, issues=[review_issue], fix_suggestions=[]),
                    ReviewOutput(overall_score=75.0, dimension_scores={}, issues=[], fix_suggestions=[]),
                ]
            )
            ro._global_reviewer.verify_issues = AsyncMock(return_value=[review_issue])

            result = await ro.revision(user_request="更新市场规模数据")

        assert result["global_review_score"] == 75.0
        assert ro._chapter_writer.rewrite.call_count >= 2
