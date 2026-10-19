"""Integration tests with real PDF: E:\market_report_systerm\docs\年报.pdf
Validates full pipeline: parse → framework → merge → cross_year → token truncation
"""
import pytest
import asyncio
import os
from src.skills.analysis.annual_report_parser import AnnualReportParserSkill


REAL_PDF = r"E:\market_report_systerm\docs\年报.pdf"
SKIP_IF_NO_PDF = pytest.mark.skipif(not os.path.exists(REAL_PDF), reason="年报.pdf not found")


@pytest.fixture
def skill():
    return AnnualReportParserSkill()


@SKIP_IF_NO_PDF
class TestRealPDFParsing:
    def test_extract_toc(self, skill):
        toc = skill._extract_toc(REAL_PDF)
        assert isinstance(toc, list)
        assert len(toc) > 0
        for entry in toc[:5]:
            assert "title" in entry
            assert "page" in entry

    def test_extract_text_and_tables(self, skill):
        all_text, all_tables = skill._extract_text_and_tables(REAL_PDF)
        assert isinstance(all_text, list)
        assert len(all_text) > 0
        assert isinstance(all_tables, list)
        assert len(all_tables) > 0
        non_empty_pages = [p for p in all_text if p and p.strip()]
        assert len(non_empty_pages) > 50

    def test_split_by_toc(self, skill):
        toc = skill._extract_toc(REAL_PDF)
        all_text, _ = skill._extract_text_and_tables(REAL_PDF)
        if toc:
            sections = skill._split_by_toc(all_text, toc[:30])
        else:
            sections = skill._generate_fallback_framework(
                [{"title": "Full", "content": all_text[0][:500] if all_text else "", "section_type": "overview", "importance": 1}]
            )
            sections = sections.get("aspects", [])
        assert len(sections) > 0

    def test_extract_year(self, skill):
        all_text, _ = skill._extract_text_and_tables(REAL_PDF)
        year = skill._extract_year(REAL_PDF, all_text[:5])
        assert year is not None
        assert 2020 <= year <= 2026

    def test_extract_financial_tables_smart(self, skill):
        _, all_tables = skill._extract_text_and_tables(REAL_PDF)
        result = skill._extract_financial_tables_smart(all_tables)
        assert isinstance(result, dict)
        assert "income" in result
        assert "balance" in result
        assert "cashflow" in result
        total_rows = sum(len(v) for v in result.values())
        assert total_rows > 0

    def test_validate_tables(self, skill):
        _, all_tables = skill._extract_text_and_tables(REAL_PDF)
        ft = skill._extract_financial_tables_smart(all_tables)
        validation = skill._validate_tables(ft)
        assert isinstance(validation, dict)
        assert "total_tables" in validation
        assert "valid_tables" in validation
        assert "warnings" in validation

    def test_generate_fallback_framework(self, skill):
        toc = skill._extract_toc(REAL_PDF)
        all_text, _ = skill._extract_text_and_tables(REAL_PDF)
        if toc:
            sections = skill._split_by_toc(all_text, toc[:30])
        else:
            sections = [{"title": "Full Report", "content": "", "section_type": "overview", "importance": 1}]
        typed_sections = []
        for s in sections:
            if isinstance(s, dict) and "title" in s:
                s.setdefault("section_type", skill._guess_section_type(s["title"]))
                s.setdefault("importance", skill._guess_importance(s.get("section_type", "other")))
                typed_sections.append(s)
        framework = skill._generate_fallback_framework(typed_sections)
        assert "aspects" in framework
        assert "aspect_to_profile" in framework
        assert len(framework["aspects"]) > 0


@SKIP_IF_NO_PDF
class TestRealPDFFullPipeline:
    """Test the complete parse_single_report pipeline (sync parts only)"""

    def test_parse_sync_components(self, skill):
        all_text, all_tables = skill._extract_text_and_tables(REAL_PDF)
        toc = skill._extract_toc(REAL_PDF)
        year = skill._extract_year(REAL_PDF, all_text[:5])
        assert year is not None
        ft = skill._extract_financial_tables_smart(all_tables)
        assert sum(len(v) for v in ft.values()) > 0
        validation = skill._validate_tables(ft)
        assert isinstance(validation, dict)
        if toc:
            sections = skill._split_by_toc(all_text, toc[:30])
        else:
            sections = [{"title": "Full", "content": "", "section_type": "overview", "importance": 1}]
        typed_sections = []
        for s in sections:
            if isinstance(s, dict) and "title" in s:
                s.setdefault("section_type", skill._guess_section_type(s["title"]))
                s.setdefault("importance", skill._guess_importance(s.get("section_type", "other")))
                typed_sections.append(s)
        framework = skill._generate_fallback_framework(typed_sections)
        assert len(framework["aspects"]) > 0
        merged = skill._merge_reports([{
            "meta": {"file_path": REAL_PDF, "year": year, "page_count": len(all_text), "has_bookmarks": bool(toc)},
            "sections": typed_sections,
            "financial_tables": ft,
            "analysis_framework": framework,
        }])
        assert "sections" in merged
        assert "financial_tables" in merged
        assert "analysis_framework" in merged
        assert "table_validation" in merged
        assert "meta" in merged


@SKIP_IF_NO_PDF
class TestRealPDFTokenTruncation:
    def test_large_context_truncation(self, skill):
        all_text, _ = skill._extract_text_and_tables(REAL_PDF)
        from src.core.agents.generic_agent import GenericAgent
        spec = type("Spec", (), {
            "name": "test_agent", "role": "analyst", "skills": [],
            "context": {}, "max_retries": 1, "timeout": 30,
        })()
        agent = GenericAgent(spec)
        full_text = "\n\n".join(p for p in all_text if p and p.strip())
        result = agent._truncate_by_tokens(full_text, max_tokens=2000)
        assert agent._count_tokens(result) <= 2500
        assert "截断" in result

    def test_table_preservation_with_real_tables(self, skill):
        _, all_tables = skill._extract_text_and_tables(REAL_PDF)
        ft = skill._extract_financial_tables_smart(all_tables)
        table_text = ""
        for table_type, rows in ft.items():
            if rows:
                table_text += f"\n#### {table_type}\n"
                for row in rows[:3]:
                    table_text += f"- {row}\n"
        from src.core.agents.generic_agent import GenericAgent
        spec = type("Spec", (), {
            "name": "test_agent", "role": "analyst", "skills": [],
            "context": {}, "max_retries": 1, "timeout": 30,
        })()
        agent = GenericAgent(spec)
        result = agent._truncate_by_tokens(table_text, max_tokens=500, preserve_tables=True)
        assert len(result) > 0
