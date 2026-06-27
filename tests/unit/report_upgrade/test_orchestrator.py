import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict
from pathlib import Path

from src.agents.fixed_agents.report_upgrade.orchestrator import (
    ReportOrchestrator, RetryPolicy, DATAPOINT_FIELDS, _is_vague_source,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput, ChapterReviewOutput, ChapterIssue,
    ReviewOutput, ReviewIssue, FixSuggestion,
    DataPoint, DataConflict, DataConflictResolution,
    DataGap, DataRepairResult,
)
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


def make_chapter(chapter_id="ch1", title="市场规模", content="市场规模达2000亿元"):
    return ChapterWriteOutput(
        chapter_id=chapter_id, title=title, content=content,
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")],
        key_conclusions=["市场规模达2000亿"],
    )


def make_review_pass(score=85.0):
    return ChapterReviewOutput(passed=True, score=score, issues=[])


def make_review_fail(score=40.0):
    return ChapterReviewOutput(
        passed=False, score=score,
        issues=[ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="无数据", suggestion="补充")],
    )


def make_global_review(score=75.0, issues=None):
    return ReviewOutput(
        overall_score=score,
        dimension_scores={"data_consistency": 70},
        issues=issues or [],
        fix_suggestions=[],
    )


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.execute.return_value = {"success": True, "content": "执行摘要内容"}
    return llm


@pytest.fixture
def mock_writer():
    return AsyncMock()


@pytest.fixture
def mock_reviewer():
    return AsyncMock()


@pytest.fixture
def mock_global_reviewer():
    return AsyncMock()


@pytest.fixture
def mock_data_repair():
    return AsyncMock()


@pytest.fixture
def mock_conflict_resolver():
    return AsyncMock()


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "exec_summary.tmpl").write_text("${topic} ${all_conclusions}", encoding="utf-8")
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def orchestrator(mock_llm, mock_writer, mock_reviewer, mock_global_reviewer,
                 mock_data_repair, mock_conflict_resolver, mock_prompts):
    return ReportOrchestrator(
        llm_skill=mock_llm,
        chapter_writer=mock_writer,
        chapter_reviewer=mock_reviewer,
        global_reviewer=mock_global_reviewer,
        data_repair_agent=mock_data_repair,
        conflict_resolver=mock_conflict_resolver,
        prompt_manager=mock_prompts,
    )


def make_task_structure(num_sections=2):
    sections = []
    for i in range(num_sections):
        sections.append({
            "section_id": f"ch{i+1}",
            "section_name": f"章节{i+1}",
            "section_role": "analysis",
            "content_dependency": [],
        })
    return {"topic": "新能源汽车", "sections": sections}


class MockAggregationResult:
    def __init__(self):
        self.layered_content = {}
        self.content_provenance = {}
        self.sources = [{"title": "测试来源", "url": "https://example.com", "type": "web"}]


class TestRetryPolicy:
    def test_get_delay(self):
        assert RetryPolicy.get_delay(0) == 1.0
        assert RetryPolicy.get_delay(1) == 2.0
        assert RetryPolicy.get_delay(2) == 4.0


