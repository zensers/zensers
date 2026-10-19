import pytest
from src.converters.template_selector import TemplateSelector


@pytest.fixture
def selector():
    return TemplateSelector()


class TestDetectComparison:
    def test_vs_separator(self, selector):
        items = ["US vs China market size", "US leads in tech", "China leads in manufacturing"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["title"] == "US"
        assert result["right"]["title"] == "China market size"

    def test_vs_case_insensitive(self, selector):
        items = ["Apple VS Samsung revenue", "Apple has loyal users", "Samsung has wider reach"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["title"] == "Apple"
        assert result["right"]["title"] == "Samsung revenue"

    def test_chinese_duibi_separator(self, selector):
        items = ["线上对比线下渠道", "线上增长快", "线下份额大"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["title"] == "线上"
        assert result["right"]["title"] == "线下渠道"

    def test_dash_separator_line(self, selector):
        items = ["Strong brand", "High margin", "---", "Competition", "Regulation"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["items"] == ["Strong brand", "High margin"]
        assert result["right"]["items"] == ["Competition", "Regulation"]

    def test_even_split_fallback(self, selector):
        items = ["Point A", "Point B", "Point C", "Point D", "Point E"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert len(result["left"]["items"]) == 2
        assert len(result["right"]["items"]) == 3

    def test_single_item_returns_none(self, selector):
        items = ["Only one item"]
        result = selector._detect_comparison(items)
        assert result is None

    def test_empty_items_returns_none(self, selector):
        items = []
        result = selector._detect_comparison(items)
        assert result is None

    def test_unmatched_items_to_shorter_side(self, selector):
        items = ["Alpha vs Beta", "Extra point"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["title"] == "Alpha"
        assert result["right"]["title"] == "Beta"
        assert "Extra point" in result["left"]["items"] or "Extra point" in result["right"]["items"]

    def test_em_dash_separator(self, selector):
        items = ["2023——2024 revenue comparison", "2023 was stable", "2024 grew"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert result["left"]["title"] == "2023"
        assert result["right"]["title"] == "2024 revenue comparison"

    def test_title_not_duplicated_in_items(self, selector):
        items = ["Cat vs Dog preference", "Cat owners are happy", "Dog owners are loyal"]
        result = selector._detect_comparison(items)
        assert result is not None
        assert "Cat" not in result["left"]["items"]
        assert "Dog preference" not in result["right"]["items"]
