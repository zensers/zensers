"""Test: _llm_converse() streaming branch integration.

After the retry-engine consolidation (spec §8 #6-#8) the conversation loop
calls ``call_llm_ex`` (engine-backed); the mock seam mirrors its real
contract: ``on_token`` receives raw chunks, the return value is the
parse-hook output (a parsed dict, or a raw string on the legacy escape
hatch).
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass


def _engine_ex(payload, raw_tokens=None):
    """Fake call_llm_ex: replay raw tokens through on_token, return payload."""
    async def _fake(prompt_builder, **kwargs):
        on_token = kwargs.get("on_token")
        if on_token and raw_tokens:
            for token in raw_tokens:
                on_token(token)
        return payload
    return _fake


@pytest.fixture
def mock_deps():
    deps = {}
    sm = MagicMock()
    sm.get.return_value = {
        "research_context": {},
        "conversation_history": [],
        "llm_config": {},
    }
    deps["session_manager"] = sm

    ms = MagicMock()
    ms.llm.max_tokens = 4096
    ms.llm.temperature = 0.7
    ms.llm.model = "test-model"
    ms.llm.cheap_model = "test-fallback"
    ms.llm.cost_limit_per_report = 0
    ms.llm.api_key = "test-key"
    ms.llm.base_url = "https://test.example.com"
    ms.llm.top_p = 1.0
    ms.llm.frequency_penalty = 0.0
    ms.llm.presence_penalty = 0.0
    deps["settings"] = ms

    pm = MagicMock()
    profile = MagicMock()
    profile.get_full_prompt.return_value = "You are a helpful assistant."
    pm.load_profile.return_value = profile
    deps["prompt_manager"] = pm
    deps["pm_instance"] = MagicMock()
    deps["pm_instance"].load_profile.return_value = profile

    deps["SessionStreamer"] = MagicMock()
    ts = MagicMock()
    ts.TOOL_DEFINITIONS = []
    deps["tool_set"] = ts
    return deps


class TestLlmConverseStreamingBranch:
    def test_imports_engine_entrypoints(self):
        from src.api.research_api import _ThinkTagFilter, _llm_call_with_engine_retry
        from src.core.llm_client import call_llm_ex, call_llm
        assert callable(call_llm_ex)
        assert callable(call_llm)
        assert callable(_ThinkTagFilter)
        assert callable(_llm_call_with_engine_retry)

    @pytest.mark.asyncio
    async def test_stream_first_iteration_calls_stream_api(self, mock_deps):
        deps = mock_deps

        mock_call_llm_ex = AsyncMock(return_value={
            "message": "Hello", "action": "continue_chat", "tool_call": None})

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", mock_call_llm_ex):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock) as mock_call_llm:
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")

                                mock_call_llm_ex.assert_awaited_once()
                                assert mock_call_llm_ex.await_args.kwargs.get("stream") is True
                                mock_call_llm.assert_not_called()
                                assert result["status"] == "done"
                                assert result["message"] == "Hello"

    @pytest.mark.asyncio
    async def test_stream_routing_thinking_tokens(self, mock_deps):
        """Raw think-tagged chunks replayed via on_token must route thinking
        content to push_chat_thinking and the rest to push_chat_token."""
        deps = mock_deps
        mock_streamer = MagicMock()
        deps["SessionStreamer"] = mock_streamer

        from src.api.research_api import _THINK_OPEN, _THINK_CLOSE
        raw = _THINK_OPEN + "thinking" + _THINK_CLOSE + '{"message": "Hi", "action": "continue_chat", "tool_call": null}'
        payload = {"message": "Hi", "action": "continue_chat", "tool_call": None}

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", mock_streamer):
                    with patch("src.api.research_api.call_llm_ex",
                               new=_engine_ex(payload, raw_tokens=[raw])):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")

                                mock_streamer.push_chat_thinking.assert_called()
                                mock_streamer.push_chat_token.assert_called()

    @pytest.mark.asyncio
    async def test_stream_failure_exhaustion_returns_terminal_fallback(self, mock_deps):
        """Total engine exhaustion (all candidates/budget spent) must yield
        the terminal continue_chat response instead of crashing."""
        deps = mock_deps

        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.TRANSPORT), 3, 12.0)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex",
                               AsyncMock(side_effect=exhausted)):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")
                                assert result["action"] == "continue_chat"
                                assert "重新描述" in result["message"]

    @pytest.mark.asyncio
    async def test_empty_stream_falls_back_before_intent_parse(self, mock_deps):
        """A cleanly-closed empty stream must not become an empty intent.

        The engine absorbs the empty stream internally (BAD_JSON_FORMAT
        ladder); the mock emulates a recovered engine returning the parsed
        payload."""
        deps = mock_deps

        payload = {"message": "fallback", "action": "continue_chat", "tool_call": None}
        mock_call_llm_ex = AsyncMock(return_value=payload)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", mock_call_llm_ex):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")

                                assert result["message"] == "fallback"
                                assert mock_call_llm_ex.await_count == 1

    @pytest.mark.asyncio
    async def test_engine_failure_not_retried_externally(self, mock_deps):
        """An exhausted engine call must not be re-driven by the outer
        handler — exactly one engine invocation happens."""
        deps = mock_deps

        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.EMPTY_CONTENT), 3, 8.0)
        mock_call_llm_ex = AsyncMock(side_effect=exhausted)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", mock_call_llm_ex):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")

                                assert result["action"] == "continue_chat"
                                assert mock_call_llm_ex.await_count == 1

    @pytest.mark.asyncio
    async def test_push_chat_token_not_called_on_degraded_path(self, mock_deps):
        deps = mock_deps
        mock_streamer = MagicMock()
        deps["SessionStreamer"] = mock_streamer

        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.TRANSPORT), 3, 12.0)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", mock_streamer):
                    with patch("src.api.research_api.call_llm_ex",
                               AsyncMock(side_effect=exhausted)):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                await api._llm_converse("test_ses", "hello")
                                mock_streamer.push_chat_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_llm_response_is_reported_without_none_type_error(self, mock_deps):
        """A None result from the engine seam must not be converted into
        result.get() — the terminal response is returned instead."""
        deps = mock_deps

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex",
                               AsyncMock(return_value=None)):
                        with patch("src.api.research_api.call_llm", new_callable=AsyncMock):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await api._llm_converse("test_ses", "hello")

                                assert result["action"] == "continue_chat"
                                assert "重新描述" in result["message"]

    @pytest.mark.asyncio
    async def test_non_first_iteration_uses_call_llm(self, mock_deps):
        """Iteration 0 streams through the engine; the background tool chain
        that continues after the first tool_call still uses call_llm."""
        deps = mock_deps

        tool_payload = {"message": "Let me search", "action": "continue_chat",
                        "tool_call": {"name": "web_search", "arguments": {"query": "test"}}}
        mock_call_llm_ex = AsyncMock(return_value=tool_payload)

        async def _mock_call_llm(*args, **kwargs):
            return {
                "success": True,
                "content": '{"message": "search done", "action": "continue_chat", "tool_call": null}',
                "model": "test-model",
                "usage": {},
            }

        mock_tool_set = MagicMock()
        mock_tool_set.TOOL_DEFINITIONS = []
        mock_tool_set.execute_tool = AsyncMock(return_value={"success": True, "data": "test result"})

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", mock_call_llm_ex):
                        with patch("src.api.research_api.call_llm", new=_mock_call_llm):
                            with patch("src.config.settings", deps["settings"]):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = mock_tool_set
                                api._loop_cancel_flags = {}
                                api._JSON_OUTPUT_SCHEMA = "{}"

                                result = await api._llm_converse("test_ses", "hello")
                                # Tool chains are intentionally continued in
                                # the background after the first search.
                                assert result["status"] == "processing"
                                assert result["message"] == "Let me search"
                                mock_tool_set.execute_tool.assert_awaited_once()
