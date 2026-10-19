"""Tests for ContentOrchestrator PPTX chart pipeline (P0-2)"""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import os
import shutil
from pathlib import Path

from src.content.content_orchestrator import ContentOrchestrator, ContentSection, SectionType


CWD = str(Path.cwd())
TEST_TMP = os.path.join(CWD, "__orch_test_tmp__")


class TestChartResolutionByFormat:
    """Test that charts are resolved for all output formats."""
    
    def setup_method(self):
        os.makedirs(TEST_TMP, exist_ok=True)
        self.orch = ContentOrchestrator()
        
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.bar(["A", "B"], [1, 2])
        self.chart_path = os.path.join(TEST_TMP, "test_chart.png")
        fig.savefig(self.chart_path, dpi=100)
        plt.close(fig)
    
    def teardown_method(self):
        if os.path.exists(TEST_TMP):
            shutil.rmtree(TEST_TMP, ignore_errors=True)
    
    def _call_prepare(self, output_format, output_dir=TEST_TMP):
        section = ContentSection(
            id="sec_1", title="Test", content="Content.", order=0, type=SectionType.BODY
        )
        research_result = {
            "title": "Report",
            "sections": [{"charts": [{"path": self.chart_path, "caption": "Test", "title": "Chart1"}]}],
            "key_findings": [],
            "data_points": [],
        }
        return self.orch._prepare_template_variables(
            title="Report",
            sections=[section],
            key_findings=[],
            data_points=[],
            research_result=research_result,
            output_format=output_format,
            output_dir=output_dir,
        )
    
    def test_pptx_charts_have_absolute_paths(self):
        result = self._call_prepare("pptx")
        sections = result.get("sections", [])
        assert len(sections) >= 1
        charts = sections[0].get("charts", [])
        assert len(charts) == 1, f"Expected 1 chart for PPTX, got {len(charts)}"
        assert os.path.isabs(charts[0]["path"]), f"PPTX path should be absolute: {charts[0]['path']}"
    
    def test_docx_charts_have_absolute_paths(self):
        result = self._call_prepare("docx")
        sections = result.get("sections", [])
        assert len(sections) >= 1
        charts = sections[0].get("charts", [])
        assert len(charts) == 1, f"Expected 1 chart for DOCX, got {len(charts)}"
        assert os.path.isabs(charts[0]["path"]), f"DOCX path should be absolute: {charts[0]['path']}"
    
    def test_pdf_charts_have_absolute_paths(self):
        result = self._call_prepare("pdf")
        sections = result.get("sections", [])
        assert len(sections) >= 1
        charts = sections[0].get("charts", [])
        assert len(charts) == 1, f"Expected 1 chart for PDF, got {len(charts)}"
        assert os.path.isabs(charts[0]["path"]), f"PDF path should be absolute: {charts[0]['path']}"
    
    def test_html_charts_consumed(self):
        result = self._call_prepare("html")
        sections = result.get("sections", [])
        assert len(sections) >= 1
        charts = sections[0].get("charts", [])
        assert len(charts) == 0, f"HTML should consume charts, got {len(charts)}"
    
    def test_no_charts_no_crash(self):
        for fmt in ["html", "pptx", "pdf", "docx"]:
            section = ContentSection(
                id="sec_1", title="Test", content="Content.", order=0, type=SectionType.BODY
            )
            research_result = {"title": "Report", "sections": [{}], "key_findings": [], "data_points": []}
            result = self.orch._prepare_template_variables(
                title="Report", sections=[section], key_findings=[], data_points=[],
                research_result=research_result, output_format=fmt, output_dir=TEST_TMP,
            )
            assert result is not None


class TestRenderSectionSlidesWithCharts:
    """Test _render_section_slides includes chart images."""
    
    def setup_method(self):
        self.orch = ContentOrchestrator()
    
    def test_section_with_charts_produces_img_tags(self):
        section = ContentSection(
            id="sec_1", title="Market Analysis", content="The market grew 5%.",
            order=0, type=SectionType.BODY,
            charts=[{"path": "/tmp/chart1.png", "caption": "Growth Chart", "anchor_type": "section_end"}],
        )
        slides = self.orch._render_section_slides(section, 1)
        all_html = "\n".join(slides)
        assert '<img src=' in all_html
        assert "chart1.png" in all_html
    
    def test_section_without_charts_no_img(self):
        section = ContentSection(
            id="sec_1", title="No Charts", content="Just text.",
            order=0, type=SectionType.BODY, charts=[],
        )
        slides = self.orch._render_section_slides(section, 1)
        all_html = "\n".join(slides)
        assert '<img src=' not in all_html
    
    def test_multiple_charts_produce_multiple_img(self):
        section = ContentSection(
            id="sec_1", title="Multi", content="Content.",
            order=0, type=SectionType.BODY,
            charts=[
                {"path": "/tmp/a.png", "caption": "A", "anchor_type": "section_end"},
                {"path": "/tmp/b.png", "caption": "B", "anchor_type": "section_end"},
            ],
        )
        slides = self.orch._render_section_slides(section, 1)
        all_html = "\n".join(slides)
        assert all_html.count('<img src=') >= 2
    
    def test_chart_only_section_produces_data_slide(self):
        section = ContentSection(
            id="sec_1", title="Chart Only", content="",
            order=0, type=SectionType.BODY,
            charts=[{"path": "/tmp/c.png", "caption": "C", "title": "Chart C", "anchor_type": "section_end"}],
        )
        slides = self.orch._render_section_slides(section, 1)
        data_slides = [s for s in slides if 'data-type="data"' in s]
        assert len(data_slides) >= 1
    
    def test_chart_alt_text_uses_caption(self):
        section = ContentSection(
            id="sec_1", title="Alt", content="Content.",
            order=0, type=SectionType.BODY,
            charts=[{"path": "/tmp/d.png", "caption": "Revenue Trend", "anchor_type": "section_end"}],
        )
        slides = self.orch._render_section_slides(section, 1)
        all_html = "\n".join(slides)
        assert "Revenue Trend" in all_html


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
