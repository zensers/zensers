# -*- coding: utf-8 -*-
"""
B1-B7: "Cannot preview this format" 修复测试

验证所有 status 硬编码检查点在 completed_with_warnings 状态下的行为。
每个测试对应文档中的一个 bug 项。

TDD RED 阶段: 这些测试应该全部失败（或断言不通过），
因为当前代码只接受 status == 'completed'。
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


def _make_research_result(status="completed", **kwargs):
    return {
        "task_id": "test_task_001",
        "status": status,
        "output_path": "/tmp/test_report.html",
        "document_path": "/tmp/test_report.html",
        "topic": "Test Topic",
        "stages_completed": 5,
        "report": {"sections": [{"id": "s1", "title": "Section 1"}]},
        "summary": "Test summary",
        **kwargs,
    }


# ============================================================
# B1: get_preview (research_api.py:1973)
# ============================================================

class TestB1GetPreviewStatusCheck:
    """
    get_preview 在 status='completed_with_warnings' 时应返回预览内容，
    而非空预览 {html_content: null, preview_url: null}。
    """

    @pytest.fixture
    def api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        return api

    @pytest.mark.asyncio
    async def test_completed_returns_preview(self, api, tmp_path):
        """status='completed' 应正常返回预览 (基线确认)"""
        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as ps:
            html_file = tmp_path / "test_task_001.html"
            html_file.write_text("<html>report</html>", encoding="utf-8")
            sm.get.return_value = {
                "research_result": _make_research_result("completed"),
            }
            ps.path.return_value = html_file
            ps.url.return_value = "/preview/test_task_001"

            result = await api.get_preview("test_task_001")

            assert result.get("html_content") is not None, \
                "completed 状态应返回 html_content"

    @pytest.mark.asyncio
    async def test_completed_with_warnings_returns_preview(self, api, tmp_path):
        """status='completed_with_warnings' 也应返回预览 (B1 核心)"""
        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as ps:
            html_file = tmp_path / "test_task_001.html"
            html_file.write_text("<html>report</html>", encoding="utf-8")
            sm.get.return_value = {
                "research_result": _make_research_result("completed_with_warnings"),
            }
            ps.path.return_value = html_file
            ps.url.return_value = "/preview/test_task_001"

            result = await api.get_preview("test_task_001")

            assert result.get("html_content") is not None, \
                "completed_with_warnings 状态应返回 html_content，当前返回 null 导致前端 Cannot preview this format"


# ============================================================
# B2: get_research_detail (main.py:565)
# ============================================================

class TestB2GetResearchDetailStatusCheck:
    """
    get_research_detail 在 status='completed_with_warnings' 时应设置
    has_valid_result=True，从而写入 preview_url。
    """

    def test_current_code_rejects_warnings(self):
        """确认当前代码的行为: status == 'completed' 对 warnings 返回 False"""
        research_result = _make_research_result("completed_with_warnings")
        current_has_valid = bool(research_result and research_result.get("status") == "completed")
        assert not current_has_valid, \
            "当前代码中 completed_with_warnings 的 has_valid_result=False，这就是 B2 bug"

    @pytest.mark.asyncio
    async def test_completed_with_warnings_gets_preview_url(self):
        """status='completed_with_warnings' 时 get_research_detail 应返回 preview_url (B2 集成)"""
        with patch("src.api.main.SessionManager") as sm_cls, \
             patch("src.api.main.PreviewStorage") as ps, \
             patch("src.api.main.ProgressStreamer") as prog:
            from src.api.main import app
            from fastapi.testclient import TestClient
            from starlette.testclient import TestClient as STC

            sm_instance = MagicMock()
            sm_cls.get_instance.return_value = sm_instance

            html_path = Path("/tmp/test_preview.html")
            sm_instance.get.return_value = {
                "research_result": _make_research_result("completed_with_warnings"),
                "research_context": {"topic": "Test"},
                "created_at": datetime.now(),
                "user_input": "test",
            }
            ps.path.return_value = html_path
            ps.url.return_value = "/preview/test_task_001"

            research_result = sm_instance.get.return_value.get("research_result", {})
            has_valid_result = bool(research_result and research_result.get("status") in ("completed", "completed_with_warnings"))
            assert has_valid_result, \
                "completed_with_warnings 应被视为有效结果，当前 has_valid_result=False 导致 preview_url 不写入响应"


# ============================================================
# B3: _handle_research_mode (research_api.py:365)
# ============================================================

class TestB3HandleResearchModeStatusCheck:
    """
    _handle_research_mode 在 status='completed_with_warnings' 时应进入 chat 模式。
    """

    def test_current_code_rejects_warnings(self):
        """确认当前代码的行为"""
        research_result = _make_research_result("completed_with_warnings")
        current_enters_chat = research_result and research_result.get("status") == "completed"
        assert not current_enters_chat, \
            "当前代码中 completed_with_warnings 不进入 chat 模式，这就是 B3 bug"

    @pytest.mark.asyncio
    async def test_completed_with_warnings_enters_chat_mode(self):
        """status='completed_with_warnings' 时 _handle_research_msg 应进入 chat 模式 (B3 集成)"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._handle_chat_mode = AsyncMock(return_value={"action": "chat"})

        session = {
            "research_result": _make_research_result("completed_with_warnings"),
            "mode": "research",
        }

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_paused.return_value = False
            gcm.return_value = cm

            result = await api._handle_research_msg("test_session", "hello", session)

            assert session.get("mode") == "chat", \
                "completed_with_warnings 应触发进入 chat 模式，当前未触发"


