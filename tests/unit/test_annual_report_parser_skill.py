"""Test: AnnualReportParserSkill — PDF parsing + dynamic TOC + LLM framework

Tests the core logic without requiring actual PDF files or LLM calls.
Uses mocking for external dependencies (pdfplumber, PyPDF2, call_llm).
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.skills.analysis.annual_report_parser import (
    AnnualReportParserSkill,
    FINANCIAL_TABLE_KEYWORDS,
    TYPE_TO_PROFILE,
    TYPE_TO_ASPECT_NAME,
)


@pytest.fixture
def skill():
    return AnnualReportParserSkill()


class TestSkillProperties:
    def test_name(self, skill):
        assert skill.name == "annual_report_parser"

    def test_description_mentions_global(self, skill):
        assert "global" in skill.description.lower() or "10-K" in skill.description


class TestGuessSectionType:
    def test_overview(self, skill):
        assert skill._guess_section_type("公司概述") == "overview"
        assert skill._guess_section_type("Executive Summary") == "overview"

    def test_financial(self, skill):
        assert skill._guess_section_type("财务报表") == "financial"
        assert skill._guess_section_type("Financial Statements") == "financial"

    def test_risk(self, skill):
        assert skill._guess_section_type("风险因素") == "risk"
        assert skill._guess_section_type("Risk Factors") == "risk"

    def test_governance(self, skill):
        assert skill._guess_section_type("公司治理") == "governance"

    def test_other(self, skill):
        assert skill._guess_section_type("备查文件") == "other"


class TestGuessImportance:
    def test_high_importance(self, skill):
        assert skill._guess_importance("财务报表") == 5
        assert skill._guess_importance("Risk Factors") == 5

    def test_low_importance(self, skill):
        assert skill._guess_importance("目录") == 1
        assert skill._guess_importance("备查文件") == 1

    def test_medium_importance(self, skill):
        assert skill._guess_importance("公司概述") == 3


class TestNormalizeFinancialTable:
    def test_basic_normalization(self, skill):
        table = {
            "headers": ["科目", "2023年", "2024年"],
            "rows": [
                ["营业收入", "1,234.56", "1,400.20"],
                ["净利润", "234.56", "280.00"],
            ],
        }
        result = skill._normalize_financial_table(table)
        assert len(result) == 2
        assert result[0]["科目"] == "营业收入"
        assert result[0]["2023"] == 1234.56
        assert result[0]["2024"] == 1400.20

    def test_negative_values_parentheses(self, skill):
        table = {
            "headers": ["科目", "2023年"],
            "rows": [["营业成本", "(1,234.56)"]],
        }
        result = skill._normalize_financial_table(table)
        assert result[0]["2023"] == -1234.56

    def test_fullwidth_minus(self, skill):
        table = {
            "headers": ["科目", "2023年"],
            "rows": [["营业外支出", "－500.00"]],
        }
        result = skill._normalize_financial_table(table)
        assert result[0]["2023"] == -500.0


class TestValidateTables:
    def test_empty_tables_warning(self, skill):
        tables = {"income": [], "balance": [], "cashflow": [], "key_metrics": []}
        result = skill._validate_tables(tables)
        assert result["total_tables"] == 0
        assert any("income" in w for w in result["warnings"])

    def test_valid_tables(self, skill):
        tables = {
            "income": [{"科目": "营业收入", "2023": 100.0}, {"科目": "净利润", "2023": 20.0}],
            "balance": [],
            "cashflow": [],
            "key_metrics": [],
        }
        result = skill._validate_tables(tables)
        assert result["valid_tables"] >= 1

    def test_non_numeric_detection(self, skill):
        tables = {
            "income": [{"科目": "营业收入", "2023": "N/A"}, {"科目": "净利润", "2023": "N/A"}, {"科目": "毛利", "2023": "N/A"}, {"科目": "税前利润", "2023": "N/A"}],
            "balance": [],
            "cashflow": [],
            "key_metrics": [],
        }
        result = skill._validate_tables(tables)
        assert len(result["needs_manual_review"]) > 0


class TestGenerateFallbackFramework:
    def test_basic_fallback(self, skill):
        sections = [
            {"title": "概述", "section_type": "overview", "importance": 3},
            {"title": "财务", "section_type": "financial", "importance": 5},
            {"title": "风险", "section_type": "risk", "importance": 5},
        ]
        result = skill._generate_fallback_framework(sections)
        assert "aspects" in result
        assert "aspect_to_profile" in result
        assert "aspect_to_section_ids" in result
        assert len(result["aspects"]) >= 2

    def test_low_importance_filtered(self, skill):
        sections = [
            {"title": "备查", "section_type": "other", "importance": 1},
            {"title": "财务", "section_type": "financial", "importance": 5},
        ]
        result = skill._generate_fallback_framework(sections)
        assert "财务分析" in result["aspects"]
        assert result["aspect_to_profile"]["财务分析"] == "financial_analysis"

    def test_empty_sections(self, skill):
        result = skill._generate_fallback_framework([])
        assert result["aspects"] == []


class TestSplitByToc:
    def test_basic_split(self, skill):
        all_text = ["Page 1 content", "Page 2 content", "Page 3 content", "Page 4 content"]
        toc = [
            {"title": "概述", "page": 1, "level": 1},
            {"title": "财务", "page": 2, "level": 1},
        ]
        result = skill._split_by_toc(all_text, toc)
        assert len(result) == 2
        assert result[0]["title"] == "概述"
        assert result[1]["title"] == "财务"

    def test_nested_toc_skipped(self, skill):
        all_text = ["P1", "P2", "P3"]
        toc = [
            {"title": "第一章", "page": 1, "level": 1},
            {"title": "1.1 子节", "page": 1, "level": 3},
        ]
        result = skill._split_by_toc(all_text, toc)
        assert len(result) == 1


class TestExtractFinancialTablesSmart:
    @pytest.mark.asyncio
    async def test_chinese_keyword_match(self, skill):
        tables = [
            {"headers": ["科目", "2023"], "rows": [["营业收入", "100"], ["净利润", "20"]]},
        ]
        result = await skill._extract_financial_tables_smart(tables)
        assert len(result["income"]) >= 1
        for row in result["income"]:
            assert isinstance(row, dict), f"Each row must be dict, got {type(row)}"

    @pytest.mark.asyncio
    async def test_english_keyword_match(self, skill):
        tables = [
            {"headers": ["Item", "2023"], "rows": [["Revenue", "100"], ["Net Income", "20"]]},
        ]
        result = await skill._extract_financial_tables_smart(tables)
        assert len(result["income"]) >= 1
        for row in result["income"]:
            assert isinstance(row, dict), f"Each row must be dict, got {type(row)}"

    @pytest.mark.asyncio
    async def test_no_match(self, skill):
        tables = [
            {"headers": ["Name", "Age"], "rows": [["Alice", "30"]]},
        ]
        result = await skill._extract_financial_tables_smart(tables)
        assert len(result["income"]) == 0

    @pytest.mark.asyncio
    async def test_multiple_tables_flattened(self, skill):
        tables = [
            {"headers": ["科目", "2023"], "rows": [["营业收入", "100"]]},
            {"headers": ["科目", "2023"], "rows": [["总资产", "500"]]},
        ]
        result = await skill._extract_financial_tables_smart(tables)
        for row in result["income"]:
            assert isinstance(row, dict)
        for row in result["balance"]:
            assert isinstance(row, dict)


class TestMergeReports:
    def test_single_report(self, skill):
        report = {"meta": {"file_path": "a.pdf"}, "sections": [{"title": "A"}]}
        result = skill._merge_reports([report])
        assert result["meta"]["file_path"] == "a.pdf"

    def test_multiple_reports(self, skill):
        reports = [
            {"meta": {"file_path": "a.pdf"}, "sections": [{"title": "A"}],
             "financial_tables": {"income": [{"科目": "营收"}], "balance": [], "cashflow": [], "key_metrics": []},
             "analysis_framework": {"aspects": ["财务"]}},
            {"meta": {"file_path": "b.pdf"}, "sections": [{"title": "B"}],
             "financial_tables": {"income": [{"科目": "营收2"}], "balance": [], "cashflow": [], "key_metrics": []},
             "analysis_framework": {}},
        ]
        result = skill._merge_reports(reports)
        assert result["meta"]["report_count"] == 2
        assert len(result["sections"]) == 2
        assert len(result["financial_tables"]["income"]) == 2


class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_unsupported_action(self, skill):
        result = await skill.execute(action="unknown")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_no_file_paths(self, skill):
        result = await skill.execute(action="parse")
        assert result["success"] is False


class TestMultilingualKeywords:
    def test_all_languages_present(self):
        for table_type in ("income", "balance", "cashflow"):
            assert "zh" in FINANCIAL_TABLE_KEYWORDS[table_type]
            assert "en" in FINANCIAL_TABLE_KEYWORDS[table_type]
            assert "ja" in FINANCIAL_TABLE_KEYWORDS[table_type]

    def test_japanese_keywords_not_empty(self):
        for table_type in ("income", "balance", "cashflow"):
            assert len(FINANCIAL_TABLE_KEYWORDS[table_type]["ja"]) > 0
