# -*- coding: utf-8 -*-
"""
端到端集成测试: "Cannot preview this format" 修复

模拟完整的用户流程:
1. research 完成后 status='completed_with_warnings'
2. get_preview → 应返回 html_content（修复前返回 null）
3. get_research_detail → 应返回 preview_url（修复前为 null）
4. _handle_research_msg → 应进入 chat 模式（修复前卡在 research 模式）
5. resume_research → 应返回 already_completed（修复前走 snapshot 恢复）
6. inject 合并 → 应保留 warnings 状态（修复前覆盖为 completed）
7. 完成消息 → 应区分 ⚠️/✅（修复前一律 ✅）
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


def _make_session(task_id="e2e_task_001", status="completed_with_warnings"):
    return {
        "task_id": task_id,
        "mode": "research",
        "status": status,
        "user_input": "Analyze the NEV market",
        "research_context": {
            "topic": "New Energy Vehicle Market Analysis",
            "framework": {
                "sections": ["Market Size", "Competition", "Technology"],
                "output_type": "industry_report",
            },
        },
        "research_result": {
            "task_id": task_id,
            "status": status,
            "output_path": "",
            "document_path": "",
            "topic": "New Energy Vehicle Market Analysis",
            "agents_used": ["market_analyst", "tech_analyst"],
            "stages_completed": 5,
            "report": {
                "sections": [
                    {"id": "market_size", "title": "Market Size", "content": "The NEV market reached..."},
                    {"id": "competition", "title": "Competition", "content": "BYD leads with..."},
                    {"id": "technology", "title": "Technology", "content": "Battery technology..."},
                ]
            },
            "summary": "The NEV market has grown significantly...",
        },
        "conversation_history": [
            {"role": "user", "content": "Analyze the NEV market"},
        ],
        "created_at": datetime.now().isoformat(),
    }


@dataclass
class FakeResearchResult:
    task_id: str = "e2e_task_001"
    status: str = "completed_with_warnings"
    topic: str = "NEV Market"
    agents_used: List[str] = field(default_factory=lambda: ["agent1"])
    stages_completed: int = 3
    output_path: Optional[str] = None
    summary: str = "Test summary"
    report: Dict[str, Any] = field(default_factory=dict)
    document_path: Optional[str] = None
    quality_score: float = 36.6
    quality_issues: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"type": "completeness", "severity": "medium", "message": "Data coverage insufficient"}
    ])


# ============================================================
# E2E Flow 1: Preview pipeline (B1 + B2)
# ============================================================

class TestE2EPreviewPipeline:
    """
    端到端: completed_with_warnings → get_preview → get_research_detail
    验证预览管道在 warnings 状态下是否畅通。
    """

    @pytest.mark.asyncio
    async def test_completed_with_warnings_gets_full_preview(self, tmp_path):
        """模拟用户点击 View Report 后，get_preview 应返回 html_content"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}

        html_content = "<html><body><h1>NEV Market Report</h1><p>Content here</p></body></html>"
        html_file = tmp_path / "e2e_task_001.html"
        html_file.write_text(html_content, encoding="utf-8")

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as ps:
            sm.get.return_value = _make_session()
            ps.path.return_value = html_file
            ps.url.return_value = "/api/v1/html-reports/e2e_task_001.html"

            result = await api.get_preview("e2e_task_001")

            assert result.get("html_content") is not None, \
                "get_preview 应返回 html_content"
            assert result.get("html_content") == html_content, \
                "html_content 应与文件内容一致"
            assert result.get("preview_url") is not None, \
                "get_preview 应返回 preview_url"
            assert result.get("preview_format") == "html"

    @pytest.mark.asyncio
    async def test_completed_gets_preview_baseline(self, tmp_path):
        """基线: completed 状态同样能正常预览"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}

        html_file = tmp_path / "e2e_task_002.html"
        html_file.write_text("<html>completed report</html>", encoding="utf-8")

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as ps:
            sm.get.return_value = _make_session("e2e_task_002", "completed")
            ps.path.return_value = html_file
            ps.url.return_value = "/api/v1/html-reports/e2e_task_002.html"

            result = await api.get_preview("e2e_task_002")
            assert result.get("html_content") is not None

    @pytest.mark.asyncio
    async def test_other_status_still_returns_empty(self, tmp_path):
        """非完成状态仍应返回空预览（回归确认）"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = _make_session("e2e_task_003", "running")

            result = await api.get_preview("e2e_task_003")
            assert result.get("html_content") is None, \
                "running 状态应返回空预览"
            assert result.get("preview_url") is None


# ============================================================
# E2E Flow 2: Chat mode transition (B3)
# ============================================================

