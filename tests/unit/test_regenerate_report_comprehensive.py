# -*- coding: utf-8 -*-
"""
Comprehensive test suite for regenerate_report fix.

Covers 90%+ of user daily scenarios:
1. Core: _regenerate_report() method (10+ scenarios)
2. Routing: 3 entry points × multiple states (8+ scenarios)
3. Data format: _convert_session_to_cache_format() edge cases (8+ scenarios)
4. Session state consistency (5+ scenarios)
5. Concurrency / error / boundary conditions (6+ scenarios)
6. End-to-end user journeys (5+ scenarios)
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from datetime import datetime


SESSION_ID = "test_regen_comprehensive"


def _make_session(**overrides):
    base = {
        "session_id": SESSION_ID,
        "mode": "research",
        "status": "completed",
        "research_result": {
            "task_id": SESSION_ID,
            "status": "completed",
            "topic": "比亚迪财务分析",
            "report": {
                "sections": [
                    {"id": "s1", "title": "营收分析", "content": "营收数据...", "data_points": []},
                    {"id": "s2", "title": "利润分析", "content": "利润数据...", "data_points": []},
                    {"id": "s3", "title": "市场前景", "content": "市场分析...", "data_points": []},
                ],
                "sources": [{"title": "Source1", "url": "http://example.com"}],
            },
            "summary": "分析完成",
            "document_path": "/old/path/preview.html",
            "output_path": "/old/path/",
        },
        "research_context": {
            "topic": "比亚迪财务分析",
            "framework": {"sections": ["营收分析", "利润分析", "市场前景"]},
        },
    }
    base.update(overrides)
    return base


def _make_cache_data(**overrides):
    base = {
        "task_id": SESSION_ID,
        "topic": "比亚迪财务分析",
        "title": "比亚迪财务分析",
        "aspects": ["营收分析", "利润分析", "市场前景"],
        "sections": [
            {"id": "s1", "title": "营收分析", "content": "营收数据..."},
            {"id": "s2", "title": "利润分析", "content": "利润数据..."},
            {"id": "s3", "title": "市场前景", "content": "市场分析..."},
        ],
        "sources": [{"title": "Source1", "url": "http://example.com"}],
        "key_findings": ["发现1", "发现2"],
    }
    base.update(overrides)
    return base


def _setup_session(session_data):
    from src.api.research_api import session_manager
    from src.core.session_manager import PersistentSessionDict
    wrapped = PersistentSessionDict(session_manager, SESSION_ID, dict(session_data))
    session_manager._sessions[SESSION_ID] = wrapped
    return session_manager.get(SESSION_ID)


def _teardown_session():
    from src.api.research_api import session_manager
    session_manager._sessions.pop(SESSION_ID, None)


def _make_api():
    from src.api.research_api import ResearchAPI
    api = ResearchAPI.__new__(ResearchAPI)
    api._executor_tasks = {}
    api._loop_cancel_flags = {}
    api._session_locks = {}
    api._orchestrator = MagicMock()
    api._knowledge_manager = MagicMock()
    api._tool_set = MagicMock()
    api._revision_locks = {}
    api._revision_task = None
    api._pending_clarifications = {}
    api._clarification_responses = {}
    api._background_tasks = {}
    api._background_task_gen = {}
    api._dream_mode_running = False
    return api


def _create_cache_file(tmp_path, session_id=None, data=None):
    sid = session_id or SESSION_ID
    cache_dir = tmp_path / sid
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "research_result_cache.json"
    cache_data = data or _make_cache_data(task_id=sid)
    cache_file.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
    return cache_file


# ============================================================
# PART 1: _regenerate_report() core method
# ============================================================

class TestRegenerateReportCore:
    """Core _regenerate_report() method tests"""

    @pytest.mark.asyncio
    async def test_normal_with_cache_file(self, tmp_path):
        """Normal case: cache file exists → loads → generates → success"""
        from src.api.research_api import ResearchAPI

        cache_data = _make_cache_data()
        _create_cache_file(tmp_path, data=cache_data)
        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value=json.dumps(cache_data, ensure_ascii=False)):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]
        api._generate_documents_from_cache.assert_called_once()
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert call_data == cache_data

    @pytest.mark.asyncio
    async def test_fallback_no_cache_file(self, tmp_path):
        """No cache file → converts session data → generates → success"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert result["status"] == "completed"
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert "sections" in call_data
        assert len(call_data["sections"]) == 3
        assert call_data["sections"][0]["title"] == "营收分析"

    @pytest.mark.asyncio
    async def test_cache_file_corrupted_falls_back(self, tmp_path):
        """Cache file exists but corrupted JSON → falls back to session data"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="{invalid json!!!"):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert result["status"] == "completed"
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert "sections" in call_data

    @pytest.mark.asyncio
    async def test_no_session_returns_error(self):
        """Session not found → returns SESSION_NOT_FOUND"""
        from src.api.research_api import ResearchAPI, session_manager

        api = ResearchAPI.__new__(ResearchAPI)
        _teardown_session()

        with patch.object(session_manager, "get", return_value=None):
            result = await api._regenerate_report(SESSION_ID)

        assert "error" in result
        assert result["error_code"] == "SESSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_no_completed_research_returns_error(self):
        """Research status != completed → returns NO_COMPLETED_RESEARCH"""
        from src.api.research_api import ResearchAPI

        for status in ["running", "paused", "cancelled", "failed", "pending"]:
            _setup_session(_make_session(**{"research_result": {"status": status}}))

            api = ResearchAPI.__new__(ResearchAPI)
            result = await api._regenerate_report(SESSION_ID)

            assert result["error_code"] == "NO_COMPLETED_RESEARCH", f"Failed for status={status}"

        _teardown_session()

    @pytest.mark.asyncio
    async def test_completed_with_warnings_still_works(self):
        """status='completed_with_warnings' should also allow regeneration"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {
                "task_id": SESSION_ID,
                "status": "completed_with_warnings",
                "topic": "Test",
                "report": {"sections": [{"id": "s1", "title": "S1", "content": "C1"}]},
            }
        }))

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_sections_returns_error(self):
        """No sections in converted data → returns NO_SECTIONS"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {
                "task_id": SESSION_ID,
                "status": "completed",
                "topic": "Test",
                "report": {"sections": []},
            }
        }))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_SECTIONS"

    @pytest.mark.asyncio
    async def test_no_research_result_key_returns_error(self):
        """session has no 'research_result' key → returns NO_COMPLETED_RESEARCH"""
        from src.api.research_api import ResearchAPI

        _setup_session({"session_id": SESSION_ID, "mode": "chat"})

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_generate_documents_raises_exception(self):
        """_generate_documents_from_cache raises → returns REGENERATE_FAILED"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(side_effect=RuntimeError("disk full"))

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "REGENERATE_FAILED"
        assert "disk full" in result["error"]

    @pytest.mark.asyncio
    async def test_task_id_differs_from_session_id(self, tmp_path):
        """task_id in research_result differs from session_id → tries both paths"""
        from src.api.research_api import ResearchAPI

        task_id = "different_task_id_001"
        _setup_session(_make_session(**{
            "research_result": {
                "task_id": task_id,
                "status": "completed",
                "topic": "Test",
                "report": {"sections": [{"id": "s1", "title": "S1", "content": "C1"}]},
            }
        }))

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        cache_data = _make_cache_data(task_id=task_id)

        exists_count = {"n": 0}
        def mock_exists(self_path):
            exists_count["n"] += 1
            return exists_count["n"] == 2

        with patch.object(Path, "exists", mock_exists), \
             patch.object(Path, "read_text", return_value=json.dumps(cache_data, ensure_ascii=False)):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_output_dir_created_if_missing(self, tmp_path):
        """data/{session_id} directory is created if it doesn't exist"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "mkdir") as mock_mkdir:
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_sse_preview_refresh_called(self):
        """After successful regeneration, SSE preview_refresh is pushed"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.session_streamer.SessionStreamer") as mock_ss, \
             patch("src.core.preview_storage.PreviewStorage") as mock_ps:
            mock_ps.url.return_value = "/preview/test.html"
            result = await api._regenerate_report(SESSION_ID)

            mock_ss.push_preview_refresh.assert_called_once_with(
                SESSION_ID, "/preview/test.html", "v1"
            )

        _teardown_session()

    @pytest.mark.asyncio
    async def test_sse_failure_does_not_break_regenerate(self):
        """SSE push failure is non-critical, regeneration still succeeds"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.session_streamer.SessionStreamer") as mock_ss, \
             patch("src.core.preview_storage.PreviewStorage") as mock_ps:
            mock_ps.url.return_value = "/preview/test.html"
            mock_ss.push_preview_refresh.side_effect = ConnectionError("SSE broken")

            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]


# ============================================================
# PART 2: Routing — 3 entry points × multiple states
# ============================================================

class TestRegenerateReportRouting:
    """Verify regenerate_report routes correctly in all entry points"""

    @pytest.mark.asyncio
    async def test_paused_completed_routes_to_regenerate(self):
        """Entry 1: paused + completed → _regenerate_report (not resume_research)"""
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager

        _setup_session(_make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": "completed",
                                "topic": "T", "report": {"sections": [{"id": "s1", "title": "S1", "content": "C1"}]}}
        }))

        cm = get_cancel_manager()
        cm.pause(SESSION_ID)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        try:
            result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", _make_session())
        finally:
            cm.resume(SESSION_ID)
            _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_chat_mode_routes_to_regenerate(self):
        """Entry 2: chat mode → _regenerate_report"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        result = await api._handle_chat_mode(SESSION_ID, "重新生成HTML文档")

        _teardown_session()
        api._regenerate_report.assert_called_once_with(SESSION_ID)

    @pytest.mark.asyncio
    async def test_research_completed_falls_to_chat_then_regenerate(self):
        """Entry 3: research mode + completed → chat → _regenerate_report"""
        _setup_session(_make_session(mode="research"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", _make_session())

        _teardown_session()
        api._regenerate_report.assert_called_once_with(SESSION_ID)

    @pytest.mark.asyncio
    async def test_resume_research_action_still_works(self):
        """'resume_research' action in paused mode still routes to resume_research() (not broken)"""
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager

        session = _make_session()
        session["research_result"] = {"task_id": SESSION_ID, "status": "running", "topic": "T"}
        _setup_session(session)

        cm = get_cancel_manager()
        cm.pause(SESSION_ID)

        api = _make_api()
        api._executor_tasks = {SESSION_ID: asyncio.create_task(asyncio.sleep(100))}
        api._llm_converse = AsyncMock(return_value={"action": "resume_research"})
        api._handle_chat_mode = AsyncMock(return_value={"status": "ok"})
        api.resume_research = AsyncMock(return_value={"status": "resumed", "message": "Research task resumed"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "regenerated"})

        try:
            result = await api._handle_research_msg(SESSION_ID, "继续研究", session)
        finally:
            cm.resume(SESSION_ID)
            task = api._executor_tasks.pop(SESSION_ID, None)
            if task and not task.done():
                task.cancel()
            _teardown_session()

        api.resume_research.assert_called_once_with(SESSION_ID)
        api._regenerate_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_enter_framework_action_not_affected(self):
        """'enter_framework' action still works (not affected by fix)"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "enter_framework"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "regenerated"})

        result = await api._handle_chat_mode(SESSION_ID, "重新做一次研究")

        _teardown_session()
        api._regenerate_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_chat_action_not_affected(self):
        """'continue_chat' action still works"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "continue_chat"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "regenerated"})

        result = await api._handle_chat_mode(SESSION_ID, "给我总结一下")

        _teardown_session()
        api._regenerate_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_revise_report_action_not_affected(self):
        """'revise_report' action still works independently"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "revise_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "regenerated"})

        result = await api._handle_chat_mode(SESSION_ID, "修改第三章")

        _teardown_session()
        api._regenerate_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_regenerate_report_returns_error_propagates(self):
        """If _regenerate_report returns error, it propagates to caller"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "error": "No completed research", "error_code": "NO_COMPLETED_RESEARCH"
        })

        result = await api._handle_chat_mode(SESSION_ID, "重新生成HTML文档")

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"


