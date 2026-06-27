import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from src.agents.fixed_agents.report_upgrade.orchestrator import (
    ReportOrchestrator,
    RetryPolicy,
    _is_vague_source,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput,
    ChapterIssue,
    ChapterReviewOutput,
    DataPoint,
    QualityIssueDiagnosis,
    ChapterDiagnostic,
    QualityReport,
)


def _make_chapter(chapter_id="ch1", title="测试章节", content="测试内容", score=75.0):
    return ChapterWriteOutput(
        chapter_id=chapter_id,
        title=title,
        content=content,
        data_points_used=[],
        key_conclusions=["结论1"],
        self_check_passed=True,
    )


def _make_orchestrator():
    writer = AsyncMock()
    reviewer = AsyncMock()
    global_reviewer = AsyncMock()
    data_repair = AsyncMock()
    conflict_resolver = AsyncMock()
    llm = AsyncMock()
    orchestrator = ReportOrchestrator(
        llm_skill=llm,
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver,
    )
    orchestrator._task_structure = {"topic": "比亚迪", "sections": []}
    orchestrator._aggregated_result = MagicMock()
    return orchestrator


class TestDiagnoseIssueSource:
    def test_fabricated_data_in_content_not_in_raw(self):
        orch = _make_orchestrator()
        issue = ChapterIssue(
            category="data_anchoring",
            severity="CRITICAL",
            location="ch2",
            description="编造保险业务收入数据",
            suggestion="删除编造断言",
        )
        raw_summary = "- 营收: 6800亿\n- 研发费用: 542亿\n- 净利润: 280亿"
        diagnosis = orch._diagnose_issue_source(issue, raw_summary)
        assert diagnosis.source_layer == "L2_fabricated"

    def test_vague_source_issue(self):
        orch = _make_orchestrator()
        issue = ChapterIssue(
            category="data_anchoring",
            severity="HIGH",
            location="ch1",
            description="数据来源标注为综合数据，缺乏具体出处",
            suggestion="补充具体来源",
        )
        raw_summary = "- 营收: 6800亿 [来源: 比亚迪年报]"
        diagnosis = orch._diagnose_issue_source(issue, raw_summary)
        assert diagnosis.source_layer == "L2_vague_source"

    def test_data_gap_in_raw_summary(self):
        orch = _make_orchestrator()
        issue = ChapterIssue(
            category="data_anchoring",
            severity="HIGH",
            location="ch2",
            description="缺乏研发投入金额数据",
            suggestion="补充研发投入数据",
        )
        raw_summary = "- 研发费用: 542亿\n- 净利润: 280亿"
        diagnosis = orch._diagnose_issue_source(issue, raw_summary)
        assert diagnosis.source_layer == "L2_omitted"

    def test_data_gap_not_in_raw_summary(self):
        orch = _make_orchestrator()
        issue = ChapterIssue(
            category="data_anchoring",
            severity="HIGH",
            location="ch3",
            description="缺乏单车利润数据",
            suggestion="补充单车利润数据",
        )
        raw_summary = "- 营收: 6800亿"
        diagnosis = orch._diagnose_issue_source(issue, raw_summary)
        assert diagnosis.source_layer == "L1_missing"

    def test_logic_issue_is_L3(self):
        orch = _make_orchestrator()
        issue = ChapterIssue(
            category="logic",
            severity="HIGH",
            location="ch1",
            description="论点与论据逻辑不一致",
            suggestion="修正逻辑推理",
        )
        raw_summary = "- 营收: 6800亿"
        diagnosis = orch._diagnose_issue_source(issue, raw_summary)
        assert diagnosis.source_layer == "L3_report"


