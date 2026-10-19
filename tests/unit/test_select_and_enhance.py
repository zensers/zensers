import pytest
from src.converters.template_selector import TemplateSelector


@pytest.fixture
def selector():
    return TemplateSelector()


class TestSelect:
    def test_cover_type(self, selector):
        assert selector._select({"slide_type": "cover"}) == "cover"

    def test_toc_type(self, selector):
        assert selector._select({"slide_type": "toc"}) == "toc"

    def test_end_type(self, selector):
        assert selector._select({"slide_type": "end"}) == "end"

    def test_section_title_underscore(self, selector):
        assert selector._select({"slide_type": "section_title"}) == "section_title"

    def test_section_title_hyphen(self, selector):
        assert selector._select({"slide_type": "section-title"}) == "section_title"

    def test_findings_type(self, selector):
        assert selector._select({"slide_type": "findings"}) == "findings"

    def test_data_with_table(self, selector):
        assert selector._select({"slide_type": "data", "table_data": [["H"], ["V"]]}) == "data_table"

    def test_kpi_highlight(self, selector):
        items = ["Revenue 15.1B", "Users 2.7M", "Growth 28.9%"]
        kpis = selector._detect_kpis(items)
        assert selector._select({"slide_type": "content", "items": items}, kpis=kpis) == "kpi_highlight"

    def test_chart_split_two_images(self, selector):
        data = {"slide_type": "content", "items": [], "images": [{"src": "a.png"}, {"src": "b.png"}]}
        assert selector._select(data) == "chart_split"

    def test_chart_full_single_image(self, selector):
        data = {"slide_type": "content", "items": [], "images": [{"src": "a.png"}]}
        assert selector._select(data) == "chart_full"

    def test_comparison_vs_items(self, selector):
        items = ["US vs China market", "US leads", "China leads"]
        comp = selector._detect_comparison(items)
        assert selector._select({"slide_type": "content", "items": items}, comparison=comp) == "comparison"

    def test_content_left_right(self, selector):
        data = {"slide_type": "content", "items": ["Point A", "Point B", "Point C"], "images": [{"src": "a.png"}]}
        assert selector._select(data) == "content_left_right"

    def test_image_with_few_items_routes_to_chart(self, selector):
        data = {"slide_type": "content", "items": ["Caption"], "images": [{"src": "chart.png"}]}
        assert selector._select(data) == "chart_full"

    def test_content_text_only(self, selector):
        data = {"slide_type": "content", "items": ["Qualitative point A", "Qualitative point B"]}
        assert selector._select(data) == "content_text_only"

    def test_comparison_even_split_5_items(self, selector):
        items = ["Point A", "Point B", "Point C", "Point D", "Point E"]
        comp = selector._detect_comparison(items)
        assert selector._select({"slide_type": "content", "items": items}, comparison=comp) == "comparison"

    def test_data_with_images_no_table(self, selector):
        data = {"slide_type": "data", "items": [], "images": [{"src": "chart.png"}]}
        assert selector._select(data) == "chart_full"


class TestSelectAndEnhance:
    def test_kpi_data_enhanced(self, selector):
        slide_data = {"slide_type": "content", "title": "Market Overview", "items": ["Revenue 15.1B", "Users 2.7M"]}
        name = selector.select_and_enhance(slide_data)
        assert name == "kpi_highlight"
        assert "kpi_data" in slide_data
        assert len(slide_data["kpi_data"]) == 2

    def test_kpi_empty_label_backfill_from_title(self, selector):
        slide_data = {"slide_type": "content", "title": "Market Overview", "items": ["Revenue 15.1B", "Users 2.7M"]}
        selector.select_and_enhance(slide_data)
        for kpi in slide_data["kpi_data"]:
            if not kpi.get("label"):
                assert kpi["label"] == "Market Overview"[:30]

    def test_comparison_data_enhanced(self, selector):
        slide_data = {"slide_type": "content", "items": ["US vs China market", "US leads", "China leads"]}
        name = selector.select_and_enhance(slide_data)
        assert name == "comparison"
        assert "comparison_data" in slide_data

    def test_section_title_enhanced(self, selector):
        slide_data = {"slide_type": "section_title", "title": "Market Analysis", "content": "This section covers market trends and dynamics"}
        name = selector.select_and_enhance(slide_data, section_index=3)
        assert name == "section_title"
        assert slide_data["section_number"] == 3
        assert "section_summary" in slide_data

    def test_insight_text_for_kpi_highlight(self, selector):
        slide_data = {"slide_type": "content", "title": "KPIs", "items": ["Revenue 15.1B", "Users 2.7M"], "content": "Strong growth. Revenue exceeded expectations."}
        selector.select_and_enhance(slide_data)
        assert "insight_text" in slide_data

    def test_insight_text_for_chart_full(self, selector):
        slide_data = {"slide_type": "content", "items": [], "images": [{"src": "chart.png"}], "content": "Chart shows upward trend."}
        selector.select_and_enhance(slide_data)
        assert "insight_text" in slide_data

    def test_no_insight_text_for_text_only(self, selector):
        slide_data = {"slide_type": "content", "items": ["Point A"], "content": "Some text."}
        selector.select_and_enhance(slide_data)
        assert "insight_text" not in slide_data

    def test_existing_insight_text_not_overwritten(self, selector):
        slide_data = {"slide_type": "content", "items": ["Revenue 15.1B", "Users 2.7M"], "content": "Some text.", "insight_text": "Custom insight"}
        selector.select_and_enhance(slide_data)
        assert slide_data["insight_text"] == "Custom insight"
