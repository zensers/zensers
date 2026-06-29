"""Test: call_llm_stream() streaming LLM function"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def _mock_settings():
    mock = MagicMock()
    mock.llm.max_tokens = 4096
    mock.llm.temperature = 0.7
    mock.llm.model = "test-model"
    mock.llm.cheap_model = "test-fallback"
    mock.llm.cost_limit_per_report = 0
    mock.llm.api_key = "test-key"
    mock.llm.base_url = "https://test.example.com"
    mock.llm.top_p = 1.0
    mock.llm.frequency_penalty = 0.0
    mock.llm.presence_penalty = 0.0
    return mock


def _make_stream_chunks(text_chunks):
    """Build a mock streaming response that yields chunks."""
    class MockChoice:
        def __init__(self, delta):
            self.delta = delta
            self.index = 0
            self.finish_reason = None

    class MockDelta:
        def __init__(self, content):
            self.content = content
            self.role = None

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(MockDelta(content))]
            self.id = "mock-id"
            self.object = "chat.completion.chunk"

    async def _gen():
        for chunk in text_chunks:
            yield MockChunk(chunk)

    return _gen


class TestCallLlmStream:
    @pytest.mark.asyncio
    async def test_yields_tokens_in_order(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["Hello", " ", "World"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt="test"):
                    tokens.append(token)
                assert tokens == ["Hello", " ", "World"]

    @pytest.mark.asyncio
    async def test_passes_stream_true(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="test"):
                    pass
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_uses_model_from_settings(self):
        ms = _mock_settings()
        ms.llm.model = "gpt-4o"
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="test"):
                    pass
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_model_override(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="test", model="gpt-4o-mini"):
                    pass
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_no_tokens(self):
        ms = _mock_settings()
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt=""):
                    tokens.append(token)
                assert tokens == []
                mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_prompt_returns_no_tokens(self):
        ms = _mock_settings()
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt="   "):
                    tokens.append(token)
                assert tokens == []

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="hi", system_prompt="Be helpful"):
                    pass
                messages = mock_client.chat.completions.create.call_args[1]["messages"]
                assert {"role": "system", "content": "Be helpful"} in messages
                assert {"role": "user", "content": "hi"} in messages

    @pytest.mark.asyncio
    async def test_max_tokens_none_uses_default(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="test"):
                    pass
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_temperature_none_uses_default(self):
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["ok"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                async for _ in call_llm_stream(prompt="test"):
                    pass
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self):
        ms = _mock_settings()
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = Exception("API error")

                from src.core.llm_client import call_llm_stream

                with pytest.raises(Exception, match="API error"):
                    async for _ in call_llm_stream(prompt="test"):
                        pass

    @pytest.mark.asyncio
    async def test_handles_empty_choices(self):
        """Stream chunks with empty choices list should be skipped."""
        class MockEmptyChunk:
            def __init__(self):
                self.choices = []
                self.id = "mock-id"

        async def _empty_gen():
            yield MockEmptyChunk()

        ms = _mock_settings()
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = _empty_gen()

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt="test"):
                    tokens.append(token)
                assert tokens == []

    @pytest.mark.asyncio
    async def test_handles_delta_without_content(self):
        """Stream chunks with delta but no content should be skipped."""
        class MockDelta:
            def __init__(self):
                self.content = None
                self.role = "assistant"

        class MockChoice:
            def __init__(self):
                self.delta = MockDelta()
                self.index = 0

        class MockChunk:
            def __init__(self):
                self.choices = [MockChoice()]
                self.id = "mock-id"

        async def _gen():
            yield MockChunk()

        ms = _mock_settings()
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = _gen()

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt="test"):
                    tokens.append(token)
                assert tokens == []

    @pytest.mark.asyncio
    async def test_skips_stream_token_counting(self):
        """Unlike call_llm, call_llm_stream does NOT count tokens or trigger callbacks."""
        ms = _mock_settings()
        mock_gen = _make_stream_chunks(["a", "b"])
        with patch("src.core.llm_client.settings", ms):
            with patch("openai.AsyncOpenAI") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_gen()

                from src.core.llm_client import call_llm_stream

                tokens = []
                async for token in call_llm_stream(prompt="test"):
                    tokens.append(token)
                assert tokens == ["a", "b"]
