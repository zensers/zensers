# -*- coding: utf-8 -*-
"""
Test for regenerate_report bug: should regenerate HTML, not return "already completed"

Bug: When user clicks "重新生成HTML文档", the action 'regenerate_report' is routed to
resume_research(), which detects research is completed and returns immediately without
regenerating anything.

3 bug locations:
  1. research_api.py:366-367  (paused mode)
  2. research_api.py:538-540  (chat mode)
  3. research_api.py:344-347  (_handle_research_msg completed → chat → same bug)

Data format issue:
  - session['research_result'] has sections under 'report.sections'
  - research_result_cache.json has sections at top-level 'sections'
  - _document_agent expects top-level 'sections'
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime


SESSION_ID = "test_regen_001"


def _make_session():
    return {
        "session_id": SESSION_ID,
        "mode": "research",
        "status": "completed",
        "research_result": {
            "task_id": SESSION_ID,
            "status": "completed",
            "topic": "Test Topic",
            "report": {
                "sections": [
                    {"id": "s1", "title": "Section 1", "content": "Content 1"},
                    {"id": "s2", "title": "Section 2", "content": "Content 2"},
                ]
            },
            "summary": "Test summary",
        },
        "research_context": {
            "topic": "Test Topic",
            "framework": {"sections": ["Section 1", "Section 2"]},
        },
    }


def _make_cache_data():
    return {
        "task_id": SESSION_ID,
        "topic": "Test Topic",
        "title": "Test Topic",
        "aspects": ["Section 1", "Section 2"],
        "sections": [
            {"id": "s1", "title": "Section 1", "content": "Content 1"},
            {"id": "s2", "title": "Section 2", "content": "Content 2"},
        ],
        "sources": [],
        "key_findings": [],
    }


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


class TestResumeResearchBug:
    """Bug #1: resume_research() returns 'already completed' without regenerating HTML"""

    @pytest.mark.asyncio
    async def test_resume_research_returns_already_completed(self):
        """When research is completed, resume_research() does nothing."""
        from src.api.research_api import ResearchAPI

        _setup_session(_make_session())

        api = ResearchAPI.__new__(ResearchAPI)
        api._executor_tasks = {}

        result = await api.resume_research(SESSION_ID)

        assert result["status"] == "completed"
        assert "already completed" in result["message"].lower()

        _teardown_session()


class TestRegenerateReportRoutingBug:
    """Bug #2: 'regenerate_report' action was incorrectly routed to resume_research()

    After fix: these tests verify that regenerate_report now routes to
    _regenerate_report() instead of resume_research(), producing
    '文档已重新生成' instead of 'already completed'.
    """

    @pytest.mark.asyncio
    async def test_paused_mode_now_regenerates_report(self):
        """
        Fix verification: research_api.py:366

        In paused+completed mode, _handle_research_msg now routes
        'regenerate_report' to _regenerate_report() which regenerates HTML.
        """
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager

        session = _make_session()
        session["research_result"]["status"] = "completed"
        _setup_session(session)

        cm = get_cancel_manager()
        cm.pause(SESSION_ID)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(
            update_from_response=MagicMock()
        ))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"),
            can_transition_to=MagicMock(return_value=False),
        ))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "status": "completed",
            "message": "文档已重新生成"
        })

        try:
            result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", session)
        finally:
            cm.resume(SESSION_ID)
            _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_chat_mode_now_regenerates_report(self):
        """
        Fix verification: research_api.py:538-540

        In chat mode, _handle_chat_mode now routes 'regenerate_report'
        to _regenerate_report() which regenerates HTML.
        """
        session = _make_session()
        session["mode"] = "chat"
        _setup_session(session)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(
            update_from_response=MagicMock()
        ))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"),
            can_transition_to=MagicMock(return_value=False),
        ))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "status": "completed",
            "message": "文档已重新生成"
        })

        result = await api._handle_chat_mode(SESSION_ID, "重新生成HTML文档")

        _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_completed_research_in_research_mode_now_regenerates(self):
        """
        Fix verification: research_api.py:344-347

        When research is completed and user sends a message in research mode,
        _handle_research_msg switches to chat mode, and 'regenerate_report'
        now routes to _regenerate_report().
        """
        session = _make_session()
        session["mode"] = "research"
        _setup_session(session)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(
            update_from_response=MagicMock()
        ))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"),
            can_transition_to=MagicMock(return_value=False),
        ))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "status": "completed",
            "message": "文档已重新生成"
        })

        result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", session)

        _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]


