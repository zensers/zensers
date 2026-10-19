# -*- coding: utf-8 -*-
"""
Table Data Extractor
====================

Parses Markdown tables from LLM output and extracts structured data
suitable for chart generation.

Features:
1. Parse standard Markdown tables (|...|...| format)
2. Extract headers, data rows, column types
3. Output structured dict compatible with ChartGenerator
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    """Parsed table result"""
    headers: List[str]
    rows: List[List[str]]
    caption: str = ""
    numeric_columns: List[int] = None

    def __post_init__(self):
        if self.numeric_columns is None:
            self.numeric_columns = self._detect_numeric_columns()

    def _detect_numeric_columns(self) -> List[int]:
        """Detect which columns contain numeric data"""
        if not self.rows:
            return []
        numeric_cols = []
        for col_idx in range(len(self.headers)):
            numeric_count = 0
            for row in self.rows:
                if col_idx < len(row):
                    if ExtractedTable._parse_number(row[col_idx]) is not None:
                        numeric_count += 1
            if numeric_count > len(self.rows) * 0.5:
                numeric_cols.append(col_idx)
        return numeric_cols

    def to_chart_data(
        self,
        value_column: Optional[int] = None,
        preferred_headers: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Convert to ChartGenerator-compatible data dict"""
        if len(self.headers) < 2 or len(self.rows) < 2:
            return None
        if not self.numeric_columns:
            return None
        categories = []
        values = []
        label_column = 0
        if value_column is None:
            value_column = self._choose_value_column(preferred_headers or self.headers)
        if value_column not in self.numeric_columns:
            return None
        for row in self.rows:
            if label_column < len(row) and value_column < len(row):
                label = row[label_column].strip()
                value = ExtractedTable._parse_number(row[value_column])
                if value is None or not label:
                    continue
                values.append(value)
                categories.append(label[:15])
        if len(categories) < 2:
            return None
        return {
            "categories": categories,
            "values": values,
            "headers": self.headers,
            "value_column": value_column,
            "value_header": self.headers[value_column],
            "source": "table",
        }

    def _choose_value_column(self, preferred_headers: List[str]) -> int:
        """Choose a semantically relevant numeric column deterministically.

        The old behavior always selected the first numeric column, which could
        silently chart revenue when the requested measure was margin or share.
        Header matching is intentionally conservative; callers can still pass
        an explicit column index when the table is ambiguous.
        """
        candidates = [h.lower() for h in preferred_headers if h]
        semantic_tokens = [
            token for header in candidates for token in (
                "份额", "市占", "占比", "比例", "率", "share", "margin", "利润",
                "growth", "增速", "增长", "revenue", "营收", "销售", "销量", "金额", "规模",
            ) if token in header
        ]
        if semantic_tokens:
            for index in self.numeric_columns:
                header = self.headers[index].lower()
                if any(token in header for token in semantic_tokens):
                    return index
        return self.numeric_columns[0]

    @staticmethod
    def _parse_number(value: Any) -> Optional[float]:
        """Parse common report-table numeric forms, including (1,234.5)."""
        if value is None:
            return None
        text = str(value).strip().replace(',', '').replace('%', '').replace('$', '')
        if not text or text in {'-', '--', '—', 'N/A', 'NA'}:
            return None
        negative = text.startswith('(') and text.endswith(')')
        if negative:
            text = text[1:-1].strip()
        try:
            parsed = float(text)
        except ValueError:
            return None
        if not math.isfinite(parsed):
            return None
        return -parsed if negative else parsed


class TableDataExtractor:
    """Extract structured data from Markdown tables in text content"""

    @staticmethod
    def extract_all(content: str) -> List[ExtractedTable]:
        """Extract all Markdown tables from content"""
        lines = content.split("\n")
        tables = []
        current_table_lines = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                current_table_lines.append(stripped)
                in_table = True
            else:
                if in_table and current_table_lines:
                    table = TableDataExtractor._parse_table_lines(current_table_lines)
                    if table:
                        tables.append(table)
                    current_table_lines = []
                    in_table = False
        if in_table and current_table_lines:
            table = TableDataExtractor._parse_table_lines(current_table_lines)
            if table:
                tables.append(table)
        return tables

    @staticmethod
    def _parse_table_lines(lines: List[str]) -> Optional[ExtractedTable]:
        """Parse a list of markdown table lines into structured data"""
        if len(lines) < 3:
            return None
        header_line = None
        data_lines = []
        for i, line in enumerate(lines):
            # Detect separator line: |---|---|  or |:---|:---:|
            stripped = line.replace("|", "").replace(":", "").replace("-", "").strip()
            if stripped == "" and "---" in line:
                header_line = lines[i - 1] if i > 0 else None
                data_lines = lines[i + 1:]
                break
        if not header_line or not data_lines:
            return None
        headers = TableDataExtractor._split_row(header_line)
        if len(headers) < 2:
            return None
        rows = []
        for line in data_lines:
            row = TableDataExtractor._split_row(line)
            if len(row) == len(headers):
                rows.append(row)
        if len(rows) < 2:
            return None
        return ExtractedTable(headers=headers, rows=rows)

    @staticmethod
    def _split_row(line: str) -> List[str]:
        """Split a markdown table row into cells"""
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        cells = []
        current = ""
        for char in line:
            if char == "|":
                cells.append(current.strip())
                current = ""
            else:
                current += char
        cells.append(current.strip())
        return cells


__all__ = ["TableDataExtractor", "ExtractedTable"]
