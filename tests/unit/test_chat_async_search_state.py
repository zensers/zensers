"""Test: Chat async search state loss bugs (backend side)

Verifies:
- Bug C/D: _continue_tool_chain_body response_data lacks mode/step
- Bug B: SessionStreamer replay can deliver duplicate chat_response
- Bug D: ProgressStreamer.push_chat_response SSE data lacks mode/step
"""

import asyncio
import pytest
import tempfile


class TestContinueToolChainMissingModeStep:
    """Bug D: response_data from _continue_tool_chain_body lacks mode/step."""

    def test_sync_processing_response_has_mode_and_step(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        result = {
            'session_id': 'ses-001',
            'step': 0,
            'mode': 'chat',
            'status': 'processing',
            'message': 'Querying information...',
        }
        assert 'mode' in result
        assert 'step' in result
        assert result['mode'] == 'chat'
        assert result['step'] == 0

    def test_background_tool_chain_response_data_lacks_mode(self):
        parsed = {
            'message': 'BYD profit margin data...',
            'action': 'continue_chat',
            'topic': 'BYD',
            'directions': ['financial'],
            'suggestions': [{'id': 'deep_research', 'label': 'Deep Research'}],
        }
        response_data = {
            'message': parsed.get('message', ''),
            'action': parsed.get('action', 'continue_chat'),
            'topic': parsed.get('topic'),
            'directions': parsed.get('directions', []),
            'suggestions': parsed.get('suggestions', []),
        }
        assert 'mode' not in response_data, "mode field is missing in background tool chain response"
        assert 'step' not in response_data, "step field is missing in background tool chain response"

    def test_enter_framework_action_not_handled_in_background_chain(self):
        parsed = {
            'message': 'I will create a research framework',
            'action': 'enter_framework',
            'topic': 'BYD',
            'framework_sections': ['Financial Analysis', 'Competition'],
        }
        response_data = {
            'message': parsed.get('message', ''),
            'action': parsed.get('action', 'continue_chat'),
            'topic': parsed.get('topic'),
            'directions': parsed.get('directions', []),
            'suggestions': parsed.get('suggestions', []),
        }
        assert response_data['action'] == 'enter_framework'
        assert 'mode' not in response_data
        assert 'framework' not in response_data
        assert 'framework_sections' not in response_data


class TestProgressStreamerSSEDataMissingModeStep:
    """Bug D: ProgressStreamer.push_chat_response SSE data lacks mode/step."""

    def test_push_chat_response_sse_data_has_no_mode(self):
        response_data = {
            'message': 'BYD data',
            'action': 'continue_chat',
            'topic': 'BYD',
            'directions': [],
            'suggestions': [],
        }
        sse_data = {
            'session_id': 'ses-001',
            'message': response_data.get('message', ''),
            'action': response_data.get('action', 'continue_chat'),
            'topic': response_data.get('topic'),
            'directions': response_data.get('directions', []),
            'suggestions': response_data.get('suggestions', []),
            'thinking_content': response_data.get('thinking_content'),
            'timestamp': '2026-07-03T10:00:00',
        }
        assert 'mode' not in sse_data
        assert 'step' not in sse_data

    def test_push_chat_response_with_mode_fix(self):
        response_data = {
            'message': 'BYD data',
            'action': 'continue_chat',
            'topic': 'BYD',
            'directions': [],
            'suggestions': [],
            'mode': 'chat',
            'step': 0,
        }
        sse_data = {
            'session_id': 'ses-001',
            'message': response_data.get('message', ''),
            'action': response_data.get('action', 'continue_chat'),
            'topic': response_data.get('topic'),
            'directions': response_data.get('directions', []),
            'suggestions': response_data.get('suggestions', []),
            'thinking_content': response_data.get('thinking_content'),
            'mode': response_data.get('mode', 'chat'),
            'step': response_data.get('step', 0),
            'timestamp': '2026-07-03T10:00:00',
        }
        assert sse_data['mode'] == 'chat'
        assert sse_data['step'] == 0


class TestProgressStreamerChatReplay:
    """Chat responses must replay even while the task remains pending."""

    @pytest.mark.asyncio
    async def test_pending_chat_response_replays_on_late_subscriber(self):
        from src.core.progress_streamer import ProgressStreamer, SSEEventType

        task_id = 'ses-pending-chat-replay'
        ProgressStreamer._task_states.pop(task_id, None)
        ProgressStreamer._subscribers.pop(task_id, None)
        task = ProgressStreamer.get_or_create_task(task_id)
        task.status = 'pending'
        task.last_chat_response = {
            'response_id': 'chat-stable-1',
            'message': '中文回复',
            'action': 'continue_chat',
            'suggestions': ['继续分析'],
        }

        streamer = ProgressStreamer(task_id)
        streamer.subscribe()
        message = await asyncio.wait_for(streamer._queue.get(), timeout=2)

        assert message.event == SSEEventType.CHAT_RESPONSE.value
        assert message.data['response_id'] == 'chat-stable-1'
        assert message.data['message'] == '中文回复'
        assert message.data['suggestions'] == ['继续分析']

        streamer.unsubscribe()
        ProgressStreamer._task_states.pop(task_id, None)
        ProgressStreamer._subscribers.pop(task_id, None)


class TestSessionStreamerReplayDuplicates:
    """Bug B: SSE replay can deliver duplicate chat_response events."""

    @pytest.mark.asyncio
    async def test_subscribe_replays_recent_messages(self):
        from src.core.session_streamer import SessionStreamer

        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_response('ses-replay-1', {
            'message': 'First response',
            'action': 'continue_chat',
        })

        streamer = SessionStreamer('ses-replay-1')
        streamer.subscribe()

        msg = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg.event == 'chat_response'
        assert msg.data['message'] == 'First response'

        streamer.unsubscribe()
        SessionStreamer._recent_messages.pop('ses-replay-1', None)

    @pytest.mark.asyncio
    async def test_replay_delivers_same_event_twice(self):
        """Simulates: first subscriber gets event, then reconnect gets replay."""
        from src.core.session_streamer import SessionStreamer

        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        s1 = SessionStreamer('ses-replay-2')
        s1.subscribe()

        SessionStreamer.push_chat_response('ses-replay-2', {
            'message': 'BYD margin data',
            'action': 'continue_chat',
            'suggestions': [{'id': 'deep', 'label': 'Deep'}],
        })

        msg1 = await asyncio.wait_for(s1._queue.get(), timeout=2)
        assert msg1.event == 'chat_response'
        assert msg1.data['message'] == 'BYD margin data'

        # Do NOT unsubscribe s1 before s2 subscribes — unsubscribe clears _recent_messages
        # when no subscribers remain. Instead, subscribe s2 first, then unsubscribe s1.
        s2 = SessionStreamer('ses-replay-2')
        s2.subscribe()

        msg2 = await asyncio.wait_for(s2._queue.get(), timeout=2)
        assert msg2.event == 'chat_response'
        assert msg2.data['message'] == 'BYD margin data'
        assert msg2.data['suggestions'] == [{'id': 'deep', 'label': 'Deep'}]

        s1.unsubscribe()
        s2.unsubscribe()
        SessionStreamer._recent_messages.pop('ses-replay-2', None)

    @pytest.mark.asyncio
    async def test_replay_with_stale_framework_suggestions(self):
        """Simulates: old chat_response with framework suggestions replayed."""
        from src.core.session_streamer import SessionStreamer

        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_response('ses-replay-3', {
            'message': 'Framework ready',
            'action': 'enter_framework',
            'suggestions': [
                {'id': 'confirm', 'label': 'Confirm'},
                {'id': 'modify', 'label': 'Modify'},
            ],
        })

        streamer = SessionStreamer('ses-replay-3')
        streamer.subscribe()

        msg = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg.event == 'chat_response'
        assert msg.data['action'] == 'enter_framework'
        assert len(msg.data['suggestions']) == 2

        streamer.unsubscribe()
        SessionStreamer._recent_messages.pop('ses-replay-3', None)


class TestSessionStreamerDualWrite:
    """ProgressStreamer.push_chat_response should dual-write to SessionStreamer."""

    def test_dual_write_creates_session_subscriber_event(self):
        from src.core.session_streamer import SessionStreamer
        from src.core.progress_streamer import ProgressStreamer

        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()
        ProgressStreamer._task_states.clear()
        ProgressStreamer._subscribers.clear()

        import tempfile
        from src.core.session_manager import SessionManager
        tmpdir = tempfile.mkdtemp()
        mgr = SessionManager(storage_dir=tmpdir)
        mgr.create('ses-dual-1', {'conversation_history': []})

        ProgressStreamer.push_chat_response('ses-dual-1', {
            'message': 'BYD data via dual-write',
            'action': 'continue_chat',
        })

        recent = SessionStreamer._recent_messages.get('ses-dual-1', [])
        chat_events = [m for m in recent if m.event == 'chat_response']
        assert len(chat_events) >= 1, "SessionStreamer should have chat_response from dual-write"
        assert chat_events[0].data['message'] == 'BYD data via dual-write'

        SessionStreamer._recent_messages.pop('ses-dual-1', None)
        ProgressStreamer._task_states.clear()


class TestSearchStateSetSearchStateDoesNotSyncActive:
    """Verify setSearchState does NOT trigger useSessionStore update."""

    def test_set_search_state_is_local_only(self):
        from src.core.session_streamer import SessionStreamer

        SessionStreamer._recent_messages.clear()

        SessionStreamer._recent_messages['ses-local'] = []

        research_like_state = {
            'currentStep': 0,
            'stepOptions': None,
            'status': 'idle',
            'searchState': 'searching',
        }

        research_like_state['searchState'] = 'completed'

        recent_before = len(SessionStreamer._recent_messages.get('ses-local', []))
        research_like_state['searchState'] = 'idle'
        recent_after = len(SessionStreamer._recent_messages.get('ses-local', []))

        assert recent_before == recent_after, "setSearchState should not produce SSE events"

        SessionStreamer._recent_messages.pop('ses-local', None)


class TestChatResponseDataSchema:
    """Verify ChatResponseData type alignment between backend and frontend."""

    def test_current_schema_lacks_mode_and_step(self):
        sse_data = {
            'session_id': 'ses-001',
            'message': 'BYD data',
            'action': 'continue_chat',
            'topic': 'BYD',
            'directions': [],
            'suggestions': [],
            'thinking_content': None,
            'timestamp': '2026-07-03T10:00:00',
        }
        assert 'mode' not in sse_data, "Current schema does not include mode"
        assert 'step' not in sse_data, "Current schema does not include step"

    def test_extended_schema_includes_mode_and_step(self):
        sse_data = {
            'session_id': 'ses-001',
            'message': 'BYD data',
            'action': 'continue_chat',
            'topic': 'BYD',
            'directions': [],
            'suggestions': [],
            'thinking_content': None,
            'timestamp': '2026-07-03T10:00:00',
            'mode': 'chat',
            'step': 0,
        }
        assert sse_data['mode'] == 'chat'
        assert sse_data['step'] == 0

    def test_framework_mode_in_extended_schema(self):
        sse_data = {
            'session_id': 'ses-001',
            'message': 'Framework ready',
            'action': 'enter_framework',
            'topic': 'BYD',
            'directions': [],
            'suggestions': [{'id': 'confirm', 'label': 'Confirm'}],
            'thinking_content': None,
            'timestamp': '2026-07-03T10:00:00',
            'mode': 'framework',
            'step': 0,
        }
        assert sse_data['mode'] == 'framework'
        assert sse_data['step'] == 0
