import pytest
from unittest.mock import patch

from src.config.llm_profiles import LLMProfile, LLMProfileRegistry


class _Delta:
    content = "ok"


class _Chunk:
    choices = [type("Choice", (), {"delta": _Delta()})()]


class _StreamingClient:
    calls = []
    failures = {}

    def __init__(self, *, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def create(self, **kwargs):
        self.calls.append({"api_key": self.api_key, "base_url": self.base_url, **kwargs})
        failure = self.failures.get(self.api_key)
        if failure:
            raise failure

        async def _response():
            yield _Chunk()

        return _response()


class _Completions:
    def __init__(self, client):
        self.create = client.create


class _OpenAI:
    def __init__(self, **kwargs):
        client = _StreamingClient(**kwargs)
        self.chat = type("Chat", (), {"completions": _Completions(client)})()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_stream_uses_configured_default_after_auth_failure():
    import src.core.llm_client as mod

    stale = LLMProfile(name="stale", provider="zhipu", api_key="stale-key", base_url="https://stale", model="glm")
    primary = LLMProfile(name="primary", provider="mimo", api_key="primary-key", base_url="https://primary", model="mimo-v2.5")
    registry = LLMProfileRegistry(
        profiles={"stale": stale, "primary": primary},
        default_profile="stale",
        fallback_chain=["stale", "primary"],
    )
    old_unavailable = set(mod._UNAVAILABLE_PROFILES)
    old_router = mod._router
    _StreamingClient.calls = []
    _StreamingClient.failures = {"stale-key": RuntimeError("401 Unauthorized")}
    mod._UNAVAILABLE_PROFILES.discard("stale")
    try:
        mod.init_llm_infrastructure(registry)
        with patch("openai.AsyncOpenAI", _OpenAI):
            tokens = [token async for token in mod.call_llm_stream("hello")]
    finally:
        mod._router = old_router
        mod._UNAVAILABLE_PROFILES.clear()
        mod._UNAVAILABLE_PROFILES.update(old_unavailable)

    assert tokens == ["ok"]
    assert [call["api_key"] for call in _StreamingClient.calls] == ["stale-key", "primary-key"]


@pytest.mark.asyncio
async def test_stream_retries_same_profile_timeout_before_provider_fallback():
    import src.core.llm_client as mod

    primary = LLMProfile(name="primary", provider="mimo", api_key="primary-key", base_url="https://primary", model="mimo-v2.5")
    backup = LLMProfile(name="backup", provider="local", api_key="backup-key", base_url="http://local", model="local")
    registry = LLMProfileRegistry(profiles={"primary": primary, "backup": backup}, default_profile="primary", fallback_chain=["primary", "backup"])
    old_router = mod._router
    old_unavailable = set(mod._UNAVAILABLE_PROFILES)
    calls = []

    class _RetryOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.chat = type("Chat", (), {"completions": self})()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def create(self, **kwargs):
            calls.append(self.api_key)
            if self.api_key == "primary-key" and calls.count("primary-key") == 1:
                raise TimeoutError("provider timed out")

            async def response():
                yield _Chunk()
            return response()

    mod._UNAVAILABLE_PROFILES.clear()
    try:
        mod.init_llm_infrastructure(registry)
        with patch("openai.AsyncOpenAI", _RetryOpenAI):
            tokens = [token async for token in mod.call_llm_stream("hello")]
    finally:
        mod._router = old_router
        mod._UNAVAILABLE_PROFILES.clear()
        mod._UNAVAILABLE_PROFILES.update(old_unavailable)

    assert tokens == ["ok"]
    assert calls[:2] == ["primary-key", "primary-key"]
    assert "backup-key" not in calls


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_partial_output():
    import src.core.llm_client as mod

    primary = LLMProfile(name="primary", provider="mimo", api_key="primary-key", base_url="https://primary", model="mimo-v2.5")
    backup = LLMProfile(name="backup", provider="local", api_key="", base_url="http://local", model="local")
    registry = LLMProfileRegistry(profiles={"primary": primary, "backup": backup}, default_profile="primary", fallback_chain=["primary", "backup"])
    old_unavailable = set(mod._UNAVAILABLE_PROFILES)
    old_router = mod._router
    mod._UNAVAILABLE_PROFILES.clear()
    _StreamingClient.calls = []

    class _PartialOpenAI(_OpenAI):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            original = self.chat.completions.create

            async def create(**call_kwargs):
                async def response():
                    yield _Chunk()
                    raise RuntimeError("connection dropped")
                _StreamingClient.calls.append({"api_key": kwargs["api_key"], **call_kwargs})
                return response()

            self.chat.completions.create = create

    try:
        mod.init_llm_infrastructure(registry)
        with patch("openai.AsyncOpenAI", _PartialOpenAI):
            with pytest.raises(RuntimeError, match="connection dropped"):
                _ = [token async for token in mod.call_llm_stream("hello")]
    finally:
        mod._router = old_router
        mod._UNAVAILABLE_PROFILES.clear()
        mod._UNAVAILABLE_PROFILES.update(old_unavailable)
    assert len(_StreamingClient.calls) == 1


class _ReasoningOnlyDelta:
    content = None
    reasoning_content = "推理答案正文"


class _ReasoningOnlyChunk:
    choices = [type("Choice", (), {"delta": _ReasoningOnlyDelta()})()]


class _ReasoningOnlyOpenAI:
    def __init__(self, **kwargs):
        self.api_key = kwargs["api_key"]
        self.chat = type("Chat", (), {"completions": self})()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def create(self, **kwargs):
        async def response():
            yield _ReasoningOnlyChunk()
            yield _ReasoningOnlyChunk()
        return response()


@pytest.mark.asyncio
async def test_stream_recovers_reasoning_only_response():
    # Regression: reasoning-first providers (MIMO 2.5/2.6) may stream the
    # whole answer through delta.reasoning_content with delta.content empty.
    # The stream must surface the buffered reasoning instead of failing
    # with "streaming LLM returned empty content".
    import src.core.llm_client as mod

    primary = LLMProfile(name="primary", provider="mimo", api_key="primary-key", base_url="https://primary", model="mimo-v2.5")
    backup = LLMProfile(name="backup", provider="local", api_key="backup-key", base_url="http://local", model="local")
    registry = LLMProfileRegistry(profiles={"primary": primary, "backup": backup}, default_profile="primary", fallback_chain=["primary", "backup"])
    old_router = mod._router
    old_unavailable = set(mod._UNAVAILABLE_PROFILES)
    mod._UNAVAILABLE_PROFILES.clear()
    try:
        mod.init_llm_infrastructure(registry)
        with patch("openai.AsyncOpenAI", _ReasoningOnlyOpenAI):
            tokens = [token async for token in mod.call_llm_stream("hello")]
    finally:
        mod._router = old_router
        mod._UNAVAILABLE_PROFILES.clear()
        mod._UNAVAILABLE_PROFILES.update(old_unavailable)

    assert tokens == ["推理答案正文推理答案正文"]


class _MixedDelta:
    content = "ok"
    reasoning_content = "should-be-ignored"


class _MixedChunk:
    choices = [type("Choice", (), {"delta": _MixedDelta()})()]


class _MixedOpenAI(_ReasoningOnlyOpenAI):
    async def create(self, **kwargs):
        async def response():
            yield _MixedChunk()
        return response()


@pytest.mark.asyncio
async def test_stream_prefers_content_over_reasoning():
    # When real content exists, buffered reasoning must NOT leak into output.
    import src.core.llm_client as mod

    primary = LLMProfile(name="primary", provider="mimo", api_key="primary-key", base_url="https://primary", model="mimo-v2.5")
    backup = LLMProfile(name="backup", provider="local", api_key="backup-key", base_url="http://local", model="local")
    registry = LLMProfileRegistry(profiles={"primary": primary, "backup": backup}, default_profile="primary", fallback_chain=["primary", "backup"])
    old_router = mod._router
    old_unavailable = set(mod._UNAVAILABLE_PROFILES)
    mod._UNAVAILABLE_PROFILES.clear()
    try:
        mod.init_llm_infrastructure(registry)
        with patch("openai.AsyncOpenAI", _MixedOpenAI):
            tokens = [token async for token in mod.call_llm_stream("hello")]
    finally:
        mod._router = old_router
        mod._UNAVAILABLE_PROFILES.clear()
        mod._UNAVAILABLE_PROFILES.update(old_unavailable)

    assert tokens == ["ok"]
