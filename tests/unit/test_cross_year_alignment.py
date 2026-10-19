"""Test: P1-1 跨年度数据对齐 — CAGR/YoY计算 + 年份提取
"""
import pytest
from src.skills.analysis.annual_report_parser import AnnualReportParserSkill


@pytest.fixture
def skill():
    return AnnualReportParserSkill()


class TestExtractYear:
    def test_year_from_filename(self, skill):
        assert skill._extract_year("2023_annual_report.pdf", []) == 2023

    def test_year_from_filename_chinese(self, skill):
        assert skill._extract_year("贵州茅台2024年年度报告.pdf", []) == 2024

    def test_year_from_text(self, skill):
        text = ["某某公司 2023 年度报告", "第一节 释义"]
        assert skill._extract_year("report.pdf", text) == 2023

    def test_year_from_text_english(self, skill):
        text = ["Apple Inc. 2023 Annual Report", "Form 10-K"]
        assert skill._extract_year("report.pdf", text) == 2023

    def test_year_not_found(self, skill):
        assert skill._extract_year("report.pdf", ["No year here"]) is None

    def test_year_multiple_matches_picks_most_common(self, skill):
        text = ["In 2021 revenue was 100. In 2022 revenue was 200. In 2022 profit was 50."]
        result = skill._extract_year("report.pdf", text)
        assert result == 2022


class TestAlignCrossYear:
    def test_cagr_calculation(self, skill):
        reports = [
            {
                "meta": {"year": 2021},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2021": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
            {
                "meta": {"year": 2023},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": 144.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert "营业收入_cagr_2y" in result["cross_year_summary"]
        cagr = result["cross_year_summary"]["营业收入_cagr_2y"]
        assert abs(cagr - 20.0) < 0.1

    def test_yoy_calculation(self, skill):
        reports = [
            {
                "meta": {"year": 2022},
                "financial_tables": {
                    "income": [{"科目": "净利润", "2022": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
            {
                "meta": {"year": 2023},
                "financial_tables": {
                    "income": [{"科目": "净利润", "2023": 130.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert "净利润_yoy_2023" in result["cross_year_summary"]
        yoy = result["cross_year_summary"]["净利润_yoy_2023"]
        assert abs(yoy - 30.0) < 0.1

    def test_single_year_no_calculation(self, skill):
        reports = [
            {
                "meta": {"year": 2023},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert result["cross_year_summary"] == {}

    def test_missing_year_skipped(self, skill):
        reports = [
            {
                "meta": {},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert result["cross_year_summary"] == {}

    def test_zero_base_skipped(self, skill):
        reports = [
            {
                "meta": {"year": 2022},
                "financial_tables": {
                    "income": [{"科目": "利润", "2022": 0.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
            {
                "meta": {"year": 2023},
                "financial_tables": {
                    "income": [{"科目": "利润", "2023": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert "利润_cagr_1y" not in result["cross_year_summary"]

    def test_metrics_by_year_structure(self, skill):
        reports = [
            {
                "meta": {"year": 2022},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2022": 100.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
            {
                "meta": {"year": 2023},
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": 120.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
            },
        ]
        result = skill._align_cross_year(reports)
        assert "营业收入" in result["metrics_by_year"]
        assert result["metrics_by_year"]["营业收入"][2022] == 100.0
        assert result["metrics_by_year"]["营业收入"][2023] == 120.0


class TestMergeReportsCrossYear:
    def test_merge_multiple_reports_includes_cross_year(self, skill):
        reports = [
            {
                "meta": {"file_path": "a.pdf", "year": 2022},
                "sections": [{"title": "Financial"}],
                "financial_tables": {"income": [{"科目": "营业收入", "2022": 100.0}], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {"aspects": ["财务分析"]},
            },
            {
                "meta": {"file_path": "b.pdf", "year": 2023},
                "sections": [{"title": "Financial"}],
                "financial_tables": {"income": [{"科目": "营业收入", "2023": 120.0}], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {},
            },
        ]
        result = skill._merge_reports(reports)
        assert "cross_year" in result
        assert "营业收入_yoy_2023" in result["cross_year"]["cross_year_summary"]

    def test_single_report_no_cross_year(self, skill):
        report = {"meta": {"file_path": "a.pdf"}, "sections": [], "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []}, "analysis_framework": {}}
        result = skill._merge_reports([report])
        assert "cross_year" not in result