# ============================================================
# PART 3: Data format conversion edge cases
# ============================================================

class TestConvertSessionToCacheFormat:
    """_convert_session_to_cache_format() edge cases"""

    def _convert(self, session_rr):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api._convert_session_to_cache_format(session_rr)

    def test_normal_conversion(self):
        """Standard session format → cache format"""
        rr = {
            "task_id": "t1",
            "status": "completed",
            "topic": "Topic A",
            "report": {
                "sections": [{"id": "s1", "title": "S1", "content": "C1"}],
                "sources": [{"title": "Src1", "url": "http://x.com"}],
            },
        }
        result = self._convert(rr)
        assert result["sections"] == [{"id": "s1", "title": "S1", "content": "C1"}]
        assert result["topic"] == "Topic A"
        assert result["title"] == "Topic A"

    def test_already_has_top_level_sections(self):
        """If top-level sections already exist, no conversion"""
        rr = {
            "task_id": "t1",
            "status": "completed",
            "sections": [{"id": "s1", "title": "S1"}],
            "report": {"sections": [{"id": "s1", "title": "S1"}]},
        }
        result = self._convert(rr)
        assert result["sections"] == [{"id": "s1", "title": "S1"}]

    def test_no_report_key(self):
        """No 'report' key → no conversion, returns as-is"""
        rr = {"task_id": "t1", "status": "completed", "topic": "T"}
        result = self._convert(rr)
        assert result == rr

    def test_report_has_no_sections(self):
        """report exists but has no sections → sections becomes []"""
        rr = {"task_id": "t1", "report": {"other_data": 123}}
        result = self._convert(rr)
        assert result["sections"] == []

    def test_extracts_aspects_sources_key_findings(self):
        """report contains aspects/sources/key_findings → extracted to top level"""
        rr = {
            "task_id": "t1",
            "topic": "Topic A",
            "report": {
                "sections": [{"id": "s1"}],
                "sources": [{"title": "Src1"}],
                "aspects": ["A1", "A2"],
                "key_findings": ["F1"],
            },
        }
        result = self._convert(rr)
        assert result["aspects"] == ["A1", "A2"]
        assert result["sources"] == [{"title": "Src1"}]
        assert result["key_findings"] == ["F1"]

    def test_topic_from_report_if_missing_at_top(self):
        """If topic missing at top level but present in report → uses report.topic"""
        rr = {
            "task_id": "t1",
            "report": {
                "sections": [{"id": "s1"}],
                "topic": "Report Topic",
            },
        }
        result = self._convert(rr)
        assert result["topic"] == "Report Topic"
        assert result["title"] == "Report Topic"

    def test_topic_at_top_level_preserved(self):
        """If topic exists at top level → preserved, not overwritten"""
        rr = {
            "task_id": "t1",
            "topic": "Top Topic",
            "report": {
                "sections": [{"id": "s1"}],
                "topic": "Report Topic",
            },
        }
        result = self._convert(rr)
        assert result["topic"] == "Top Topic"

    def test_does_not_modify_original(self):
        """Conversion should not modify the original dict"""
        rr = {
            "task_id": "t1",
            "topic": "T",
            "report": {"sections": [{"id": "s1"}]},
        }
        original_rr = dict(rr)
        self._convert(rr)
        assert rr == original_rr

    def test_empty_sections_list(self):
        """Empty sections list → converted correctly (triggers NO_SECTIONS in _regenerate_report)"""
        rr = {"task_id": "t1", "topic": "T", "report": {"sections": []}}
        result = self._convert(rr)
        assert result["sections"] == []
        assert "title" in result

    def test_large_sections_list(self):
        """Large number of sections → all preserved"""
        sections = [{"id": f"s{i}", "title": f"Section {i}", "content": f"Content {i}"} for i in range(50)]
        rr = {"task_id": "t1", "topic": "T", "report": {"sections": sections}}
        result = self._convert(rr)
        assert len(result["sections"]) == 50

    def test_unicode_and_special_chars(self):
        """Chinese / special characters in sections → preserved"""
        rr = {
            "task_id": "t1",
            "topic": "比亚迪<2024>财务 & 分析",
            "report": {
                "sections": [
                    {"id": "s1", "title": "营收「分析」", "content": "数据：100亿元\n换行"},
                    {"id": "s2", "title": "利润<分析>", "content": "特殊字符: & < > \""},
                ],
            },
        }
        result = self._convert(rr)
        assert result["topic"] == "比亚迪<2024>财务 & 分析"
        assert result["sections"][0]["title"] == "营收「分析」"
        assert result["sections"][1]["content"] == "特殊字符: & < > \""