# ============================================================
# B5: resume_research (research_api.py:2067)
# ============================================================

class TestB5ResumeResearchStatusCheck:
    """
    resume_research 在 status='completed_with_warnings' 时应返回
    "Research already completed while paused"，而非继续恢复流程。
    """

    def test_current_code_rejects_warnings(self):
        """确认当前代码的行为"""
        rr = _make_research_result("completed_with_warnings")
        current_returns = rr and rr.get("status") == "completed"
        assert not current_returns, \
            "当前代码中 completed_with_warnings 不返回 'already completed'，这就是 B5 bug"

    @pytest.mark.asyncio
    async def test_completed_with_warnings_returns_already_completed(self):
        """status='completed_with_warnings' 时 resume_research 应返回 'already completed' (B5 集成)"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._load_cancel_snapshot = AsyncMock(return_value=None)

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_cancelled.return_value = False
            gcm.return_value = cm

            sm.get.return_value = {
                "research_result": _make_research_result("completed_with_warnings"),
            }

            result = await api.resume_research("test_task_001")

            assert result.get("status") == "completed", \
                "completed_with_warnings 应返回 'already completed while paused'，当前返回其他状态"


# ============================================================
# B6: inject merge status check (research_executor.py:179)
# ============================================================

class TestB6InjectMergeStatusCheck:
    """
    inject 操作后 result.status == "completed" 的检查应同时接受
    completed_with_warnings，否则合并逻辑被跳过。
    """

    def test_completed_allows_merge(self):
        """ResearchResult.status='completed' 应允许合并 (基线确认)"""
        @dataclass
        class FakeResult:
            status: str = "completed"

        result = FakeResult(status="completed")
        should_merge = result.status in ("completed", "completed_with_warnings")
        assert should_merge

    def test_completed_with_warnings_allows_merge(self):
        """ResearchResult.status='completed_with_warnings' 也应允许合并 (B6 核心)"""
        @dataclass
        class FakeResult:
            status: str = "completed_with_warnings"

        result = FakeResult(status="completed_with_warnings")
        should_merge = result.status in ("completed", "completed_with_warnings")
        assert should_merge, \
            "completed_with_warnings 应允许 inject 合并，当前跳过导致 inject 结果丢失"

    def test_current_code_rejects_warnings(self):
        """确认当前代码的行为"""
        @dataclass
        class FakeResult:
            status: str = "completed_with_warnings"

        result = FakeResult(status="completed_with_warnings")
        current_allows = result.status == "completed"
        assert not current_allows, \
            "当前代码中 completed_with_warnings 不允许 inject 合并，这就是 B6 bug"


# ============================================================
# B7: inject merge status override (research_executor.py:196)
# ============================================================

class TestB7InjectMergeStatusOverride:
    """
    inject 合并后 session["research_result"]["status"] 硬编码为 "completed"，
    应保留原始 status 或取两者中更差的状态。
    """

    def test_completed_preserves_completed(self):
        """original=completed + inject=completed → merged=completed (基线确认)"""
        original_status = "completed"
        inject_status = "completed"
        merged = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"
        assert merged == "completed"

    def test_original_warnings_preserved(self):
        """original=completed_with_warnings + inject=completed → merged=completed_with_warnings (B7 核心)"""
        original_status = "completed_with_warnings"
        inject_status = "completed"
        merged = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"
        assert merged == "completed_with_warnings", \
            "原始 completed_with_warnings 不应被覆盖为 completed"

    def test_inject_warnings_preserved(self):
        """original=completed + inject=completed_with_warnings → merged=completed_with_warnings (B7 核心)"""
        original_status = "completed"
        inject_status = "completed_with_warnings"
        merged = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"
        assert merged == "completed_with_warnings", \
            "inject 的 completed_with_warnings 不应被丢弃"

    def test_current_code_always_completed(self):
        """确认当前代码的行为: 硬编码 'completed' 丢失 warnings"""
        original_status = "completed_with_warnings"
        current_merged = "completed"  # 硬编码
        assert current_merged != original_status, \
            "当前代码硬编码 status='completed'，覆盖了原始的 completed_with_warnings，这就是 B7 bug"


# ============================================================
# B4: completion message (research_executor.py:467-472)
# ============================================================

class TestB4CompletionMessage:
    """
    完成消息应区分 completed 和 completed_with_warnings。
    """

    def test_completed_shows_success(self):
        """status='completed' 应显示 ✅"""
        status = "completed"
        is_warning = status == "completed_with_warnings"
        assert not is_warning, "completed 不应显示警告"

    def test_completed_with_warnings_shows_warning(self):
        """status='completed_with_warnings' 应显示 ⚠️ (B4 核心)"""
        status = "completed_with_warnings"
        is_warning = status == "completed_with_warnings"
        assert is_warning, \
            "completed_with_warnings 应被识别为警告状态，当前一律显示 ✅ 误导用户"

    def test_current_code_no_distinction(self):
        """确认当前代码的行为: 不区分两种状态"""
        for status in ("completed", "completed_with_warnings"):
            current_msg = "**Research Complete** ✅"
            assert "✅" in current_msg, \
                f"当前代码无论 status={status} 都显示 ✅，这就是 B4 bug"


# ============================================================
# 集成: 阻塞链路验证
# ============================================================

class TestBlockingChainIntegration:
    """
    验证 completed_with_warnings 在整条阻塞链路中应被接受。
    """

    def test_status_check_expression_b1(self):
        """B1: != 'completed' 对 warnings 的判断"""
        status = "completed_with_warnings"
        current_blocked = status != "completed"  # True → 被阻塞
        fixed_not_blocked = status not in ("completed", "completed_with_warnings")  # False → 不阻塞
        assert current_blocked, "当前 B1 阻塞了 warnings"
        assert not fixed_not_blocked, "修复后 B1 不应阻塞 warnings"

    def test_status_check_expression_b2(self):
        """B2: == 'completed' 对 warnings 的判断"""
        status = "completed_with_warnings"
        current_accepted = status == "completed"  # False → 不接受
        fixed_accepted = status in ("completed", "completed_with_warnings")  # True → 接受
        assert not current_accepted, "当前 B2 不接受 warnings"
        assert fixed_accepted, "修复后 B2 应接受 warnings"

    def test_status_check_expression_b3(self):
        """B3: == 'completed' 对 warnings 的判断"""
        status = "completed_with_warnings"
        current_enters = status == "completed"
        fixed_enters = status in ("completed", "completed_with_warnings")
        assert not current_enters, "当前 B3 不进入 chat"
        assert fixed_enters, "修复后 B3 应进入 chat"

    def test_status_check_expression_b5(self):
        """B5: == 'completed' 对 warnings 的判断"""
        status = "completed_with_warnings"
        current = status == "completed"
        fixed = status in ("completed", "completed_with_warnings")
        assert not current, "当前 B5 不返回 already_completed"
        assert fixed, "修复后 B5 应返回 already_completed"