class TestExtractOmittedData:
    def test_exact_match_in_raw_summary(self):
        orch = _make_orchestrator()
        raw_summary = "- 研发费用: 542亿 (元) [来源: 比亚迪年报]\n- 净利润: 280亿"
        result = orch._extract_omitted_data("研发费用", raw_summary)
        assert result is not None
        assert "542" in result

    def test_no_match_returns_none(self):
        orch = _make_orchestrator()
        raw_summary = "- 营收: 6800亿"
        result = orch._extract_omitted_data("单车利润", raw_summary)
        assert result is None

    def test_partial_match(self):
        orch = _make_orchestrator()
        raw_summary = "- 研发投入: 542亿元 [来源: 年报]\n- 净利润: 280亿"
        result = orch._extract_omitted_data("研发投入金额", raw_summary)
        assert result is not None
        assert "542" in result


class TestBuildAnchorPatchInstructionsL2Omitted:
    def test_l2_omitted_with_raw_data(self):
        orch = _make_orchestrator()
        issues = [
            ChapterIssue(
                category="data_anchoring",
                severity="HIGH",
                location="ch2",
                description="缺乏研发投入金额数据",
                suggestion="补充研发投入数据",
            ),
        ]
        chapter_data = {"content": "比亚迪研发投入..."}
        raw_summary = "- 研发费用: 542亿 (元) [来源: 比亚迪年报]"
        instructions = orch._build_anchor_patch_instructions(
            issues, chapter_data, raw_data_summary=raw_summary,
        )
        assert any("补充已有数据" in inst for inst in instructions)

    def test_l1_missing_no_raw_data(self):
        orch = _make_orchestrator()
        issues = [
            ChapterIssue(
                category="data_anchoring",
                severity="HIGH",
                location="ch3",
                description="缺乏单车利润数据",
                suggestion="补充单车利润数据",
            ),
        ]
        chapter_data = {"content": "比亚迪单车利润..."}
        raw_summary = "- 营收: 6800亿"
        instructions = orch._build_anchor_patch_instructions(
            issues, chapter_data, raw_data_summary=raw_summary,
        )
        assert any("标注数据缺口" in inst for inst in instructions)

    def test_fabricated_data(self):
        orch = _make_orchestrator()
        issues = [
            ChapterIssue(
                category="data_anchoring",
                severity="CRITICAL",
                location="ch2",
                description="编造保险业务收入数据",
                suggestion="删除编造断言",
            ),
        ]
        raw_summary = "- 营收: 6800亿"
        instructions = orch._build_anchor_patch_instructions(
            issues, {}, raw_data_summary=raw_summary,
        )
        assert any("删除无据断言" in inst or "编造" in inst for inst in instructions)


class TestRetryPolicyConvergence:
    def test_max_convergence_rounds(self):
        assert RetryPolicy.MAX_CONVERGENCE_ROUNDS == 3

    def test_convergence_improvement_threshold(self):
        assert RetryPolicy.MIN_CONVERGENCE_IMPROVEMENT == 5

    def test_target_score(self):
        assert RetryPolicy.TARGET_SCORE == 80


class TestAssembleFinalReportWithQualityReport:
    def test_quality_report_included(self):
        chapters = [
            _make_chapter(chapter_id="ch1", title="章节1", content="内容1"),
        ]
        review_output = MagicMock()
        review_output.overall_score = 85.0

        quality_report = QualityReport(
            overall_score=85.0,
            convergence_rounds=2,
            converged=True,
            chapter_diagnostics=[
                ChapterDiagnostic(chapter_id="ch1", score=85.0, source_layer="L3_report"),
            ],
        )

        result = ReportOrchestrator._assemble_final_report(
            chapters, "执行摘要", review_output, "比亚迪",
            original_sources=[], quality_report=quality_report,
        )
        assert "quality_report" in result
        assert result["quality_report"]["overall_score"] == 85.0
        assert result["quality_report"]["converged"] is True
        assert len(result["quality_report"]["chapter_diagnostics"]) == 1

    def test_no_quality_report(self):
        chapters = [_make_chapter()]
        review_output = MagicMock()
        review_output.overall_score = 75.0
        result = ReportOrchestrator._assemble_final_report(
            chapters, "摘要", review_output, "测试",
            original_sources=[], quality_report=None,
        )
        assert "quality_report" not in result or result.get("quality_report") is None
