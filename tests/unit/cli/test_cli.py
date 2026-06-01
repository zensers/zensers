"""CLI单元测试."""

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
    """测试CLI命令."""

    def test_cli_help(self):
        """测试CLI帮助信息."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Zensers" in result.output
        assert "research" in result.output

    def test_version_command(self):
        """测试版本命令."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Zensers" in result.output
        assert "0.1.0" in result.output

    def test_research_command_help(self):
        """测试research命令帮助."""
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "研究需求" in result.output
        assert "--output" in result.output
        assert "--format" in result.output

    def test_status_command_help(self):
        """测试status命令帮助."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "任务ID" in result.output
        assert "--watch" in result.output

    def test_download_command_help(self):
        """测试download命令帮助."""
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0
        assert "任务ID" in result.output
        assert "--output" in result.output


class TestConfigCommand:
    """测试配置命令."""

    def test_config_show_no_config(self):
        """测试显示配置（无配置文件）."""
        with patch.object(Path, "exists", return_value=False):
            result = runner.invoke(app, ["config", "--show"])
            assert result.exit_code == 0
            assert "尚未创建" in result.output or "dim" in result.output

    def test_config_reset(self):
        """测试重置配置."""
        with patch("builtins.open", mock_open := Mock()):
            with patch.object(Path, "mkdir"):
                result = runner.invoke(app, ["config", "--reset"])
                assert result.exit_code == 0
                assert "已重置" in result.output or "green" in result.output


class TestResearchCommand:
    """测试研究命令."""

    @pytest.mark.asyncio
    async def test_research_success(self):
        """测试研究命令成功执行."""
        mock_result = {
            "success": True,
            "report": {
                "title": "测试报告",
                "sections": [
                    {"title": "章节1", "content": "内容1"},
                    {"title": "章节2", "content": "内容2"},
                ]
            },
            "quality_score": 0.85,
        }
        
        with patch("cli.main.Orchestrator") as mock_orch:
            mock_instance = Mock()
            mock_instance.process_request = AsyncMock(return_value=mock_result)
            mock_orch.return_value = mock_instance
            
            result = runner.invoke(app, ["research", "测试需求"])
            
            assert result.exit_code == 0
            assert "完成" in result.output or "green" in result.output

    @pytest.mark.asyncio
    async def test_research_failure(self):
        """测试研究命令失败."""
        mock_result = {
            "success": False,
            "error": "研究失败",
        }
        
        with patch("cli.main.Orchestrator") as mock_orch:
            mock_instance = Mock()
            mock_instance.process_request = AsyncMock(return_value=mock_result)
            mock_orch.return_value = mock_instance
            
            result = runner.invoke(app, ["research", "测试需求"])
            
            assert result.exit_code == 1


class TestStatusCommand:
    """测试状态命令."""

    def test_status_list_no_tasks(self):
        """测试列出任务（无任务）."""
        with patch("cli.main.TaskStorage") as mock_storage:
            mock_instance = Mock()
            mock_instance.list_tasks.return_value = []
            mock_storage.return_value = mock_instance
            
            result = runner.invoke(app, ["status"])
            
            assert result.exit_code == 0
            assert "没有" in result.output or "dim" in result.output

    def test_status_show_task(self):
        """测试显示特定任务状态."""
        mock_task = {
            "id": "test-task-123",
            "status": "running",
            "progress": 50,
            "created_at": "2024-01-01T00:00:00",
        }
        
        with patch("cli.main.TaskStorage") as mock_storage:
            mock_instance = Mock()
            mock_instance.get_task.return_value = mock_task
            mock_storage.return_value = mock_instance
            
            result = runner.invoke(app, ["status", "test-task-123"])
            
            assert result.exit_code == 0
            assert "test-task-123" in result.output or "running" in result.output

    def test_status_task_not_found(self):
        """测试任务不存在."""
        with patch("cli.main.TaskStorage") as mock_storage:
            mock_instance = Mock()
            mock_instance.get_task.return_value = None
            mock_storage.return_value = mock_instance
            
            result = runner.invoke(app, ["status", "non-existent"])
            
            assert result.exit_code == 1
            assert "未找到" in result.output or "red" in result.output


class TestDownloadCommand:
    """测试下载命令."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """测试下载成功."""
        mock_task = {
            "id": "test-task-123",
            "status": "completed",
            "result": {
                "report": {
                    "title": "测试报告",
                    "sections": [{"title": "章节1", "content": "内容"}],
                }
            },
        }
        
        with patch("cli.main.TaskStorage") as mock_storage:
            mock_instance = Mock()
            mock_instance.get_task.return_value = mock_task
            mock_storage.return_value = mock_instance
            
            with patch("cli.main._save_report", new_callable=AsyncMock):
                result = runner.invoke(app, [
                    "download", "test-task-123",
                    "--output", "/tmp/test.md",
                    "--format", "markdown"
                ])
                
                assert result.exit_code == 0
                assert "已下载" in result.output or "green" in result.output

    def test_download_task_not_completed(self):
        """测试任务未完成."""
        mock_task = {
            "id": "test-task-123",
            "status": "running",
        }
        
        with patch("cli.main.TaskStorage") as mock_storage:
            mock_instance = Mock()
            mock_instance.get_task.return_value = mock_task
            mock_storage.return_value = mock_instance
            
            result = runner.invoke(app, [
                "download", "test-task-123",
                "--output", "/tmp/test.md"
            ])
            
            assert result.exit_code == 1
            assert "尚未完成" in result.output or "yellow" in result.output


class TestReportFormatting:
    """测试报告格式化."""

    def test_format_markdown_report(self):
        """测试Markdown格式化."""
        from cli.main import _format_markdown_report
        
        report = {
            "title": "测试报告",
            "sections": [
                {"title": "章节1", "content": "内容1"},
                {"title": "章节2", "content": "内容2"},
            ]
        }
        
        result = _format_markdown_report(report)
        
        assert "# 测试报告" in result
        assert "## 章节1" in result
        assert "## 章节2" in result
        assert "内容1" in result
        assert "内容2" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
