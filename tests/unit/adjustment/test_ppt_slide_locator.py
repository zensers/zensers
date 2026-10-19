import pytest
from src.core.adjustment.ppt_slide_locator import PptSlideLocator


def _make_slide_data_list():
    return [
        {"slide_type": "cover", "title": "Market Report 2024"},
        {"slide_type": "section_title", "title": "Market Size"},
        {"slide_type": "content", "title": "TAM Analysis", "items": ["TAM $10B", "CAGR 5%"]},
        {"slide_type": "data", "title": "Revenue Breakdown", "table_data": [["Year", "Rev"], ["2024", "$10B"]]},
        {"slide_type": "end", "title": "Thank You"},
    ]


class TestLocateByIndex:
    def test_valid_index(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_index=2) == 2

    def test_index_zero(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_index=0) == 0

    def test_index_out_of_range_returns_none(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_index=10) is None

    def test_negative_index_returns_none(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_index=-1) is None


class TestLocateByTitle:
    def test_exact_title_match(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_title="Market Size") == 1

    def test_partial_title_match(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_title="Revenue") == 3

    def test_case_insensitive_match(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_title="tam analysis") == 2

    def test_no_match_returns_none(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, slide_title="Nonexistent") is None


class TestLocateByKeyword:
    def test_keyword_in_items(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, keyword="CAGR") == 2

    def test_keyword_in_table_data(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, keyword="Rev") == 3

    def test_keyword_no_match_returns_none(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl, keyword="nonexistent_keyword") is None


class TestLocatePriority:
    def test_index_takes_priority_over_title(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        result = locator.locate(sdl, slide_index=0, slide_title="Revenue")
        assert result == 0

    def test_title_takes_priority_over_keyword(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        result = locator.locate(sdl, slide_title="TAM Analysis", keyword="CAGR")
        assert result == 2

    def test_no_args_returns_none(self):
        locator = PptSlideLocator()
        sdl = _make_slide_data_list()
        assert locator.locate(sdl) is None