class TestReportOrchestratorGenerateReport:
    @pytest.mark.asyncio
    async def test_single_chapter_pass_review(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer, mock_llm):
        mock_writer.write.return_value = make_chapter()
        mock_reviewer.review.return_value = make_review_pass()
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert result["topic"] == "新能源汽车"
        assert len(result["sections"]) == 1
        assert "sources" in result
        assert len(result["sources"]) == 1

    @pytest.mark.asyncio
    async def test_chapter_fails_review_then_rewrites(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_rewritten = make_chapter(content="重写后内容")
        mock_writer.write.return_value = ch1
        mock_writer.rewrite.return_value = ch1_rewritten
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="logic", severity="HIGH", location="p:1", description="逻辑问题", suggestion="补充推理")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert len(result["sections"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_chapters(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter("ch1", "市场规模")
        ch2 = make_chapter("ch2", "竞争格局", "竞争格局分析")
        mock_writer.write.side_effect = [ch1, ch2]
        mock_reviewer.review.return_value = make_review_pass()
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(2),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert len(result["sections"]) == 2


class TestReportOrchestratorExtractChapterData:
    def test_extract_from_provenance(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"data": "内容"}}}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data == {"data": "内容"}
        assert raw_summary == ""

    def test_extract_from_layered_content_fallback(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {}
        agg.layered_content = {"analysis": {"ch1_market": {"data": "市场规模"}}}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data == {"data": "市场规模"}

    def test_extract_returns_empty_when_not_found(self, orchestrator):
        agg = MockAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch99", [])
        assert chapter_data == {}
        assert raw_summary == ""


class TestReportOrchestratorExtractValidateDataPoints:
    def test_extracts_from_content_chinese_units(self, orchestrator):
        ch = ChapterWriteOutput(chapter_id="ch1", title="测试", content="市场规模达到2000亿元，增速15%")
        dps = orchestrator._extract_and_validate_data_points(ch)
        values = [dp.value for dp in dps]
        assert "2000" in values

    def test_extracts_from_content_english_units(self, orchestrator):
        ch = ChapterWriteOutput(chapter_id="ch1", title="测试", content="Revenue reached 5.2 billion USD")
        dps = orchestrator._extract_and_validate_data_points(ch)
        values = [dp.value for dp in dps]
        assert "5.2" in values

    def test_no_duplicate_extraction(self, orchestrator):
        dp = DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="市场规模达2000亿元",
            data_points_used=[dp],
        )
        dps = orchestrator._extract_and_validate_data_points(ch)
        metric_2000_count = sum(1 for d in dps if d.value == "2000" and d.unit == "亿元")
        assert metric_2000_count == 1


class TestReportOrchestratorPrecedingSummary:
    def test_append_and_truncate(self, orchestrator):
        orchestrator._MAX_PRECEDING_SUMMARY_LENGTH = 50
        ch1 = make_chapter()
        ch1.key_conclusions = ["A" * 30]
        result = orchestrator._append_preceding_summary("", ch1)
        assert len(result) <= 50

    def test_rebuild(self, orchestrator):
        chapters = [make_chapter(), make_chapter("ch2", "竞争格局")]
        summary = orchestrator._rebuild_preceding_summary(chapters)
        assert "市场规模" in summary
        assert "竞争格局" in summary


class TestReportOrchestratorAssembleFinalReport:
    def test_assemble_with_sources(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        sources = [{"title": "来源1", "url": "https://a.com"}]
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", sources)
        assert result["sources"] == sources

    def test_assemble_without_sources(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert result["sources"] == []

    def test_assemble_sections_have_data_points(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert len(result["sections"][0]["data_points"]) == 1


class TestReportOrchestratorCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_and_restore(self, orchestrator, tmp_path):
        with patch.object(orchestrator, '_checkpoint_chapter'):
            pass

        checkpoint_dir = tmp_path / "data" / "test_task" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        ch = make_chapter()
        chapter_data = {
            "chapter_id": ch.chapter_id,
            "title": ch.title,
            "content": ch.content,
            "data_points_used": [asdict(dp) for dp in ch.data_points_used],
            "key_conclusions": ch.key_conclusions,
            "self_check_passed": ch.self_check_passed,
            "self_check_issues": ch.self_check_issues,
            "data_registry_snapshot": DataRegistry().to_snapshot(),
            "timestamp": "2026-06-26T00:00:00",
        }
        (checkpoint_dir / "chapter_ch1.json").write_text(
            json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
        )

        with patch('src.agents.fixed_agents.report_upgrade.orchestrator.Path') as mock_path_cls:
            mock_path_cls.return_value = tmp_path / "data"
            restored = await orchestrator._restore_from_checkpoint("test_task")

        assert restored is not None
        chapters, snapshot = restored
        assert len(chapters) == 1
        assert chapters[0].chapter_id == "ch1"


class TestReportOrchestratorVerifyDownstreamConsistency:
    def test_warns_on_inconsistent_value(self, orchestrator, caplog):
        patched_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
        )
        other_ch = ChapterWriteOutput(
            chapter_id="ch2", title="概述", content="市场规模约1800亿元",
        )
        import logging
        with caplog.at_level(logging.WARNING):
            orchestrator._verify_downstream_consistency([patched_ch, other_ch], {"ch1"})
        assert len(caplog.records) == 1

    def test_no_warning_when_consistent(self, orchestrator, caplog):
        patched_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
        )
        other_ch = ChapterWriteOutput(
            chapter_id="ch2", title="概述", content="市场增速15%",
        )
        import logging
        with caplog.at_level(logging.WARNING):
            orchestrator._verify_downstream_consistency([patched_ch, other_ch], {"ch1"})
        assert len(caplog.records) == 0


class TestReportOrchestratorUnderstandFramework:
    def test_produces_narrative_context(self, orchestrator):
        ts = make_task_structure(2)
        fc = {"name": "行业研究"}
        result = orchestrator._understand_framework(ts, fc)
        assert "新能源汽车" in result
        assert "章节1" in result
        assert "章节2" in result


class TestReportOrchestratorExtractMetric:
    def test_extracts_from_brackets(self, orchestrator):
        assert orchestrator._extract_metric("「市场规模」数据缺失") == "市场规模"

    def test_fallback_to_prefix(self, orchestrator):
        result = orchestrator._extract_metric("数据缺失无引号")
        assert len(result) <= 20


class TestIsVagueSource:
    def test_empty_is_vague(self):
        assert _is_vague_source("") is True
        assert _is_vague_source("   ") is True

    def test_vague_patterns(self):
        assert _is_vague_source("行业综合数据") is True
        assert _is_vague_source("综合数据") is True
        assert _is_vague_source("公开数据") is True
        assert _is_vague_source("市场数据") is True
        assert _is_vague_source("研究报告") is True

    def test_specific_source_not_vague(self):
        assert _is_vague_source("iimedia.cn") is False
        assert _is_vague_source("中国汽车工业协会") is False
        assert _is_vague_source("乘联会") is False


class TestCleanKeyFindings:
    def test_strips_markdown(self, orchestrator):
        raw = "# 执行摘要\n\n**核心发现一：** 内容\n\n**核心发现二：** 内容2"
        result = orchestrator._clean_key_findings(raw)
        assert all(not line.startswith("#") for line in result)
        assert all("**" not in line for line in result)

    def test_removes_empty_lines(self, orchestrator):
        raw = "第一行\n\n第二行\n\n第三行"
        result = orchestrator._clean_key_findings(raw)
        assert "" not in result

    def test_max_10_lines(self, orchestrator):
        raw = "\n".join(f"第{i}行" for i in range(20))
        result = orchestrator._clean_key_findings(raw)
        assert len(result) <= 10


class TestGroundDataPointSources:
    def test_vague_source_replaced(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "行业综合数据"}]
        sources = [{"title": "中国汽车工业协会", "url": "https://caam.org.cn", "type": "web"}]
        result = orchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "中国汽车工业协会"

    def test_specific_source_kept(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "iimedia.cn"}]
        sources = [{"title": "中国汽车工业协会", "url": "https://caam.org.cn", "type": "web"}]
        result = orchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "iimedia.cn"

    def test_no_sources_available(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "行业综合数据"}]
        result = orchestrator._ground_data_point_sources(dps, [])
        assert result[0]["source"] == "行业综合数据"


