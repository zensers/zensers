import pytest
from unittest.mock import MagicMock, patch
from src.core.adjustment.ppt_element_editor import PptElementEditor


def _make_slide_data_with_chart():
    return {
        "slide_type": "data",
        "title": "Revenue",
        "images": [
            {"src": "/charts/bar_revenue.png", "alt": "Revenue Bar Chart", "image_type": "chart"},
        ],
    }


def _make_slide_data_with_images():
    return {
        "slide_type": "content",
        "title": "Overview",
        "images": [
            {"src": "/images/photo1.jpg", "alt": "Photo 1", "image_type": "photo"},
        ],
    }


class TestSwapChart:
    def test_swap_chart_updates_slide_data(self):
        editor = PptElementEditor()
        mock_chart_gen = MagicMock()
        mock_chart_gen.generate_chart.return_value = "/charts/pie_revenue.png"

        sd = _make_slide_data_with_chart()
        result = editor.swap_chart(sd, 0, "pie", chart_generator=mock_chart_gen)

        assert result is True
        assert sd["images"][0]["src"] == "/charts/pie_revenue.png"
        assert "pie" in sd["images"][0]["src"]

    def test_swap_chart_invalid_index_returns_false(self):
        editor = PptElementEditor()
        mock_chart_gen = MagicMock()
        sd = _make_slide_data_with_chart()
        result = editor.swap_chart(sd, 5, "pie", chart_generator=mock_chart_gen)
        assert result is False

    def test_swap_chart_no_images_returns_false(self):
        editor = PptElementEditor()
        mock_chart_gen = MagicMock()
        sd = {"slide_type": "content", "title": "No images"}
        result = editor.swap_chart(sd, 0, "pie", chart_generator=mock_chart_gen)
        assert result is False


class TestReplaceImage:
    def test_replace_image_updates_slide_data(self):
        editor = PptElementEditor()
        mock_img_provider = MagicMock()
        mock_img_provider.replace_image.return_value = {
            "src": "/images/new_photo.jpg", "alt": "New Photo", "image_type": "photo"
        }

        sd = _make_slide_data_with_images()
        result = editor.replace_image(sd, 0, "new keyword", image_provider=mock_img_provider)

        assert result is True
        assert sd["images"][0]["src"] == "/images/new_photo.jpg"

    def test_replace_image_invalid_index_returns_false(self):
        editor = PptElementEditor()
        mock_img_provider = MagicMock()
        sd = _make_slide_data_with_images()
        result = editor.replace_image(sd, 5, "keyword", image_provider=mock_img_provider)
        assert result is False

    def test_replace_image_no_images_returns_false(self):
        editor = PptElementEditor()
        mock_img_provider = MagicMock()
        sd = {"slide_type": "content", "title": "No images"}
        result = editor.replace_image(sd, 0, "keyword", image_provider=mock_img_provider)
        assert result is False
