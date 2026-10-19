"""Tests for session commands."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


class TestSessionStartCommand:
    def test_session_start_help(self):
        result = runner.invoke(app, ["session", "start", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.output
        assert "--user-id" in result.output


class TestSessionAttachCommand:
    def test_session_attach_help(self):
        result = runner.invoke(app, ["session", "attach", "--help"])
        assert result.exit_code == 0


class TestSessionListCommand:
    def test_session_list_help(self):
        result = runner.invoke(app, ["session", "list", "--help"])
        assert result.exit_code == 0


class TestSessionShowCommand:
    def test_session_show_help(self):
        result = runner.invoke(app, ["session", "show", "--help"])
        assert result.exit_code == 0


class TestSessionHistoryCommand:
    def test_session_history_help(self):
        result = runner.invoke(app, ["session", "history", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output


class TestSessionModifyCommand:
    def test_session_modify_help(self):
        result = runner.invoke(app, ["session", "modify", "--help"])
        assert result.exit_code == 0
        assert "--aspects" in result.output
        assert "--topic" in result.output


class TestSessionConfirmCommand:
    def test_session_confirm_help(self):
        result = runner.invoke(app, ["session", "confirm", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--output" in result.output


class TestSessionReviseCommand:
    def test_session_revise_help(self):
        result = runner.invoke(app, ["session", "revise", "--help"])
        assert result.exit_code == 0
        assert "--aspects" in result.output


class TestSessionDeleteCommand:
    def test_session_delete_help(self):
        result = runner.invoke(app, ["session", "delete", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output


class TestSessionModifyValidation:
    def test_modify_no_args_fails(self):
        result = runner.invoke(app, ["session", "modify", "test-id"])
        assert result.exit_code == 1


class TestSessionReviseValidation:
    def test_revise_no_aspects_fails(self):
        result = runner.invoke(app, ["session", "revise", "test-id"])
        assert result.exit_code == 1


class TestSessionDeleteValidation:
    def test_delete_no_force_prompts(self):
        result = runner.invoke(app, ["session", "delete", "test-id"])
        assert result.exit_code == 0
        assert "force" in result.output.lower() or "sure" in result.output.lower()


class TestSessionAsyncFunctions:
    @pytest.mark.asyncio
    async def test_session_start_success(self):
        from cli.commands.session import _session_start
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_start = AsyncMock(return_value={
                    "session_id": "abc123",
                    "response": "Analysis started",
                })
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                with patch("src.cli.repl.SessionREPL") as MockREPL:
                    mock_repl = AsyncMock()
                    MockREPL.return_value = mock_repl
                    await _session_start("test requirement", "default", False)
                    mock_instance.research_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_start_api_error(self):
        from cli.commands.session import _session_start
        from src.cli.client import ZensersError
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_start = AsyncMock(side_effect=ZensersError("API error"))
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                with pytest.raises((SystemExit, Exception)):
                    await _session_start("test", "default", False)

    @pytest.mark.asyncio
    async def test_session_list_empty(self):
        from cli.commands.session import _session_list
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_sessions = AsyncMock(return_value={"sessions": []})
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                await _session_list()
                mock_instance.research_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_show(self):
        from cli.commands.session import _session_show
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_detail = AsyncMock(return_value={
                    "status": "running",
                    "topic": "Market Analysis",
                    "sections": ["market_size", "competition"],
                })
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                await _session_show("task-123")
                mock_instance.research_detail.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_session_confirm_success(self):
        from cli.commands.session import _session_confirm
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.document_generate = AsyncMock(return_value={
                    "success": True,
                    "document_path": "/tmp/report.docx",
                })
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                await _session_confirm("task-123", "docx", None)
                mock_instance.document_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_confirm_api_error(self):
        from cli.commands.session import _session_confirm
        from src.cli.client import ZensersError
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.document_generate = AsyncMock(side_effect=ZensersError("confirm failed"))
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                with pytest.raises((SystemExit, Exception)):
                    await _session_confirm("task-123", "docx", None)

    @pytest.mark.asyncio
    async def test_session_revise_success(self):
        from cli.commands.session import _session_revise
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_revise = AsyncMock(return_value={"status": "completed"})
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                await _session_revise("task-123", ["market_size"])
                mock_instance.research_revise.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_delete_no_force(self):
        from cli.commands.session import _session_delete
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            await _session_delete("task-123", force=False)
            assert not any("deleted" in str(c).lower() for c in mock_console.print.call_args_list)

    @pytest.mark.asyncio
    async def test_session_delete_with_force(self):
        from cli.commands.session import _session_delete
        mock_console = Mock()
        with patch("cli.commands.session.console", mock_console):
            with patch("src.cli.client.ZensersClient") as MockClient:
                mock_instance = AsyncMock()
                mock_instance.research_cancel = AsyncMock(return_value={"status": "cancelled"})
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_instance
                await _session_delete("task-123", force=True)
                mock_instance.research_cancel.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