class TestDataFormatMismatch:
    """Bug #3: session format vs cache format — sections location differs"""

    def test_session_format_has_sections_under_report(self):
        """session['research_result'] stores sections under report.sections"""
        session = _make_session()
        rr = session["research_result"]

        assert "sections" in rr["report"]
        assert len(rr["report"]["sections"]) == 2
        assert rr.get("sections") is None

    def test_cache_format_has_top_level_sections(self):
        """research_result_cache.json stores sections at top level"""
        cache = _make_cache_data()

        assert "sections" in cache
        assert len(cache["sections"]) == 2
        assert "report" not in cache

    def test_document_agent_expects_top_level_sections(self):
        """ContentOrchestrator.transform_to_html reads research_result.get('sections')"""
        session_format = _make_session()["research_result"]
        cache_format = _make_cache_data()

        session_sections = session_format.get("sections", [])
        cache_sections = cache_format.get("sections", [])

        assert session_sections == []
        assert len(cache_sections) == 2

    def test_session_data_needs_format_conversion(self):
        """
        To pass session['research_result'] to _document_agent, we must convert:
        report.sections → top-level sections
        """
        session = _make_session()
        rr = session["research_result"]

        converted = dict(rr)
        if "report" in converted and "sections" not in converted:
            report = converted.get("report", {})
            converted["sections"] = report.get("sections", [])
            converted["topic"] = converted.get("topic", report.get("topic", ""))
            converted["title"] = converted.get("topic", "")

        assert "sections" in converted
        assert len(converted["sections"]) == 2


class TestGenerateDocumentsFromCacheExistingMethod:
    """Verify _generate_documents_from_cache() works but is not called for regenerate"""

    @pytest.mark.asyncio
    async def test_method_exists_and_works(self, tmp_path):
        """_generate_documents_from_cache() exists and can regenerate documents"""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)

        mock_doc_agent_execute = AsyncMock(side_effect=[
            {"success": True, "document_path": str(tmp_path / "preview.html")},
            {"success": True, "document_path": str(tmp_path / "report.docx")},
        ])

        api._orchestrator = MagicMock()
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = mock_doc_agent_execute

        session = _make_session()
        cache_data = _make_cache_data()
        output_dir = tmp_path / SESSION_ID
        output_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.core.preview_storage.PreviewStorage.copy_file"):
            with patch("src.core.progress_streamer.update_progress"):
                with patch("src.core.progress_streamer.complete_task"):
                    await api._generate_documents_from_cache(
                        SESSION_ID, cache_data, output_dir, session
                    )

        assert mock_doc_agent_execute.call_count >= 1

        first_call = mock_doc_agent_execute.call_args_list[0][0][0]
        assert first_call["action"] == "produce_document"
        assert first_call["output_format"] == "html"
        assert "sections" in first_call["research_result"]
        assert len(first_call["research_result"]["sections"]) == 2


