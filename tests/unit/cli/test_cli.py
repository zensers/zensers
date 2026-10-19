"""CLI unit tests — updated for refactored module structure."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


class TestCLICommands:
    def test_cli_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Zensers" in result.output
        assert "research" in result.output
        assert "session" in result.output
        assert "task" in result.output

    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Zensers" in result.output

    def test_research_command_help(self):
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--format" in result.output

    def test_status_command_help(self):
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "--watch" in result.output

    def test_download_command_help(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output

    def test_global_options_present(self):
        result = runner.invoke(app, ["--help"])
        assert "--api-url" in result.output
        assert "--no-color" in result.output
        assert "--json" in result.output


class TestConfigCommand:
    def test_config_show(self):
        result = runner.invoke(app, ["config", "--show"])
        assert result.exit_code == 0
        assert "default_output_format" in result.output

    def test_config_set_invalid_format(self):
        result = runner.invoke(app, ["config", "--set", "no_equals_sign"])
        assert result.exit_code == 1

    def test_config_set_unknown_key(self):
        result = runner.invoke(app, ["config", "--set", "nonexistent_key=val"])
        assert result.exit_code == 1

    def test_config_no_args(self):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0


class TestSessionCommands:
    def test_session_help(self):
        result = runner.invoke(app, ["session", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "attach" in result.output
        assert "history" in result.output

    def test_session_start_help(self):
        result = runner.invoke(app, ["session", "start", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.output

    def test_session_attach_help(self):
        result = runner.invoke(app, ["session", "attach", "--help"])
        assert result.exit_code == 0

    def test_session_history_help(self):
        result = runner.invoke(app, ["session", "history", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output


class TestTaskCommands:
    def test_task_help(self):
        result = runner.invoke(app, ["task", "--help"])
        assert result.exit_code == 0
        assert "pause" in result.output
        assert "cancel" in result.output
        assert "status" in result.output


class TestLLMCommands:
    def test_llm_help(self):
        result = runner.invoke(app, ["llm", "--help"])
        assert result.exit_code == 0
        assert "set-config" in result.output
        assert "reset-config" in result.output

    def test_llm_set_config_help(self):
        result = runner.invoke(app, ["llm", "set-config", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.output


class TestClientErrors:
    def test_zensers_error(self):
        from cli.client import ZensersError
        err = ZensersError("test", status_code=500)
        assert err.message == "test"
        assert err.status_code == 500

    def test_connection_error(self):
        from cli.client import ZensersConnectionError, ZensersError
        err = ZensersConnectionError("refused")
        assert isinstance(err, ZensersError)

    def test_not_found_error(self):
        from cli.client import ZensersNotFoundError, ZensersError
        err = ZensersNotFoundError("missing")
        assert isinstance(err, ZensersError)

    def test_server_error(self):
        from cli.client import ZensersServerError, ZensersError
        err = ZensersServerError("internal")
        assert isinstance(err, ZensersError)


class TestClientContextManager:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                assert client._base_url == "http://localhost:8000"


class TestREPLCommands:
    @pytest.mark.asyncio
    async def test_quit_command(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("test-session")
        result = await repl._handle_command("/quit")
        assert result is False

    @pytest.mark.asyncio
    async def test_exit_command(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("test-session")
        result = await repl._handle_command("/exit")
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        from cli.repl import SessionREPL
        repl = SessionREPL("test-session")
        result = await repl._handle_command("/unknown")
        assert result is True

    @pytest.mark.asyncio
    async def test_help_command(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("test-session", console=mock_console)
        result = await repl._handle_command("/help")
        assert result is True

    @pytest.mark.asyncio
    async def test_revise_no_arg(self):
        from cli.repl import SessionREPL
        mock_console = Mock()
        repl = SessionREPL("test-session", console=mock_console)
        result = await repl._handle_command("/revise")
        assert result is True


class TestCLIConfig:
    def test_load_defaults(self):
        from cli.utils import CLIConfig
        with patch.object(Path, "exists", return_value=False):
            cfg = CLIConfig.load()
        assert cfg.default_output_format == "markdown"
        assert cfg.auto_save_reports is True

    def test_save_and_load(self):
        from cli.utils import CLIConfig
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "config.json"
            with patch.object(Path, "home", return_value=Path(tmpdir).parent):
                with patch("cli.utils.Path.home", return_value=Path(tmpdir)):
                    cfg = CLIConfig(default_output_format="docx")
                    cfg.save()
                    loaded = CLIConfig.load()
                    assert loaded.default_output_format == "docx"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
