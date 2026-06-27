import pytest
from dataclasses import asdict

from src.agents.fixed_agents.report_upgrade.models import (
    DataPoint,
    MetricEntry,
    ChapterWriteInput,
    ChapterWriteOutput,
    ChapterReviewInput,
    ChapterIssue,
    ChapterReviewOutput,
    ReviewInput,
    ReviewIssue,
    FixSuggestion,
    ReviewOutput,
    DataGap,
    DataRepairResult,
    DataConflict,
    DataConflictResolution,
)


class TestDataPoint:
    def test_create_with_required_fields(self):
        dp = DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")
        assert dp.metric == "市场规模"
        assert dp.value == "2000"
        assert dp.unit == "亿元"
        assert dp.source == "iimedia.cn"
        assert dp.chapter_id == ""
        assert dp.confidence == 1.0

    def test_create_with_all_fields(self):
        dp = DataPoint(
            metric="市场规模", value="2000", unit="亿元",
            source="iimedia.cn", chapter_id="ch1", confidence=0.9,
        )
        assert dp.chapter_id == "ch1"
        assert dp.confidence == 0.9

    def test_asdict(self):
        dp = DataPoint(metric="增速", value="15", unit="%", source="gov.cn")
        d = asdict(dp)
        assert d == {
            "metric": "增速", "value": "15", "unit": "%",
            "source": "gov.cn", "chapter_id": "", "confidence": 1.0,
        }

    def test_from_dict_filters_extra_fields(self):
        raw = {"metric": "GDP", "value": "120", "unit": "万亿元", "source": "gov.cn", "year": 2025}
        DATAPOINT_FIELDS = {"metric", "value", "unit", "source", "chapter_id", "confidence"}
        dp = DataPoint(**{k: v for k, v in raw.items() if k in DATAPOINT_FIELDS})
        assert dp.metric == "GDP"
        assert not hasattr(dp, "year")


class TestMetricEntry:
    def test_create_with_no_conflicts(self):
        me = MetricEntry(
            metric="市场规模", value="2000", unit="亿元",
            canonical_chapter="ch1", source="iimedia.cn",
        )
        assert me.conflicts == []

    def test_create_with_conflicts(self):
        me = MetricEntry(
            metric="市场规模", value="2000", unit="亿元",
            canonical_chapter="ch1", source="iimedia.cn",
            conflicts=[{"chapter_id": "ch2", "value": "1800", "unit": "亿元", "source": "iresearch.cn"}],
        )
        assert len(me.conflicts) == 1


class TestChapterWriteInput:
    def test_create(self):
        inp = ChapterWriteInput(
            framework_config={"name": "行业研究"},
            task_structure={"topic": "新能源汽车"},
            chapter_spec={"section_id": "ch1", "section_name": "市场规模"},
            chapter_data={"市场规模": "2000亿"},
            preceding_summary="前文摘要",
            used_metrics_summary="已用指标",
        )
        assert inp.framework_config["name"] == "行业研究"
        assert inp.chapter_data["市场规模"] == "2000亿"


class TestChapterWriteOutput:
    def test_defaults(self):
        out = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="正文内容")
        assert out.data_points_used == []
        assert out.key_conclusions == []
        assert out.self_check_passed is True
        assert out.self_check_issues == []

    def test_with_data_points(self):
        dp = DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")
        out = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="正文",
            data_points_used=[dp], key_conclusions=["市场规模达2000亿"],
            self_check_passed=False, self_check_issues=["格式问题"],
        )
        assert len(out.data_points_used) == 1
        assert out.self_check_passed is False


class TestChapterReviewInput:
    def test_topic_default(self):
        inp = ChapterReviewInput(
            framework_config={},
            chapter_spec={},
            chapter_content="content",
            preceding_summary="",
            used_metrics_summary="",
        )
        assert inp.topic == ""

    def test_topic_set(self):
        inp = ChapterReviewInput(
            framework_config={},
            chapter_spec={},
            chapter_content="content",
            preceding_summary="",
            used_metrics_summary="",
            topic="新能源汽车市场分析",
        )
        assert inp.topic == "新能源汽车市场分析"