class TestRegenerateReportFixVerification:
    """Tests to verify the fix: _regenerate_report() method works correctly"""

    @pytest.mark.asyncio
    async def test_convert_session_to_cache_format_works(self):
        """_convert_session_to_cache_format() correctly extracts sections from report"""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        session_rr = _make_session()["research_result"]

        converted = api._convert_session_to_cache_format(session_rr)

        assert "sections" in converted
        assert len(converted["sections"]) == 2
        assert converted["sections"][0]["id"] == "s1"
        assert converted["topic"] == "Test Topic"
        assert converted["title"] == "Test Topic"

    @pytest.mark.asyncio
    async def test_regenerate_report_loads_cache_file(self, tmp_path):
        """_regenerate_report() loads research_result_cache.json when available"""
        from src.api.research_api import ResearchAPI

        cache_data = _make_cache_data()
        cache_dir = tmp_path / SESSION_ID
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "research_result_cache.json"
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")

        session = _make_session()
        _setup_session(session)

        api = _make_api()
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch.object(Path, "exists") as mock_exists:
            with patch.object(Path, "read_text") as mock_read:
                mock_exists.return_value = True
                mock_read.return_value = json.dumps(cache_data, ensure_ascii=False)

                result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]
        api._generate_documents_from_cache.assert_called_once()
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert "sections" in call_data
        assert len(call_data["sections"]) == 2

    @pytest.mark.asyncio
    async def test_regenerate_report_fallback_to_session_data(self, tmp_path):
        """_regenerate_report() converts session data when cache file missing"""
        from src.api.research_api import ResearchAPI

        session = _make_session()
        _setup_session(session)

        api = _make_api()
        api._generate_documents_from_cache = AsyncMock(return_value="")

        with patch("src.api.research_api.Path") as mock_path:
            mock_path.return_value.exists = MagicMock(return_value=False)

            result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert result["status"] == "completed"
        api._generate_documents_from_cache.assert_called_once()
        call_data = api._generate_documents_from_cache.call_args[0][1]
        assert "sections" in call_data
        assert len(call_data["sections"]) == 2

    @pytest.mark.asyncio
    async def test_paused_mode_now_calls_regenerate_report(self):
        """FIX: paused mode routes regenerate_report to _regenerate_report()"""
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager

        session = _make_session()
        session["research_result"]["status"] = "completed"
        _setup_session(session)

        cm = get_cancel_manager()
        cm.pause(SESSION_ID)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(
            update_from_response=MagicMock()
        ))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"),
            can_transition_to=MagicMock(return_value=False),
        ))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "status": "completed",
            "message": "文档已重新生成"
        })

        try:
            result = await api._handle_research_msg(SESSION_ID, "重新生成HTML", session)
        finally:
            cm.resume(SESSION_ID)
            _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_chat_mode_now_calls_regenerate_report(self):
        """FIX: chat mode routes regenerate_report to _regenerate_report()"""
        session = _make_session()
        session["mode"] = "chat"
        _setup_session(session)

        api = _make_api()
        api._get_or_create_intent_state = MagicMock(return_value=MagicMock(
            update_from_response=MagicMock()
        ))
        api._get_or_create_conv_machine = MagicMock(return_value=MagicMock(
            current_state=MagicMock(value="completed"),
            can_transition_to=MagicMock(return_value=False),
        ))
        api._save_dialogue_state = MagicMock()
        api._sync_mode_with_state = MagicMock()
        api._chat_response = MagicMock(return_value={"status": "ok"})
        api._llm_converse = AsyncMock(return_value={"action": "regenerate_report"})
        api._regenerate_report = AsyncMock(return_value={
            "status": "completed",
            "message": "文档已重新生成"
        })

        result = await api._handle_chat_mode(SESSION_ID, "重新生成HTML文档")

        _teardown_session()

        api._regenerate_report.assert_called_once_with(SESSION_ID)
        assert result["status"] == "completed"
        assert "文档已重新生成" in result["message"]

    @pytest.mark.asyncio
    async def test_no_completed_research_returns_error(self):
        """_regenerate_report() returns error when no completed research exists"""
        from src.api.research_api import ResearchAPI

        session = _make_session()
        session["research_result"]["status"] = "running"
        _setup_session(session)

        api = ResearchAPI.__new__(ResearchAPI)

        result = await api._regenerate_report(SESSION_ID)

        _teardown_session()

        assert "error" in result
        assert result["error_code"] == "NO_COMPLETED_RESEARCH"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
