"""Tests for FormatStrategy interface and implementations (P0-0)"""
import sys
sys.path.insert(0, "E:/market_report_systerm")

from src.content.format_strategy import (
    FormatStrategy,
    DOCXStrategy,
    PPTXStrategy,
    PDFStrategy,
    OutputFormat,
    ChartStyleConfig,
    WritingDirective,
    QualityStandard,
    LayoutPreference,
    get_format_strategy,
    STRATEGY_REGISTRY,
)


class TestOutputFormat:
    def test_docx_value(self):
        assert OutputFormat.DOCX.value == "docx"

    def test_pptx_value(self):
        assert OutputFormat.PPTX.value == "pptx"

    def test_pdf_value(self):
        assert OutputFormat.PDF.value == "pdf"

    def test_html_value(self):
        assert OutputFormat.HTML.value == "html"

    def test_no_md(self):
        values = [f.value for f in OutputFormat]
        assert "md" not in values


class TestChartStyleConfig:
    def test_defaults(self):
        cfg = ChartStyleConfig()
        assert cfg.figsize == (5.0, 3.5)
        assert cfg.dpi == 200
        assert cfg.transparent_bg is False

    def test_pptx_overrides(self):
        cfg = ChartStyleConfig(
            figsize=(7.5, 4.5),
            dpi=200,
            title_fontsize=16,
            transparent_bg=True,
        )
        assert cfg.figsize == (7.5, 4.5)
        assert cfg.dpi == 200
        assert cfg.transparent_bg is True


class TestDOCXStrategy:
    def setup_method(self):
        self.strategy = DOCXStrategy()

    def test_format_name(self):
        assert self.strategy.format_name == "docx"

    def test_writing_directive_style(self):
        d = self.strategy.get_writing_directive()
        assert d.content_style == "detailed"
        assert d.require_chart_suggestion is False

    def test_chart_style_not_transparent(self):
        s = self.strategy.get_chart_style()
        assert s.transparent_bg is False
        assert s.figsize == (9.0, 5.2)
        assert s.dpi == 200

    def test_quality_standard_has_paragraph_checks(self):
        q = self.strategy.get_quality_standard()
        assert "paragraph_completeness" in q.check_items

    def test_chart_position_embedded(self):
        l = self.strategy.get_layout_preference()
        assert l.chart_position == "embedded"

    def test_prompt_suffix_mentions_detailed(self):
        p = self.strategy.get_chapter_writer_prompt_suffix()
        assert "详细" in p


class TestPPTXStrategy:
    def setup_method(self):
        self.strategy = PPTXStrategy()

    def test_format_name(self):
        assert self.strategy.format_name == "pptx"

    def test_writing_directive_style(self):
        d = self.strategy.get_writing_directive()
        assert d.content_style == "bullet_points"
        assert d.require_chart_suggestion is True
        assert d.bullet_max_chars == 25

    def test_chart_style_transparent(self):
        s = self.strategy.get_chart_style()
        assert s.transparent_bg is True
        assert s.figsize == (7.5, 4.5)
        assert s.dpi == 200
        assert s.title_fontsize == 16

    def test_quality_standard_has_chart_coverage(self):
        q = self.strategy.get_quality_standard()
        assert "chart_coverage" in q.check_items
        assert q.min_chart_count_per_section == 1
        assert q.max_slide_text_chars == 300

    def test_layout_preference_split(self):
        l = self.strategy.get_layout_preference()
        assert l.prefer_split_layout is True
        assert "chart_split" in l.slide_layouts
        assert l.chart_position == "right"

    def test_prompt_suffix_mentions_slide(self):
        p = self.strategy.get_chapter_writer_prompt_suffix()
        assert "幻灯片" in p
        assert "图表建议" in p


class TestPDFStrategy:
    def setup_method(self):
        self.strategy = PDFStrategy()

    def test_format_name(self):
        assert self.strategy.format_name == "pdf"

    def test_writing_directive_style(self):
        d = self.strategy.get_writing_directive()
        assert d.content_style == "detailed"
        assert d.require_chart_suggestion is False

    def test_chart_style_not_transparent(self):
        s = self.strategy.get_chart_style()
        assert s.transparent_bg is False
        assert s.dpi == 200

    def test_quality_standard_has_print_checks(self):
        q = self.strategy.get_quality_standard()
        assert "print_readability" in q.check_items


class TestGetFormatStrategy:
    def test_docx(self):
        s = get_format_strategy("docx")
        assert isinstance(s, DOCXStrategy)

    def test_pptx(self):
        s = get_format_strategy("pptx")
        assert isinstance(s, PPTXStrategy)

    def test_pdf(self):
        s = get_format_strategy("pdf")
        assert isinstance(s, PDFStrategy)

    def test_unknown_defaults_to_docx(self):
        s = get_format_strategy("unknown")
        assert isinstance(s, DOCXStrategy)

    def test_empty_defaults_to_docx(self):
        s = get_format_strategy("")
        assert isinstance(s, DOCXStrategy)


class TestStrategyRegistry:
    def test_has_three_entries(self):
        assert len(STRATEGY_REGISTRY) == 3

    def test_keys_match_output_format_values(self):
        assert "docx" in STRATEGY_REGISTRY
        assert "pptx" in STRATEGY_REGISTRY
        assert "pdf" in STRATEGY_REGISTRY

    def test_instances_are_correct_types(self):
        assert isinstance(STRATEGY_REGISTRY["docx"], DOCXStrategy)
        assert isinstance(STRATEGY_REGISTRY["pptx"], PPTXStrategy)
        assert isinstance(STRATEGY_REGISTRY["pdf"], PDFStrategy)


class TestStrategyInterface:
    def test_all_strategies_implement_interface(self):
        for name, strategy in STRATEGY_REGISTRY.items():
            assert isinstance(strategy, FormatStrategy), f"{name} does not implement FormatStrategy"
            assert strategy.format_name == name
            assert isinstance(strategy.get_writing_directive(), WritingDirective)
            assert isinstance(strategy.get_chart_style(), ChartStyleConfig)
            assert isinstance(strategy.get_quality_standard(), QualityStandard)
            assert isinstance(strategy.get_layout_preference(), LayoutPreference)
            assert isinstance(strategy.get_chapter_writer_prompt_suffix(), str)
            assert len(strategy.get_chapter_writer_prompt_suffix()) > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
