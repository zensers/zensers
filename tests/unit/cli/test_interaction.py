"""Tests for interaction callback builder."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


class TestBuildInteractionCallback:
    @pytest.mark.asyncio
    async def test_returns_callable(self):
        from cli.interaction import build_interaction_callback
        mock_console = Mock()
        fake_questionary = Mock()
        with patch.dict("sys.modules", {"questionary": fake_questionary}):
            callback = await build_interaction_callback(mock_console)
        assert callable(callback)

    @pytest.mark.asyncio
    async def test_missing_questionary_raises(self):
        from cli.interaction import build_interaction_callback
        mock_console = Mock()
        with patch.dict("sys.modules", {"questionary": None}):
            with patch("builtins.__import__", side_effect=ImportError("no questionary")):
                with pytest.raises((SystemExit, ImportError)):
                    await build_interaction_callback(mock_console)


class TestInteractionCallbackRouting:
    @pytest.mark.asyncio
    async def test_options_step_routes_to_handle_options(self):
        from cli.interaction import _handle_options
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Option1")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_questionary.Style = Mock(return_value=[])
        mock_console = Mock()

        result = await _handle_options(
            mock_questionary, mock_console,
            {"options": [{"label": "Option1", "value": "opt1"}]},
            [{"label": "Option1", "value": "opt1"}],
            "Select one:",
            "select_output_type",
        )
        assert "output_type" in result
        assert result["output_type"] == "opt1"

    @pytest.mark.asyncio
    async def test_framework_step_routes_to_handle_framework(self):
        from cli.interaction import _handle_framework
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="detailed - Full analysis (20)")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_framework(
            mock_questionary, mock_console,
            {"framework_options": [{"id": "detailed", "name": "detailed", "description": "Full analysis", "estimated_pages": "20"}]},
            [{"id": "detailed", "name": "detailed", "description": "Full analysis", "estimated_pages": "20"}],
            "Select framework:",
        )
        assert "framework_id" in result
        assert result["framework_id"] == "detailed"

    @pytest.mark.asyncio
    async def test_summary_confirm(self):
        from cli.interaction import _handle_summary
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Confirm and start")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_summary(
            mock_questionary, mock_console,
            {"summary": {"topic": "AI Market", "output_type": "industry_report"}},
            {"topic": "AI Market", "output_type": "industry_report"},
            "Confirm?",
        )
        assert result["confirmed"] is True

    @pytest.mark.asyncio
    async def test_summary_cancel(self):
        from cli.interaction import _handle_summary
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Cancel")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_summary(
            mock_questionary, mock_console,
            {"summary": {}}, {},
            "Confirm?",
        )
        assert result["confirmed"] is False

    @pytest.mark.asyncio
    async def test_preview_confirm(self):
        from cli.interaction import _handle_preview
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Confirm and finalize")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_preview(
            mock_questionary, mock_console,
            {"preview_url": "http://example.com/preview"},
            "Preview ready:",
        )
        assert result["action"] == "confirm"

    @pytest.mark.asyncio
    async def test_preview_revise(self):
        from cli.interaction import _handle_preview
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Needs revision")
        mock_text = Mock()
        mock_text.ask_async = AsyncMock(return_value="Add more data")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_questionary.text = Mock(return_value=mock_text)
        mock_console = Mock()

        result = await _handle_preview(
            mock_questionary, mock_console,
            {"actions": ["confirm", "revise"]},
            "Preview:",
        )
        assert result["action"] == "revise"
        assert result["adjustment"] == "Add more data"

    @pytest.mark.asyncio
    async def test_fallback_continue(self):
        from cli.interaction import _handle_fallback
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Continue")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_fallback(mock_questionary, mock_console, {"step": "unknown"})
        assert result["confirmed"] is True

    @pytest.mark.asyncio
    async def test_fallback_cancel(self):
        from cli.interaction import _handle_fallback
        mock_questionary = Mock()
        mock_select = Mock()
        mock_select.ask_async = AsyncMock(return_value="Cancel")
        mock_questionary.select = Mock(return_value=mock_select)
        mock_console = Mock()

        result = await _handle_fallback(mock_questionary, mock_console, {"step": "unknown"})
        assert result["confirmed"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
