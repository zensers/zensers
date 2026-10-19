import pytest
from unittest.mock import MagicMock, patch
from src.core.adjustment.ppt_atomic_editor import PptAtomicEditor
from src.core.adjustment.slide_data_path_resolver import SlideDataPathResolver


def _make_slide_data():
    return {
        "slide_type": "content",
        "title": "Market Size",
        "items": ["TAM $10B", "CAGR 5%"],
        "kpi_data": [{"number": "$10B", "label": "TAM"}],
    }


class TestUpdateSlideData:
    def test_update_title(self):
        editor = PptAtomicEditor()
        sd = _make_slide_data()
        result = editor.update_slide_data(sd, "title", "Updated Title")
        assert result is True
        assert sd["title"] == "Updated Title"

    def test_update_items_index(self):
        editor = PptAtomicEditor()
        sd = _make_slide_data()
        result = editor.update_slide_data(sd, "items[0]", "TAM $12B")
        assert result is True
        assert sd["items"][0] == "TAM $12B"

    def test_update_kpi_nested(self):
        editor = PptAtomicEditor()
        sd = _make_slide_data()
        result = editor.update_slide_data(sd, "kpi_data[0].number", "$12B")
        assert result is True
        assert sd["kpi_data"][0]["number"] == "$12B"

    def test_update_invalid_path_returns_false(self):
        editor = PptAtomicEditor()
        sd = _make_slide_data()
        result = editor.update_slide_data(sd, "nonexistent.field", "value")
        assert result is False

    def test_update_preserves_other_fields(self):
        editor = PptAtomicEditor()
        sd = _make_slide_data()
        editor.update_slide_data(sd, "title", "New Title")
        assert sd["items"] == ["TAM $10B", "CAGR 5%"]
        assert sd["kpi_data"][0]["label"] == "TAM"


class TestEditPptxShape:
    def test_edit_text_calls_shape_text_frame(self):
        editor = PptAtomicEditor()
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame.paragraphs = [MagicMock()]
        mock_shape.text_frame.paragraphs[0].runs = [MagicMock()]
        mock_shape.text_frame.paragraphs[0].runs[0].text = "old"

        editor.edit_text(mock_shape, "new text")

        mock_shape.text_frame.paragraphs[0].runs[0].text = "new text"

    def test_edit_text_no_text_frame_raises(self):
        editor = PptAtomicEditor()
        mock_shape = MagicMock()
        mock_shape.has_text_frame = False
        with pytest.raises(ValueError, match="no text frame"):
            editor.edit_text(mock_shape, "new text")

    def test_edit_text_empty_runs_sets_paragraph_text(self):
        editor = PptAtomicEditor()
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_para = MagicMock()
        mock_para.runs = []
        mock_shape.text_frame.paragraphs = [mock_para]

        editor.edit_text(mock_shape, "new text")

        mock_para.text = "new text"
