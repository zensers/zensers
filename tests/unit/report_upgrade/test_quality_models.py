import pytest
from src.agents.fixed_agents.report_upgrade.models import (
    QualityIssueDiagnosis,
    ChapterDiagnostic,
    QualityReport,
)


class TestQualityIssueDiagnosis:
    def test_create_with_required_fields(self):
        d = QualityIssueDiagnosis(
            issue_description="缺乏研发投入数据",
            source_layer="L2_omitted",
            remediation="补充已有数据: 542亿元",
        )
        assert d.issue_description == "缺乏研发投入数据"
        assert d.source_layer == "L2_omitted"
        assert d.remediation == "补充已有数据: 542亿元"
        assert d.resolved is False

    def test_create_with_resolved(self):
        d = QualityIssueDiagnosis(
            issue_description="编造数据",
            source_layer="L2_fabricated",
            remediation="删除编造断言",
            resolved=True,
        )
        assert d.resolved is True

    def test_source_layer_values(self):
        for layer in ["L1_missing", "L2_omitted", "L2_fabricated", "L2_vague_source", "L3_report"]:
            d = QualityIssueDiagnosis(
                issue_description="test",
                source_layer=layer,
                remediation="",
            )
            assert d.source_layer == layer


class TestChapterDiagnostic:
    def test_create_with_defaults(self):
        d = ChapterDiagnostic(
            chapter_id="ch1",
            score=75.0,
            source_layer="L3_report",
        )
        assert d.chapter_id == "ch1"
        assert d.score == 75.0
        assert d.source_layer == "L3_report"
        assert d.gaps == []
        assert d.repair_attempts == []
        assert d.remediations == []

    def test_create_with_all_fields(self):
        d = ChapterDiagnostic(
            chapter_id="ch2",
            score=45.0,
            source_layer="L2_omitted",
            gaps=["研发投入金额", "单车利润"],
            repair_attempts=[{"gap": "研发投入金额", "searched": True, "found": True, "source": "StockDataSkill"}],
            remediations=["已补充研发费用率"],
        )
        assert len(d.gaps) == 2
        assert d.repair_attempts[0]["source"] == "StockDataSkill"


class TestQualityReport:
    def test_create_with_defaults(self):
        r = QualityReport()
        assert r.overall_score == 0.0
        assert r.target_score == 80.0
        assert r.convergence_rounds == 0
        assert r.converged is False
        assert r.chapter_diagnostics == []

    def test_create_with_values(self):
        r = QualityReport(
            overall_score=82.0,
            convergence_rounds=2,
            converged=True,
            chapter_diagnostics=[
                ChapterDiagnostic(chapter_id="ch1", score=85.0, source_layer="L3_report"),
            ],
        )
        assert r.overall_score == 82.0
        assert r.converged is True
        assert len(r.chapter_diagnostics) == 1