class TestAssembleFinalReportP3P5:
    def test_chapter_sources_populated(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        sources = [{"title": "来源1", "url": "https://a.com", "type": "web"}]
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", sources)
        assert len(result["sections"][0]["sources"]) == 1
        assert result["sections"][0]["sources"][0]["title"] == "来源1"

    def test_chapter_sources_empty_when_no_original(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert result["sections"][0]["sources"] == []

    def test_key_findings_cleaned(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        raw_summary = "# 执行摘要\n\n**核心发现一：** 测试\n\n**核心发现二：** 测试2"
        result = orchestrator._assemble_final_report(chapters, raw_summary, review, "主题")
        assert all("**" not in f for f in result["key_findings"])
        assert all(not f.startswith("#") for f in result["key_findings"])

    def test_vague_data_point_source_grounded(self, orchestrator):
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="销量1200万辆",
            data_points_used=[DataPoint(metric="销量", value="1200", unit="万辆", source="行业综合数据")],
            key_conclusions=["销量1200万"],
        )
        sources = [{"title": "乘联会", "url": "https://cpcaauto.com", "type": "web"}]
        result = orchestrator._assemble_final_report([ch], "摘要", make_global_review(), "主题", sources)
        assert result["sections"][0]["data_points"][0]["source"] == "乘联会"


class TestAuditFixesB1toB8:
    def test_extract_raw_summary_body_is_dict(self, orchestrator):
        meta = {"data_points": [{"title": "测试", "content": {"key": "val"}}]}
        result = ReportOrchestrator._extract_raw_summary(meta)
        assert "key" in result

    def test_extract_raw_summary_body_is_list(self, orchestrator):
        meta = {"data_points": [{"title": "测试", "content": [1, 2, 3]}]}
        result = ReportOrchestrator._extract_raw_summary(meta)
        assert "1" in result

    def test_verify_downstream_consistency_float_value(self, orchestrator):
        patched = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="营收1502.25亿元",
            data_points_used=[DataPoint(metric="营收", value=1502.25, unit="亿元", source="财报")],
        )
        other = ChapterWriteOutput(
            chapter_id="ch2", title="其他", content="营收1502.25亿元",
        )
        ReportOrchestrator._verify_downstream_consistency([patched, other], {"ch1"})

    def test_assemble_final_report_sources_with_href(self, orchestrator):
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="测试",
            data_points_used=[DataPoint(metric="测试", value="1", unit="个", source="行业综合数据")],
        )
        sources = [{"title": "来源", "href": "https://a.com", "type": "web"}]
        result = orchestrator._assemble_final_report([ch], "摘要", make_global_review(), "主题", sources)
        assert result["sections"][0]["sources"][0]["url"] == "https://a.com"

    def test_ground_data_point_sources_with_href(self, orchestrator):
        dps = [{"metric": "测试", "value": "1", "unit": "个", "source": "行业综合数据"}]
        sources = [{"title": "来源", "href": "https://a.com"}]
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "来源"

    def test_extract_chapter_data_tracks_matched_key(self, orchestrator):
        agg = MagicMock()
        agg.layered_content = {"analysis": {
            "phase_2_agent_0": "精炼内容",
            "phase_2_agent_0__meta": {"data_points": [{"title": "测试", "content": "原始数据"}]},
        }}
        agg.content_provenance = {"phase_2_agent_0": MagicMock(section_target="核心财务指标")}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "核心财务指标", [])
        assert chapter_data == {"content": "精炼内容"}
        assert "测试" in raw_summary

    def test_split_chapter_data_str_with_meta(self, orchestrator):
        lc = {"analysis": {
            "agent_0": "内容文本",
            "agent_0__meta": {"data_points": [{"title": "DP1", "content": "数据"}]},
        }}
        refined, raw_summary = ReportOrchestrator._split_chapter_data("内容文本", "agent_0", lc)
        assert refined == {"content": "内容文本"}
        assert "DP1" in raw_summary


