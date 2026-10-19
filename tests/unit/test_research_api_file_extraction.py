import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.api.research_api import ResearchAPI
from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine


def _make_api():
    api = ResearchAPI.__new__(ResearchAPI)
    return api


class TestStartResearchWithFileIds:
    @pytest.mark.asyncio
    async def test_file_ids_triggers_extraction(self):
        api = _make_api()
        mock_session_manager = MagicMock()
        mock_session = {'research_context': {}, 'mode': 'chat'}
        mock_session_manager.get.return_value = mock_session
        mock_state_machine = ConversationStateMachine()

        mock_extraction = MagicMock()
        mock_extraction.title = "Test Report"
        mock_extraction.sections = []
        mock_extraction.tables = []
        mock_extraction.key_topics = ["market"]

        mock_adapter = MagicMock()
        mock_adapter.extract.return_value = mock_extraction
        mock_adapter_cls = MagicMock(return_value=mock_adapter)

        with patch('src.api.research_api.session_manager', mock_session_manager), \
             patch('src.api.research_api.ConversationStateMachine', return_value=mock_state_machine), \
             patch('src.api.research_api.detect_language') as mock_detect, \
             patch('src.api.research_api.set_global_language'), \
             patch('src.api.research_api.SmartClarifier'), \
             patch('src.core.adjustment.ppt_input_adapter.PptInputAdapter', return_value=mock_adapter):
            mock_detect.return_value = MagicMock(value='zh')

            file_ids = [{"id": "f1", "path": "/tmp/test.docx", "filename": "test.docx", "size_mb": 1.0}]
            result = await api.start_research("test", "user1", {}, file_ids)

            mock_adapter.extract.assert_called_once_with(["/tmp/test.docx"])
            assert mock_state_machine.current_state == ConversationState.DATA_EXTRACTED
            assert mock_session['research_context']['extraction_result'] is mock_extraction

    @pytest.mark.asyncio
    async def test_no_file_ids_normal_flow(self):
        api = _make_api()
        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = {'research_context': {}}
        mock_state_machine = ConversationStateMachine()

        with patch('src.api.research_api.session_manager', mock_session_manager), \
             patch('src.api.research_api.ConversationStateMachine', return_value=mock_state_machine), \
             patch('src.api.research_api.detect_language') as mock_detect, \
             patch('src.api.research_api.set_global_language'), \
             patch('src.api.research_api.SmartClarifier'), \
             patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
            mock_detect.return_value = MagicMock(value='zh')
            mock_handle.return_value = {"status": "ok"}

            result = await api.start_research("test", "user1", {})

            mock_handle.assert_called_once()
            assert mock_state_machine.current_state == ConversationState.UNDERSTANDING


class TestSyncModeWithNewStates:
    def test_data_extracted_sets_chat(self):
        api = _make_api()
        m = ConversationStateMachine()
        m.transition(ConversationState.DATA_EXTRACTED)
        session = {"mode": "research"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "chat"

    def test_requirement_confirm_sets_chat(self):
        api = _make_api()
        m = ConversationStateMachine()
        m.transition(ConversationState.DATA_EXTRACTED)
        m.transition(ConversationState.REQUIREMENT_CONFIRM)
        session = {"mode": "research"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "chat"

    def test_data_supplement_sets_chat(self):
        api = _make_api()
        m = ConversationStateMachine()
        m.transition(ConversationState.DATA_EXTRACTED)
        m.transition(ConversationState.REQUIREMENT_CONFIRM)
        m.transition(ConversationState.DATA_SUPPLEMENT)
        session = {"mode": "research"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "chat"


class TestResolveTransitionNewActions:
    def test_confirm_requirements_transitions_to_data_supplement(self):
        api = _make_api()
        result = api._resolve_transition("confirm_requirements")
        assert result == ConversationState.DATA_SUPPLEMENT

    def test_enter_ppt_generation_transitions_to_requirement_confirm(self):
        api = _make_api()
        result = api._resolve_transition("enter_ppt_generation")
        assert result == ConversationState.REQUIREMENT_CONFIRM


class TestBuildExtractionSummary:
    def test_builds_summary_from_extraction_result(self):
        api = _make_api()
        from src.core.adjustment.extraction_types import ExtractionResult, ExtractionSummary
        from src.content.content_orchestrator import ContentSection, SectionType

        extraction = ExtractionResult(
            title="Report",
            sections=[
                ContentSection(id="s0", title="Intro", content="Hello world", order=0, type=SectionType.BODY),
            ],
            tables=[[["A", "B"], ["1", "2"]]],
            key_topics=["market", "revenue"],
            metadata={"format": "docx"},
            summary=None,
        )
        file_ids = [{"id": "f1", "path": "/tmp/test.docx", "filename": "test.docx", "size_mb": 1.0}]
        result = api._build_extraction_summary(extraction, file_ids)

        assert isinstance(result, ExtractionSummary)
        assert result.file_count == 1
        assert result.title == "Report"
        assert result.tables_count == 1
        assert result.key_topics == ["market", "revenue"]
        assert result.extraction_status == "success"


class TestFormatExtractionSummaryMessage:
    def test_format_with_title_and_topics(self):
        api = _make_api()
        from src.core.adjustment.extraction_types import ExtractionSummary
        summary = ExtractionSummary(
            file_count=2, total_pages=10,
            format_types=["docx"], title="Annual Report",
            sections=[], tables_count=3, key_topics=["market", "revenue"],
        )
        msg = api._format_extraction_summary_message(summary)
        assert "Annual Report" in msg
        assert "market" in msg
        assert "您想基于这份材料做什么" in msg

    def test_format_without_title(self):
        api = _make_api()
        from src.core.adjustment.extraction_types import ExtractionSummary
        summary = ExtractionSummary(
            file_count=1, total_pages=5,
            format_types=["pdf"], title=None,
            sections=[], key_topics=[],
        )
        msg = api._format_extraction_summary_message(summary)
        assert "您的文档" in msg


class TestBuildDialogueContextNewStates:
    def test_data_extracted_has_guidance(self):
        api = _make_api()
        guidance = api._build_dialogue_context(ConversationState.DATA_EXTRACTED)
        assert "Data Extracted" in guidance
        assert "enter_ppt_generation" in guidance

    def test_requirement_confirm_has_guidance(self):
        api = _make_api()
        guidance = api._build_dialogue_context(ConversationState.REQUIREMENT_CONFIRM)
        assert "Requirement Confirmation" in guidance
        assert "confirm_requirements" in guidance

    def test_data_supplement_has_guidance(self):
        api = _make_api()
        guidance = api._build_dialogue_context(ConversationState.DATA_SUPPLEMENT)
        assert "Data Supplementation" in guidance
        assert "enter_framework" in guidance