class TestChapterIssue:
    def test_create(self):
        iss = ChapterIssue(
            category="data_support", severity="HIGH",
            location="data:市场规模", description="无数据支撑",
            suggestion="补充市场规模数据",
        )
        assert iss.category == "data_support"
        assert iss.severity == "HIGH"


class TestChapterReviewOutput:
    def test_defaults(self):
        out = ChapterReviewOutput(passed=True, score=85.0)
        assert out.issues == []

    def test_with_issues(self):
        iss = ChapterIssue(
            category="logic", severity="MEDIUM",
            location="paragraph:3", description="逻辑跳跃",
            suggestion="补充过渡句",
        )
        out = ChapterReviewOutput(passed=False, score=45.0, issues=[iss])
        assert len(out.issues) == 1


class TestReviewInput:
    def test_create(self):
        inp = ReviewInput(
            framework_config={"name": "行业研究"},
            report_summary="报告摘要",
            conflicts_summary="数据冲突摘要",
        )
        assert inp.report_summary == "报告摘要"


class TestReviewIssue:
    def test_create(self):
        iss = ReviewIssue(
            dimension="data_consistency", severity="CRITICAL",
            description="跨章节数据矛盾",
            location="chapter_1, chapter_3",
            evidence="2000亿 vs 1800亿",
        )
        assert iss.dimension == "data_consistency"


class TestFixSuggestion:
    def test_create(self):
        fs = FixSuggestion(
            target_chapter="chapter_3",
            issue_id="issue_1",
            fix_type="patch",
            fix_instruction="统一为2000亿元",
            priority="CRITICAL",
        )
        assert fs.fix_type == "patch"


class TestReviewOutput:
    def test_defaults(self):
        out = ReviewOutput(overall_score=75.0)
        assert out.dimension_scores == {}
        assert out.issues == []
        assert out.fix_suggestions == []

    def test_with_all(self):
        iss = ReviewIssue(
            dimension="data_consistency", severity="CRITICAL",
            description="矛盾", location="ch1", evidence="ev",
        )
        fs = FixSuggestion(
            target_chapter="ch1", issue_id="i1",
            fix_type="rewrite", fix_instruction="重写", priority="HIGH",
        )
        out = ReviewOutput(
            overall_score=60.0,
            dimension_scores={"data_consistency": 40},
            issues=[iss], fix_suggestions=[fs],
        )
        assert len(out.issues) == 1
        assert len(out.fix_suggestions) == 1


class TestDataGap:
    def test_defaults(self):
        gap = DataGap(chapter_id="ch1", metric="市场规模", context="缺失市场规模数据")
        assert gap.search_keywords == []


class TestDataRepairResult:
    def test_not_found(self):
        gap = DataGap(chapter_id="ch1", metric="市场规模", context="缺失")
        r = DataRepairResult(gap=gap, found=False)
        assert r.value is None
        assert r.confidence == 0.0

    def test_found(self):
        gap = DataGap(chapter_id="ch1", metric="市场规模", context="缺失")
        r = DataRepairResult(
            gap=gap, found=True,
            value="2000", unit="亿元", source="iimedia.cn",
            source_title="2025年报告", confidence=0.85,
        )
        assert r.found is True
        assert r.confidence == 0.85


class TestDataConflict:
    def test_create(self):
        c = DataConflict(
            metric="市场规模",
            entries=[
                {"chapter_id": "ch1", "value": "2000", "unit": "亿元", "source": "A"},
                {"chapter_id": "ch2", "value": "1800", "unit": "亿元", "source": "B"},
            ],
        )
        assert len(c.entries) == 2


class TestDataConflictResolution:
    def test_create(self):
        conflict = DataConflict(metric="市场规模", entries=[])
        r = DataConflictResolution(
            conflict=conflict,
            canonical_value="2000",
            canonical_unit="亿元",
            canonical_source="iimedia.cn",
            reason="来源权威性更高",
            chapters_to_update=["ch2"],
        )
        assert r.canonical_value == "2000"
        assert len(r.chapters_to_update) == 1