class TestBuildAnchorPatchInstructions:
    def test_fabricated_data_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="CRITICAL",
            location="p:2", description="编造数据：营收5000亿",
            suggestion="删除该数值",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "删除" in result[0]

    def test_vague_source_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="HIGH",
            location="p:3", description="模糊来源：据行业分析",
            suggestion="替换为具体来源",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "补充具体来源" in result[0]

    def test_data_gap_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="HIGH",
            location="p:4", description="未标注数据缺口",
            suggestion="标注数据缺口",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "标注数据缺口" in result[0]

    def test_multiple_issues(self, orchestrator):
        issues = [
            ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion=""),
            ChapterIssue(category="data_anchoring", severity="HIGH", location="p:2", description="模糊来源", suggestion=""),
        ]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 2

    def test_empty_issues(self, orchestrator):
        result = ReportOrchestrator._build_anchor_patch_instructions([], {})
        assert result == []


class TestReviewPatchSeparation:
    @pytest.mark.asyncio
    async def test_anchor_issues_trigger_patch_not_rewrite(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_patched = make_chapter(content="修补后内容")
        mock_writer.write.return_value = ch1
        mock_writer.patch_data.return_value = ch1_patched
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion="删除")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        mock_writer.patch_data.assert_called_once()
        mock_writer.rewrite.assert_not_called()

    @pytest.mark.asyncio
    async def test_logic_issues_trigger_rewrite(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_rewritten = make_chapter(content="重写后内容")
        mock_writer.write.return_value = ch1
        mock_writer.rewrite.return_value = ch1_rewritten
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="logic", severity="CRITICAL", location="p:1", description="逻辑跳跃", suggestion="补充推理")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        mock_writer.rewrite.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_score_drop_keeps_original(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_patched = make_chapter(content="修补后内容")
        mock_writer.write.return_value = ch1
        mock_writer.patch_data.return_value = ch1_patched
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=50,
                issues=[ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion="删除")],
            ),
            ChapterReviewOutput(passed=False, score=30, issues=[]),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert result["sections"][0]["content"] == "市场规模达2000亿元"


class TestBaseContentExtraction:
    def test_base_content_from_chapter_data(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"content": "分析Agent的专业输出"}}}
        chapter_data, _ = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data.get("content") == "分析Agent的专业输出"

    def test_base_content_from_string_data(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": "分析Agent的字符串输出"}}
        chapter_data, _ = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data.get("content") == "分析Agent的字符串输出"
