"""Tests for SessionREPL."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


class TestSessionREPLInit:
    def test_default_init(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("test-session")
        assert repl.session_id == "test-session"
        assert repl._api_base_url is None

    def test_custom_console(self):
        from cli.repl import SessionREPL
        from rich.console import Console
        mock_console = Mock(spec=Console)
        repl = SessionREPL("s1", console=mock_console)
        assert repl.console is mock_console

    def test_custom_api_url(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("s1", api_base_url="http://custom:9000")
        assert repl._api_base_url == "http://custom:9000"


class TestREPLQuitCommands:
    @pytest.mark.asyncio
    async def test_quit_returns_false(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("s1")
        assert await repl._handle_command("/quit") is False

    @pytest.mark.asyncio
    async def test_exit_returns_false(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("s1")
        assert await repl._handle_command("/exit") is False

    @pytest.mark.asyncio
    async def test_q_returns_false(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("s1")
        assert await repl._handle_command("/q") is False


class TestREPLHelpCommand:
    @pytest.mark.asyncio
    async def test_help_returns_true(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        assert await repl._handle_command("/help") is True

    @pytest.mark.asyncio
    async def test_help_prints_commands(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        await repl._handle_command("/help")
        assert mock_console.print.called


class TestREPLUnknownCommand:
    @pytest.mark.asyncio
    async def test_unknown_returns_true(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        assert await repl._handle_command("/unknown") is True


class TestREPLReviseCommand:
    @pytest.mark.asyncio
    async def test_revise_no_arg(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        result = await repl._handle_command("/revise")
        assert result is True

    @pytest.mark.asyncio
    async def test_revise_with_section(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_revise = AsyncMock(return_value={"status": "completed"})
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/revise market_size")
            assert result is True


class TestREPLHistoryCommand:
    @pytest.mark.asyncio
    async def test_history_empty(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_messages = AsyncMock(return_value={"messages": []})
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/history")
            assert result is True

    @pytest.mark.asyncio
    async def test_history_with_messages(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_messages = AsyncMock(return_value={
                "messages": [
                    {"role": "user", "content": "hello", "timestamp": "2024-01-01"},
                    {"role": "assistant", "content": "hi", "timestamp": "2024-01-01"},
                ]
            })
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/history")
            assert result is True


class TestREPLStatusCommand:
    @pytest.mark.asyncio
    async def test_status(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_status = AsyncMock(return_value={"status": "running", "progress": 0.5})
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/status")
            assert result is True


class TestREPLConfirmCommand:
    @pytest.mark.asyncio
    async def test_confirm(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.document_generate = AsyncMock(return_value={"success": True, "document_path": "/tmp/report.docx"})
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/confirm")
            assert result is True


class TestREPLExportCommand:
    @pytest.mark.asyncio
    async def test_export_default_format(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.document_export = AsyncMock(return_value=(b"doc content", "application/octet-stream"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/export")
            assert result is True

    @pytest.mark.asyncio
    async def test_export_pdf(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.document_export = AsyncMock(return_value=(b"pdf content", "application/pdf"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            result = await repl._handle_command("/export pdf")
            assert result is True


class TestREPLHandleMessage:
    @pytest.mark.asyncio
    async def test_message_sends_to_api(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        mock_console.print = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_interact = AsyncMock(return_value={
                "response": "Here is the analysis",
                "state": "reporting",
            })
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            await repl._handle_message("analyze market size")
            mock_instance.research_interact.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_api_error(self):
        from cli.repl import SessionREPL
        from cli.client import ZensersError
        mock_console = Mock()
        mock_console.print = Mock()
        repl = SessionREPL("s1", console=mock_console)
        with patch("src.cli.client.ZensersClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.research_interact = AsyncMock(side_effect=ZensersError("API error"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            await repl._handle_message("test")
            assert mock_console.print.called


class TestREPLConstants:
    def test_commands_defined(self):
        from cli.repl import REPL_COMMANDS
        assert "/help" in REPL_COMMANDS
        assert "/history" in REPL_COMMANDS
        assert "/status" in REPL_COMMANDS
        assert "/revise" in REPL_COMMANDS
        assert "/confirm" in REPL_COMMANDS
        assert "/export" in REPL_COMMANDS
        assert "/quit" in REPL_COMMANDS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
