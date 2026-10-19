import pytest
from src.core.adjustment.ppt_report_adapter import PptReportAdapter


class TestPptReportAdapter:
    def test_adapts_slide_data_list_with_sections(self):
        slide_data_list = [
            {"slide_type": "cover", "title": "Market Report"},
            {"slide_type": "content", "title": "Market Size", "items": ["TAM $10B"]},
        ]
        adapter = PptReportAdapter(slide_data_list, task_id="t1")
        assert adapter.id == "t1"
        assert len(adapter.sections) == 2
        assert adapter.sections[0].id == "slide_0"
        assert adapter.sections[0].title == "Market Report"
        assert adapter.sections[1].title == "Market Size"

    def test_fallback_title_for_missing_title(self):
        slide_data_list = [{"slide_type": "content", "title": ""}]
        adapter = PptReportAdapter(slide_data_list, task_id="t1")
        assert adapter.sections[0].title == "Slide 1"

    def test_map_type_section_title(self):
        adapter = PptReportAdapter(
            [{"slide_type": "section_title", "title": "Ch1"}], task_id="t1"
        )
        assert adapter.sections[0].type == "section_title"

    def test_map_type_section_title_hyphenated(self):
        adapter = PptReportAdapter(
            [{"slide_type": "section-title", "title": "Ch1"}], task_id="t1"
        )
        assert adapter.sections[0].type == "section_title"

    def test_map_type_unknown_defaults_to_content(self):
        adapter = PptReportAdapter(
            [{"slide_type": "weird_type", "title": "Test"}], task_id="t1"
        )
        assert adapter.sections[0].type == "content"

    def test_build_content_text_includes_items(self):
        sd = {"slide_type": "content", "title": "Test", "items": ["point1", "point2"]}
        adapter = PptReportAdapter([sd], task_id="t1")
        content = adapter._build_content_text(sd)
        assert "point1" in content
        assert "point2" in content

    def test_build_content_text_includes_table_rows(self):
        sd = {"slide_type": "data", "title": "Test", 
              "table_data": [["Year", "Rev"], ["2024", "$10B"], ["2025", "$12B"], ["2026", "$15B"]]}
        adapter = PptReportAdapter([sd], task_id="t1")
        content = adapter._build_content_text(sd)
        assert "2024" in content
        assert "$15B" not in content

    def test_empty_slide_data_list(self):
        adapter = PptReportAdapter([], task_id="t1")
        assert len(adapter.sections) == 0
