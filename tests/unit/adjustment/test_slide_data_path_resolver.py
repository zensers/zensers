import pytest
from src.core.adjustment.slide_data_path_resolver import SlideDataPathResolver


class TestSlideDataPathResolverGet:
    def test_get_simple_key(self):
        data = {"title": "Market Size", "content": "text"}
        assert SlideDataPathResolver.get(data, "title") == "Market Size"

    def test_get_nested_key(self):
        data = {"kpi_data": [{"number": "100", "label": "Revenue"}]}
        assert SlideDataPathResolver.get(data, "kpi_data[0].number") == "100"

    def test_get_array_index(self):
        data = {"items": ["point1", "point2", "point3"]}
        assert SlideDataPathResolver.get(data, "items[0]") == "point1"
        assert SlideDataPathResolver.get(data, "items[2]") == "point3"

    def test_get_missing_key_returns_default(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.get(data, "missing") is None
        assert SlideDataPathResolver.get(data, "missing", "fallback") == "fallback"

    def test_get_out_of_range_index_returns_default(self):
        data = {"items": ["a", "b"]}
        assert SlideDataPathResolver.get(data, "items[5]") is None

    def test_get_nested_missing_path_returns_default(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.get(data, "kpi_data[0].number") is None

    def test_get_empty_path_returns_root(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.get(data, "") == data

    def test_get_dict_index_on_non_list_returns_default(self):
        data = {"items": "not_a_list"}
        assert SlideDataPathResolver.get(data, "items[0]") is None

    def test_get_key_on_non_dict_returns_default(self):
        data = {"items": ["a", "b"]}
        assert SlideDataPathResolver.get(data, "items[0].sub") is None


class TestSlideDataPathResolverSet:
    def test_set_simple_key(self):
        data = {"title": "old"}
        assert SlideDataPathResolver.set(data, "title", "new") is True
        assert data["title"] == "new"

    def test_set_nested_key(self):
        data = {"kpi_data": [{"number": "100", "label": "Revenue"}]}
        assert SlideDataPathResolver.set(data, "kpi_data[0].number", "200") is True
        assert data["kpi_data"][0]["number"] == "200"

    def test_set_array_index(self):
        data = {"items": ["a", "b", "c"]}
        assert SlideDataPathResolver.set(data, "items[1]", "X") is True
        assert data["items"][1] == "X"

    def test_set_missing_nested_key_returns_false(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.set(data, "kpi_data[0].number", "val") is False

    def test_set_out_of_range_returns_false(self):
        data = {"items": ["a"]}
        assert SlideDataPathResolver.set(data, "items[3]", "val") is False

    def test_set_empty_path_returns_false(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.set(data, "", "val") is False

    def test_set_creates_new_key_in_existing_dict(self):
        data = {"title": "test"}
        assert SlideDataPathResolver.set(data, "new_field", "val") is True
        assert data["new_field"] == "val"
