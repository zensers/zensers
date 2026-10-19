# -*- coding: utf-8 -*-
"""Tests for Markdown table to HTML conversion (改造项2)"""

import pytest
from src.content.content_orchestrator import ContentOrchestrator


class TestMdTableToHtml:
    """Test _md_table_to_html static method"""

    def test_basic_table(self):
        """Basic 3-row table with header"""
        lines = [
            "| 指标 | 2024年 | 2025年 |",
            "|------|--------|--------|",
            "| 销量 | 950万  | 1200万 |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert "<table" in result
        assert "<thead>" in result
        assert "<tbody>" in result
        assert "指标" in result and "<th" in result
        assert "950万" in result and "<td" in result

    def test_alignment(self):
        """Alignment hints: left, center, right"""
        lines = [
            "| 左 | 中 | 右 |",
            "|:---|:---:|---:|",
            "| a  | b   | c  |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert 'text-align:left' in result
        assert 'text-align:center' in result
        assert 'text-align:right' in result

    def test_inconsistent_columns_padded(self):
        """Rows with fewer columns get padded"""
        lines = [
            "| A | B | C |",
            "|---|---|---|",
            "| 1 | 2 |",  # Missing one column
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert result != ""  # Doesn't crash
        # Empty cell padded — may have style attribute
        assert "><" in result  # There's an empty cell somewhere

    def test_separator_with_empty_cells(self):
        """Separator row with empty cells doesn't break alignment detection"""
        lines = [
            "| A |  | C |",
            "|---|--|---|",
            "| 1 | 2 | 3 |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert result != ""

    def test_too_few_lines_returns_empty(self):
        """Less than 2 lines returns empty string"""
        assert ContentOrchestrator._md_table_to_html(["| A | B |"]) == ""

    def test_no_separator_returns_empty(self):
        """No separator row returns empty string (prevents | text | false match)"""
        lines = [
            "| some text |",
            "| other text |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert result == ""

    def test_data_table_class(self):
        """Output table has data-table class"""
        lines = [
            "| A | B |",
            "|---|---|",
            "| 1 | 2 |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert 'class="data-table"' in result

    def test_multiple_data_rows(self):
        """Table with multiple data rows"""
        lines = [
            "| 名称 | 数值 |",
            "|------|------|",
            "| A    | 10   |",
            "| B    | 20   |",
            "| C    | 30   |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert result.count("<tr>") == 4  # 1 header + 3 data
        # td tags may have style attributes, so check for td> pattern
        assert result.count("<td") == 6  # 3 rows * 2 cols

    def test_inline_markdown_in_cells(self):
        """Bold/italic in cells gets converted"""
        lines = [
            "| 名称 | 描述 |",
            "|------|------|",
            "| A    | **加粗** |",
        ]
        result = ContentOrchestrator._md_table_to_html(lines)
        assert "<strong>加粗</strong>" in result


class TestContentToHtmlMdTable:
    """Test _content_to_html integration with MD tables"""

    def test_md_table_converted_in_content(self):
        """MD table in content gets converted to HTML table"""
        content = "一些文字\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n更多文字"
        result = ContentOrchestrator._content_to_html(content)
        assert "<table" in result
        assert "A" in result and "<th" in result
        assert "1" in result and "<td" in result

    def test_fallback_on_invalid_table(self):
        """Invalid MD table (no separator) falls back to paragraphs"""
        content = "| some text |\n| other text |"
        result = ContentOrchestrator._content_to_html(content)
        # Should not contain table tags, should contain paragraphs
        assert "<table" not in result
        assert "section-content" in result

    def test_non_table_pipe_not_matched(self):
        """Standalone | in text is not treated as table"""
        content = "公式: a | b = c"
        result = ContentOrchestrator._content_to_html(content)
        assert "<table" not in result

    def test_mixed_content_with_table(self):
        """Heading + table + paragraph works together"""
        content = "## 标题\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n段落文字"
        result = ContentOrchestrator._content_to_html(content)
        assert "subsection-title" in result
        assert "<table" in result
        assert "section-content" in result
