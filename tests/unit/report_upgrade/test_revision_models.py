import pytest
from dataclasses import asdict

from src.agents.fixed_agents.report_upgrade.revision_models import (
    RevisionComplexity,
    RevisionTarget,
    RevisionLocation,
    ChapterRewriteResult,
)


class TestRevisionComplexity:
    def test_enum_values(self):
        assert RevisionComplexity.LIGHTWEIGHT.value == "lightweight"
        assert RevisionComplexity.STANDARD.value == "standard"
        assert RevisionComplexity.COMPLEX.value == "complex"
        assert RevisionComplexity.FULL.value == "full"

    def test_all_four_values(self):
        assert len(RevisionComplexity) == 4


class TestRevisionTarget:
    def test_create_with_required_fields(self):
        t = RevisionTarget(
            chapter_id="ch1",
            chapter_title="市场规模",
            revision_type="rewrite",
            revision_description="修改市场规模数据",
        )
        assert t.chapter_id == "ch1"
        assert t.chapter_title == "市场规模"
        assert t.revision_type == "rewrite"
        assert t.revision_description == "修改市场规模数据"
        assert t.data_patches == []

    def test_create_with_data_patches(self):
        t = RevisionTarget(
            chapter_id="ch2",
            chapter_title="竞争格局",
            revision_type="patch_data",
            revision_description="修正竞争格局数据",
            data_patches=["将市占率从30%改为35%", "更新CR3指标"],
        )
        assert len(t.data_patches) == 2
        assert "将市占率从30%改为35%" in t.data_patches


class TestRevisionLocation:
    def test_default_complexity_is_standard(self):
        loc = RevisionLocation()
        assert loc.complexity == RevisionComplexity.STANDARD
        assert loc.targets == []
        assert loc.data_gaps == []
        assert loc.data_conflicts == []
        assert loc.preceding_summary == ""

    def test_create_with_targets(self):
        loc = RevisionLocation(
            complexity=RevisionComplexity.COMPLEX,
            targets=[
                RevisionTarget(chapter_id="ch1", chapter_title="A", revision_type="rewrite", revision_description="修改A"),
                RevisionTarget(chapter_id="ch2", chapter_title="B", revision_type="rewrite", revision_description="修改B"),
            ],
            data_gaps=[{"chapter_id": "ch1", "metric": "营收", "context": "缺失"}],
            preceding_summary="前文结论摘要",
        )
        assert loc.complexity == RevisionComplexity.COMPLEX
        assert len(loc.targets) == 2
        assert len(loc.data_gaps) == 1
        assert loc.preceding_summary == "前文结论摘要"

    def test_lightweight_location(self):
        loc = RevisionLocation(
            complexity=RevisionComplexity.LIGHTWEIGHT,
            targets=[RevisionTarget(chapter_id="ch1", chapter_title="A", revision_type="modify", revision_description="改标题")],
        )
        assert loc.complexity == RevisionComplexity.LIGHTWEIGHT


class TestChapterRewriteResult:
    def test_create_basic(self):
        r = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧内容",
            revised_content="新内容",
            review_passed=True,
            review_score=85.0,
        )
        assert r.chapter_id == "ch1"
        assert r.original_content == "旧内容"
        assert r.revised_content == "新内容"
        assert r.review_passed is True
        assert r.review_score == 85.0
        assert r.data_points_changed == []
        assert r.data_points_added == []
        assert r.data_points_removed == []
        assert r.rewrite_rounds == 1

    def test_create_with_data_changes(self):
        r = ChapterRewriteResult(
            chapter_id="ch1",
            original_content="旧",
            revised_content="新",
            review_passed=True,
            review_score=90.0,
            data_points_added=[{"metric": "营收", "value": "500亿"}],
            rewrite_rounds=2,
        )
        assert len(r.data_points_added) == 1
        assert r.rewrite_rounds == 2

    def test_failed_rewrite(self):
        r = ChapterRewriteResult(
            chapter_id="ch_missing",
            original_content="",
            revised_content="",
            review_passed=False,
            review_score=0.0,
        )
        assert r.review_passed is False
        assert r.review_score == 0.0
