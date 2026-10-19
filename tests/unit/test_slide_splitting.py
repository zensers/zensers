import pytest
from src.converters.base_parser import SlideElementParser


@pytest.fixture
def parser():
    return SlideElementParser()


class TestSplitDenseSlides:
    def test_no_split_when_few_items(self, parser):
        slides = [{"slide_type": "content", "title": "T", "items": ["a", "b", "c"]}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1
        assert result[0]["items"] == ["a", "b", "c"]

    def test_split_12_items_into_3_slides(self, parser):
        items = [f"item_{i}" for i in range(12)]
        slides = [{"slide_type": "content", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 3
        assert len(result[0]["items"]) == 4
        assert len(result[1]["items"]) == 4
        assert len(result[2]["items"]) == 4

    def test_images_distributed_across_sub_slides(self, parser):
        items = [f"item_{i}" for i in range(8)]
        images = [{"src": "a.png", "alt": ""}, {"src": "b.png", "alt": ""}]
        slides = [{"slide_type": "content", "title": "T", "items": items, "images": images}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 2
        total_images = sum(len(s.get("images", [])) for s in result)
        assert total_images == 2

    def test_cover_not_split(self, parser):
        items = [f"item_{i}" for i in range(10)]
        slides = [{"slide_type": "cover", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1

    def test_toc_not_split(self, parser):
        items = [f"item_{i}" for i in range(10)]
        slides = [{"slide_type": "toc", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1

    def test_end_not_split(self, parser):
        items = [f"item_{i}" for i in range(10)]
        slides = [{"slide_type": "end", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1

    def test_data_with_table_not_split(self, parser):
        items = [f"item_{i}" for i in range(10)]
        slides = [{"slide_type": "data", "title": "T", "items": items, "table_data": [["h1", "h2"], ["v1", "v2"]]}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1

    def test_content_preserved_on_first_chunk(self, parser):
        items = [f"item_{i}" for i in range(8)]
        slides = [{"slide_type": "content", "title": "T", "items": items, "content": "intro text"}]
        result = parser._split_dense_slides(slides)
        assert result[0].get("content") == "intro text"
        assert "content" not in result[1]

    def test_title_preserved_on_all_sub_slides(self, parser):
        items = [f"item_{i}" for i in range(8)]
        slides = [{"slide_type": "content", "title": "Market", "items": items}]
        result = parser._split_dense_slides(slides)
        for s in result:
            assert s["title"] == "Market"

    def test_exactly_5_items_no_split(self, parser):
        items = [f"item_{i}" for i in range(5)]
        slides = [{"slide_type": "content", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 1

    def test_6_items_splits(self, parser):
        items = [f"item_{i}" for i in range(6)]
        slides = [{"slide_type": "content", "title": "T", "items": items}]
        result = parser._split_dense_slides(slides)
        assert len(result) == 2
