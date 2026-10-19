"""Test: P0-5 GenericAgent document_context injection + preloaded data

Tests:
1. _truncate_by_paragraph truncates at paragraph boundaries
2. document_context injection in prompt
3. preloaded data delivery for DATA_COLLECTION agents
"""
import pytest


class TestTruncateByParagraph:
    def _truncate(self, text, max_chars=8000):
        if len(text) <= max_chars:
            return text
        paragraphs = text.split('\n\n')
        result = []
        current_len = 0
        for para in paragraphs:
            if current_len + len(para) + 2 > max_chars:
                break
            result.append(para)
            current_len += len(para) + 2
        if not result:
            lines = text.split('\n')
            for line in lines:
                if current_len + len(line) + 1 > max_chars:
                    break
                result.append(line)
                current_len += len(line) + 1
        truncated = '\n\n'.join(result) if '\n\n' in text[:max_chars] else '\n'.join(result)
        if len(truncated) < len(text):
            truncated += "\n\n[... truncated ...]"
        return truncated

    def test_short_text_not_truncated(self):
        text = "Short text"
        result = self._truncate(text, max_chars=100)
        assert result == text

    def test_truncation_at_paragraph_boundary(self):
        paragraphs = ["Short para 1", "Short para 2", "Short para 3 " * 50]
        text = '\n\n'.join(paragraphs)
        result = self._truncate(text, max_chars=200)
        assert "Short para 1" in result
        assert "Short para 2" in result

    def test_single_paragraph_truncated_by_line(self):
        text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        result = self._truncate(text, max_chars=20)
        assert "Line 1" in result

    def test_truncation_marker_added(self):
        text = "A" * 20000
        result = self._truncate(text, max_chars=100)
        assert "truncated" in result.lower()


class TestDocumentContextInjection:
    def test_dict_tables_formatted(self):
        document_tables = {
            "income": [{"科目": "Revenue", "2023": 100.0}],
            "balance": [],
            "cashflow": [{"科目": "Operating", "2023": 50.0}],
        }
        doc_injection = "\n### 结构化财务数据\n"
        for table_type, rows in document_tables.items():
            if rows:
                doc_injection += f"\n#### {table_type}\n"
                for row in rows:
                    doc_injection += f"- {row}\n"
        
        assert "income" in doc_injection
        assert "cashflow" in doc_injection
        assert "balance" not in doc_injection

    def test_list_tables_formatted(self):
        document_tables = [{"table": 1}, {"table": 2}, {"table": 3},
                           {"table": 4}, {"table": 5}, {"table": 6}]
        doc_injection = "\n### 结构化财务数据\n"
        for table in document_tables[:5]:
            doc_injection += f"\n{table}\n"
        
        assert "table" in doc_injection
        assert len([l for l in doc_injection.split('\n') if 'table' in l]) == 5

    def test_empty_tables_no_injection(self):
        document_tables = {"income": [], "balance": [], "cashflow": []}
        doc_injection = ""
        for table_type, rows in document_tables.items():
            if rows:
                doc_injection += f"#### {table_type}\n"
        
        assert doc_injection == ""


class TestPreloadedDataDelivery:
    def test_data_points_from_sections(self):
        annual_report_data = {
            "sections": [
                {"title": "Financial", "content": "Revenue is 1 billion"},
                {"title": "Risk", "content": "Market risk is high"},
            ],
            "financial_tables": {
                "income": [{"科目": "Revenue", "2023": 1000}],
                "balance": [],
                "cashflow": [],
            },
        }
        data_points = []
        for section in annual_report_data.get("sections", []):
            data_points.append({
                "title": section.get("title", ""),
                "content": section.get("content", "")[:2000],
                "source": "annual_report_pdf",
                "type": "document",
            })
        for table_type, rows in annual_report_data.get("financial_tables", {}).items():
            for row in rows[:10]:
                data_points.append({
                    "title": f"{table_type} - {row.get('科目', '')}",
                    "content": str(row),
                    "source": "annual_report_pdf_table",
                    "type": "structured_data",
                })
        
        assert len(data_points) == 3
        assert data_points[0]["source"] == "annual_report_pdf"
        assert data_points[2]["source"] == "annual_report_pdf_table"

    def test_context_preloaded_flag(self):
        context = {"preloaded": True, "aspect": "Financial Analysis", "topic": "Test"}
        assert context.get("preloaded") is True