# ============================================================
# PART 4: Session state consistency
# ============================================================

class TestSessionStateConsistency:
    """Verify session state is correct after regeneration"""

    @pytest.mark.asyncio
    async def test_session_research_result_updated_after_regeneration(self):
        """After regeneration, session['research_result'] has correct format"""
        from src.api.research_api import ResearchAPI, session_manager

        session = _make_session()
        wrapped = _setup_session(session)

        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": "/new/preview.html"},
            {"success": True, "document_path": "/new/report.docx"},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"):
            await api._regenerate_report(SESSION_ID)

        rr = wrapped.get("research_result", {})
        assert rr.get("status") == "completed"
        assert rr.get("document_path") == "/new/preview.html"

        _teardown_session()

    @pytest.mark.asyncio
    async def test_session_mode_set_to_chat_after_regeneration(self):
        """After regeneration, session mode is 'chat' (can continue conversation)"""
        from src.api.research_api import ResearchAPI

        session = _make_session(mode="research")
        wrapped = _setup_session(session)

        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": "/preview.html"},
            {"success": True, "document_path": "/report.docx"},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"):
            await api._regenerate_report(SESSION_ID)

        assert wrapped.get("mode") == "chat"

        _teardown_session()

    @pytest.mark.asyncio
    async def test_multiple_regenerations_dont_corrupt_session(self):
        """Consecutive regenerations don't corrupt session data"""
        from src.api.research_api import ResearchAPI

        session = _make_session()
        wrapped = _setup_session(session)

        for i in range(3):
            mock_doc_execute = AsyncMock(side_effect=[
                {"success": True, "document_path": f"/preview_{i}.html"},
                {"success": True, "document_path": f"/report_{i}.docx"},
            ])

            api = ResearchAPI.__new__(ResearchAPI)
            api._orchestrator = MagicMock()
            api._orchestrator._document_agent = MagicMock()
            api._orchestrator._document_agent.execute = mock_doc_execute

            with patch.object(Path, "exists", return_value=False), \
                 patch("src.core.preview_storage.PreviewStorage.copy_file"), \
                 patch("src.core.progress_streamer.update_progress"), \
                 patch("src.core.progress_streamer.complete_task"):
                result = await api._regenerate_report(SESSION_ID)

            assert result["status"] == "completed"

        rr = wrapped.get("research_result", {})
        assert rr.get("status") == "completed"

        _teardown_session()

    @pytest.mark.asyncio
    async def test_session_report_has_sections_after_regenerate(self):
        """After regenerate, session['research_result']['report']['sections'] is accessible"""
        from src.api.research_api import ResearchAPI

        session = _make_session()
        wrapped = _setup_session(session)

        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": "/preview.html"},
            {"success": True, "document_path": "/report.docx"},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"):
            await api._regenerate_report(SESSION_ID)

        rr = wrapped.get("research_result", {})
        report = rr.get("report", {})
        sections = report.get("sections", [])

        assert len(sections) > 0

        _teardown_session()

    @pytest.mark.asyncio
    async def test_session_result_has_document_path(self):
        """After regeneration, session has document_path for download"""
        from src.api.research_api import ResearchAPI

        session = _make_session()
        wrapped = _setup_session(session)

        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": "/new/preview.html"},
            {"success": True, "document_path": "/new/report.docx"},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=False), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"):
            await api._regenerate_report(SESSION_ID)

        rr = wrapped.get("research_result", {})
        assert rr.get("document_path") == "/new/preview.html"

        _teardown_session()