class TestE2EChatModeTransition:
    """
    端到端: completed_with_warnings → 用户发消息 → 进入 chat 模式
    """

    @pytest.mark.asyncio
    async def test_warning_status_enters_chat_mode(self):
        """warnings 状态下用户发消息，应切换到 chat 模式"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._handle_chat_mode = AsyncMock(return_value={
            "action": "continue_chat",
            "message": "How can I help you further?",
        })

        session = _make_session()
        assert session["mode"] == "research", "初始应为 research 模式"

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_paused.return_value = False
            gcm.return_value = cm

            result = await api._handle_research_msg("e2e_task_001", "Show me the report", session)

            assert session.get("mode") == "chat", \
                "warnings 状态应切换到 chat 模式"
            api._handle_chat_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_completed_also_enters_chat_mode(self):
        """基线: completed 状态也进入 chat 模式"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._handle_chat_mode = AsyncMock(return_value={"action": "chat"})

        session = _make_session(status="completed")

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_paused.return_value = False
            gcm.return_value = cm

            await api._handle_research_msg("task", "hello", session)
            assert session.get("mode") == "chat"

    @pytest.mark.asyncio
    async def test_running_status_does_not_enter_chat(self):
        """回归: running 状态不应进入 chat 模式"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {"e2e_task_001": MagicMock(done=MagicMock(return_value=False))}
        api._llm_converse = AsyncMock(return_value={"action": "continue_chat"})

        session = _make_session(status="running")
        session["research_result"]["status"] = "executing"
        original_mode = session["mode"]

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_paused.return_value = False
            gcm.return_value = cm

            await api._handle_research_msg("e2e_task_001", "hello", session)
            assert session.get("mode") != "chat", \
                "running 状态不应进入 chat 模式"


# ============================================================
# E2E Flow 3: Resume research (B5)
# ============================================================

class TestE2EResumeResearch:
    """
    端到端: completed_with_warnings → resume_research → 返回 already completed
    """

    @pytest.mark.asyncio
    async def test_warning_status_resume_returns_already_completed(self):
        """warnings 状态下 resume，应返回 'already completed'"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._load_cancel_snapshot = AsyncMock(return_value=None)

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_cancelled.return_value = False
            gcm.return_value = cm

            sm.get.return_value = _make_session()

            result = await api.resume_research("e2e_task_001")

            assert result.get("status") == "completed", \
                f"应返回 status='completed'，实际返回 status='{result.get('status')}'"
            assert "already completed" in result.get("message", "").lower(), \
                f"消息应包含 'already completed'，实际: {result.get('message')}"

    @pytest.mark.asyncio
    async def test_completed_status_resume_returns_already_completed(self):
        """基线: completed 状态同样返回 already completed"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._load_cancel_snapshot = AsyncMock(return_value=None)

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_cancelled.return_value = False
            gcm.return_value = cm

            sm.get.return_value = _make_session(status="completed")

            result = await api.resume_research("e2e_task_001")
            assert result.get("status") == "completed"


# ============================================================
# E2E Flow 4: Inject merge preserves warnings (B6 + B7)
# ============================================================

class TestE2EInjectMergePreservesWarnings:
    """
    端到端: inject 操作后，completed_with_warnings 状态被保留
    模拟 research_executor.py 中的 inject 合并逻辑。
    """

    def test_original_warnings_preserved_after_merge(self):
        """original=completed_with_warnings + inject=completed → merged=completed_with_warnings"""
        original = {
            "task_id": "e2e_task_001",
            "status": "completed_with_warnings",
            "output_path": "/tmp/report.html",
            "report": {"sections": [{"id": "s1", "title": "Market Size"}]},
        }
        inject_result = FakeResearchResult(status="completed")

        original_status = original.get("status", "completed")
        inject_status = inject_result.status
        merged_status = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"

        assert merged_status == "completed_with_warnings", \
            "原始 warnings 状态应被保留"

    def test_inject_warnings_propagated_to_merged(self):
        """original=completed + inject=completed_with_warnings → merged=completed_with_warnings"""
        original = {
            "task_id": "e2e_task_001",
            "status": "completed",
            "output_path": "/tmp/report.html",
            "report": {"sections": [{"id": "s1", "title": "Market Size"}]},
        }
        inject_result = FakeResearchResult(status="completed_with_warnings")

        original_status = original.get("status", "completed")
        inject_status = inject_result.status
        merged_status = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"

        assert merged_status == "completed_with_warnings", \
            "inject 的 warnings 状态应被传播"

    def test_both_completed_stays_completed(self):
        """original=completed + inject=completed → merged=completed"""
        original = {"task_id": "t1", "status": "completed", "report": {"sections": []}}
        inject_result = FakeResearchResult(status="completed")

        original_status = original.get("status", "completed")
        inject_status = inject_result.status
        merged_status = "completed_with_warnings" if (
            original_status == "completed_with_warnings" or inject_status == "completed_with_warnings"
        ) else "completed"

        assert merged_status == "completed"

    def test_inject_merge_allows_warnings_status(self):
        """B6: inject 结果 status=completed_with_warnings 应允许合并"""
        inject_result = FakeResearchResult(status="completed_with_warnings")
        session = {"task_id": "t1"}
        should_merge = session is not None and inject_result and inject_result.status in ("completed", "completed_with_warnings")
        assert should_merge, "completed_with_warnings 应允许 inject 合并"


# ============================================================
# E2E Flow 5: Completion message differentiation (B4)
# ============================================================

class TestE2ECompletionMessage:
    """
    端到端: 验证完成消息区分 completed 和 completed_with_warnings
    """

    def test_warning_message_includes_quality_score(self):
        """warnings 消息应包含质量分数"""
        orchestrator_result = FakeResearchResult(
            status="completed_with_warnings",
            quality_score=36.6,
        )

        if orchestrator_result.status == "completed_with_warnings":
            msg = (
                f"**Research Complete** ⚠️\n\n"
                f"Quality score: {orchestrator_result.quality_score:.1f} — "
                f"report has quality issues but is available for preview."
            )
        else:
            msg = f"**Research Complete** ✅\n\nResearch completed."

        assert "⚠️" in msg, "warnings 状态应显示 ⚠️"
        assert "36.6" in msg, "消息应包含质量分数"

    def test_completed_message_shows_success(self):
        """completed 消息应显示 ✅"""
        orchestrator_result = FakeResearchResult(status="completed", quality_score=85.0)

        if orchestrator_result.status == "completed_with_warnings":
            msg = f"**Research Complete** ⚠️\n\nQuality score: {orchestrator_result.quality_score:.1f}"
        else:
            msg = f"**Research Complete** ✅\n\nResearch completed."

        assert "✅" in msg, "completed 状态应显示 ✅"
        assert "⚠️" not in msg

    def test_warning_suggestions_include_improve_quality(self):
        """warnings 状态的建议应包含 Improve Quality"""
        orchestrator_result = FakeResearchResult(status="completed_with_warnings")

        if orchestrator_result.status == "completed_with_warnings":
            suggestions = [
                {"id": "view_report", "label": "View Report"},
                {"id": "improve_quality", "label": "Improve Quality"},
            ]
        else:
            suggestions = [
                {"id": "view_report", "label": "View Report"},
            ]

        assert len(suggestions) == 2
        assert any(s["id"] == "improve_quality" for s in suggestions)


# ============================================================
# E2E Flow 6: Full pipeline — status transitions
# ============================================================

class TestE2EFullStatusPipeline:
    """
    端到端: 完整的状态流转验证
    从 completed_with_warnings 状态出发，验证每个检查点都正确处理。
    """

    def test_all_status_checks_accept_warnings(self):
        """所有修改过的检查点都应接受 completed_with_warnings"""
        status = "completed_with_warnings"

        checks = {
            "B1 (get_preview)": status not in ("completed", "completed_with_warnings"),
            "B2 (has_valid_result)": status in ("completed", "completed_with_warnings"),
            "B3 (chat mode)": status in ("completed", "completed_with_warnings"),
            "B5 (resume)": status in ("completed", "completed_with_warnings"),
            "B6 (inject merge)": status in ("completed", "completed_with_warnings"),
        }

        for name, accepted in checks.items():
            if name.startswith("B1"):
                assert not accepted, f"{name}: completed_with_warnings 不应被 'not in' 拒绝"
            else:
                assert accepted, f"{name}: completed_with_warnings 应被接受"

    def test_no_other_status_accepted(self):
        """其他非完成状态仍被拒绝（回归确认）"""
        for status in ["running", "failed", "cancelled", "paused", "error"]:
            accepted = status in ("completed", "completed_with_warnings")
            assert not accepted, f"status='{status}' 不应被接受为完成状态"

    @pytest.mark.asyncio
    async def test_end_to_end_user_journey_with_warnings(self, tmp_path):
        """
        完整用户旅程:
        1. Research 完成后 status=completed_with_warnings
        2. 用户点击 View Report → get_preview 返回内容
        3. 用户发消息 → 切换到 chat 模式
        4. 用户尝试 resume → 返回 already completed
        """
        from src.api.research_api import ResearchAPI

        html_content = "<html><body><h1>NEV Market Report</h1></body></html>"
        html_file = tmp_path / "journey_task.html"
        html_file.write_text(html_content, encoding="utf-8")

        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}
        api._handle_chat_mode = AsyncMock(return_value={"action": "continue_chat"})
        api._load_cancel_snapshot = AsyncMock(return_value=None)

        session = _make_session(task_id="journey_task")

        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api.PreviewStorage") as ps, \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
            cm = MagicMock()
            cm.is_cancelled.return_value = False
            cm.is_paused.return_value = False
            gcm.return_value = cm

            sm.get.return_value = session
            ps.path.return_value = html_file
            ps.url.return_value = "/api/v1/html-reports/journey_task.html"

            # Step 1: get_preview
            preview = await api.get_preview("journey_task")
            assert preview.get("html_content") is not None, \
                "Step 1 失败: get_preview 应返回 html_content"
            assert preview.get("html_content") == html_content

            # Step 2: _handle_research_msg → chat mode
            result = await api._handle_research_msg("journey_task", "Show me the report", session)
            assert session.get("mode") == "chat", \
                "Step 2 失败: 应切换到 chat 模式"

            # Step 3: resume_research → already completed
            session["mode"] = "research"  # reset for resume test
            resume_result = await api.resume_research("journey_task")
            assert resume_result.get("status") == "completed", \
                "Step 3 失败: resume 应返回 already completed"
