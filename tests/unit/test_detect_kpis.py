import pytest
from src.converters.template_selector import TemplateSelector


@pytest.fixture
def selector():
    return TemplateSelector()


class TestDetectKpis:
    def test_absolute_value_with_unit(self, selector):
        items = ["Revenue reached 15.1B USD in 2024"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 1
        assert kpis[0]["number"] == "15.1B"
        assert kpis[0]["trend"] is None

    def test_percentage_as_fallback(self, selector):
        items = ["Market share grew to 28.9%"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 1
        assert kpis[0]["number"] == "28.9%"

    def test_absolute_with_percentage_trend(self, selector):
        items = ["Revenue 15.1B, up 28.9% YoY"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 1
        assert kpis[0]["number"] == "15.1B"
        assert kpis[0]["trend"] == "28.9%"

    def test_year_followed_by_B_not_matched(self, selector):
        items = ["Project 2024B launched"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 0

    def test_version_number_not_matched(self, selector):
        items = ["Version 2B released"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 0

    def test_single_digit_with_currency_matched(self, selector):
        items = ["Valued at 5B USD"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 1
        assert kpis[0]["number"] == "5B"

    def test_chinese_units(self, selector):
        items = ["营收达到3.2万亿"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 1
        assert kpis[0]["number"] == "3.2万亿"

    def test_label_from_colon_prefix(self, selector):
        items = ["Total Revenue: 15.1B USD"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["label"] == "Total Revenue"

    def test_label_from_stopword_filter(self, selector):
        items = ["Global revenue reached 15.1B"]
        kpis = selector._detect_kpis(items)
        assert "reached" not in kpis[0]["label"].lower()
        assert "Global" in kpis[0]["label"] or "revenue" in kpis[0]["label"]

    def test_label_empty_when_only_stopwords(self, selector):
        items = ["reached 15.1B"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["label"] == ""

    def test_trend_direction_up(self, selector):
        items = ["Revenue grew 15.1B"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["trend_direction"] == "up"

    def test_trend_direction_down(self, selector):
        items = ["Revenue declined 15.1B"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["trend_direction"] == "down"

    def test_no_trend_direction(self, selector):
        items = ["Revenue 15.1B"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["trend_direction"] is None

    def test_multiple_kpis(self, selector):
        items = ["Revenue 15.1B", "Users 2.7M", "Growth 28.9%"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 3

    def test_no_kpi_in_plain_text(self, selector):
        items = ["This is a qualitative observation"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 0

    def test_phase_3B_not_matched(self, selector):
        items = ["Phase 3B completed"]
        kpis = selector._detect_kpis(items)
        assert len(kpis) == 0

    def test_original_text_preserved(self, selector):
        items = ["Revenue 15.1B USD"]
        kpis = selector._detect_kpis(items)
        assert kpis[0]["original_text"] == "Revenue 15.1B USD"

    def test_percentage_token_filtered_from_label(self, selector):
        items = ["Revenue 15.1B, 28.9% growth"]
        kpis = selector._detect_kpis(items)
        assert "28.9%" not in kpis[0]["label"]