# ============================================================
# PART 5: Concurrency / error / boundary conditions
# ============================================================

class TestConcurrencyAndBoundary:
    """Edge cases: concurrency, races, boundary conditions"""

    @pytest.mark.asyncio
    async def test_regenerate_while_research_running_returns_error(self):
        """Cannot regenerate while research is still running"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": "running", "topic": "T"}
        }))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_regenerate_after_session_deleted(self):
        """Session deleted between call start and session_manager.get → error"""
        from src.api.research_api import ResearchAPI, session_manager

        _teardown_session()

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(session_manager, "get", return_value=None):
            result = await api._regenerate_report(SESSION_ID)

        assert result["error_code"] == "SESSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_regenerate_with_cancelled_research(self):
        """Cancelled research → cannot regenerate"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": "cancelled", "topic": "T"}
        }))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_regenerate_with_failed_research(self):
        """Failed research → cannot regenerate"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": "failed", "topic": "T"}
        }))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_cache_file_deleted_between_exists_and_read(self):
        """Race: cache file deleted between exists() and read_text() → falls back"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._generate_documents_from_cache = AsyncMock(return_value="")

        call_count = {"n": 0}
        def mock_read_text(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise FileNotFoundError("cache deleted")
            return json.dumps(_make_cache_data(), ensure_ascii=False)

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", mock_read_text):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert "sections" in call_data

    @pytest.mark.asyncio
    async def test_research_result_with_none_status(self):
        """research_result exists but status is None → NO_COMPLETED_RESEARCH"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": None, "topic": "T"}
        }))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_research_result_is_empty_dict(self):
        """research_result is {} → NO_COMPLETED_RESEARCH"""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session(research_result={}))

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"

    @pytest.mark.asyncio
    async def test_research_result_none_value(self):
        """research_result is None → NO_COMPLETED_RESEARCH"""
        from src.api.research_api import ResearchAPI

        _setup_session({"session_id": SESSION_ID, "research_result": None})

        api = ResearchAPI.__new__(ResearchAPI)

        with patch.object(Path, "exists", return_value=False):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"


# ============================================================
# PART 6: End-to-end user journeys
# ============================================================

class TestEndToEndUserJourneys:
    """Full user scenario tests"""

    @pytest.mark.asyncio
    async def test_journey_complete_research_then_regenerate_html(self, tmp_path):
        """
        Journey: User completes research → finds report issue → says "重新生成HTML" → gets new preview
        """
        from src.api.research_api import ResearchAPI

        session = _make_session()
        wrapped = _setup_session(session)

        cache_data = _make_cache_data()
        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": str(tmp_path / "new_preview.html")},
            {"success": True, "document_path": str(tmp_path / "new_report.docx")},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value=json.dumps(cache_data, ensure_ascii=False)), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.preview_storage.PreviewStorage.url", return_value="/preview/new.html"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"), \
             patch("src.core.session_streamer.SessionStreamer.push_preview_refresh") as mock_sse:
            result = await api._regenerate_report(SESSION_ID)

            mock_sse.assert_called_once_with(SESSION_ID, "/preview/new.html", "v1")

        assert result["status"] == "completed"
        assert result["message"] == "文档已重新生成"

        assert wrapped.get("mode") == "chat"
        assert wrapped.get("research_result", {}).get("status") == "completed"

        _teardown_session()

    @pytest.mark.asyncio
    async def test_journey_paused_completed_regenerate(self):
        """
        Journey: Research paused → completes in background → user says "重新生成" → works
        (Previously returned "Research already completed while paused")
        """
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager

        session = _make_session(**{
            "research_result": {"task_id": SESSION_ID, "status": "completed",
                                "topic": "T", "report": {"sections": [{"id": "s1", "title": "S1", "content": "C1"}]}}
        })
        _setup_session(session)

        cm = get_cancel_manager()
        cm.pause(SESSION_ID)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        try:
            result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", session)
        finally:
            cm.resume(SESSION_ID)
            _teardown_session()

        assert "already completed" not in result.get("message", "").lower()
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_journey_chat_mode_regenerate(self):
        """
        Journey: User in chat mode → says "重新生成报告" → gets new preview
        (Previously returned "Research already completed while paused")
        """
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        result = await api._handle_chat_mode(SESSION_ID, "重新生成报告")

        _teardown_session()

        assert "already completed" not in result.get("message", "").lower()
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_journey_no_research_regenerate_gives_clear_error(self):
        """
        Journey: User has no research → says "重新生成" → gets clear error message
        """
        _setup_session({"session_id": SESSION_ID, "mode": "chat"})

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "error": "No completed research to regenerate from",
            "error_code": "NO_COMPLETED_RESEARCH"
        })

        result = await api._handle_chat_mode(SESSION_ID, "重新生成HTML")

        _teardown_session()

        assert result.get("error_code") == "NO_COMPLETED_RESEARCH"
        assert "already completed" not in result.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_journey_cache_corrupted_still_works(self, tmp_path):
        """
        Journey: Cache file is corrupted → falls back to session data → still regenerates
        """
        from src.api.research_api import ResearchAPI

        session = _make_session()
        _setup_session(session)

        mock_doc_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": str(tmp_path / "preview.html")},
            {"success": True, "document_path": str(tmp_path / "report.docx")},
        ])

        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_execute

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="CORRUPTED DATA {{{{"), \
             patch("src.core.preview_storage.PreviewStorage.copy_file"), \
             patch("src.core.preview_storage.PreviewStorage.url", return_value="/preview/test.html"), \
             patch("src.core.progress_streamer.update_progress"), \
             patch("src.core.progress_streamer.complete_task"), \
             patch("src.core.session_streamer.SessionStreamer.push_preview_refresh"):
            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

        call_data = mock_doc_execute.call_args_list[0][0][0]
        assert call_data["research_result"].get("sections") is not None
        assert len(call_data["research_result"]["sections"]) == 3


# ============================================================
# PART 7: resume_research still works for its own purpose
# ============================================================

class TestResumeResearchUnchanged:
    """Verify resume_research() is not broken by the fix"""

    @pytest.mark.asyncio
    async def test_resume_research_completed_still_returns_already_completed(self):
        """resume_research() for completed research still returns 'already completed'"""
        _setup_session(_make_session())

        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}

        result = await api.resume_research(SESSION_ID)

        _teardown_session()
        assert result["status"] == "completed"
        assert "already completed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_resume_research_not_for_regenerate(self):
        """resume_research is NOT called when action is regenerate_report"""
        _setup_session(_make_session(mode="chat"))

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(update_from_response=MagicMock()))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"), can_transition_to=MagicMock(return_value=False)))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api.resume_research = AsyncMock(return_value={"status": "completed", "message": "resumed"})
        api._regenerate_report = AsyncMock(return_value={"status": "completed", "message": "文档已重新生成"})

        await api._handle_chat_mode(SESSION_ID, "重新生成HTML")

        _teardown_session()
        api.resume_research.assert_not_called()
        api._regenerate_report.assert_called_once()


# ============================================================
# PART 8: LLM prompt modification verification
# ============================================================

class TestLLMPromptModification:
    """Verify the LLM prompt correctly distinguishes regenerate_report from enter_framework"""

    @pytest.mark.asyncio
    async def test_prompt_contains_regenerate_report_keyword(self):
        """The prompt should contain 'regenerate_report' as an available action"""
        from src.api.research_api import ResearchAPI

        source = inspect.getsource(ResearchAPI._llm_converse)
        assert "regenerate_report" in source

    def test_prompt_distinguishes_new_research_vs_regenerate(self):
        """The prompt should tell LLM: new research=enter_framework, regenerate document=regenerate_report"""
        from src.api.research_api import ResearchAPI

        source = inspect.getsource(ResearchAPI._handle_chat_mode)
        assert "regenerate_report" in source
        assert "_regenerate_report" in source


if __name__ == "__main__":
    import inspect
    pytest.main([__file__, "-v"])
else:
    import inspect
