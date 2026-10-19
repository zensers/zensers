# tests/unit/core/test_llm_client_ex.py
# -*- coding: utf-8 -*-
import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.core import llm_client
from src.core.llm_retry import CandidateDesc, LLMStreamCommitted


def _descs():
    return [
        CandidateDesc(name="mimo", model="mimo-v2.6-flash", fallback_model="mimo-v2.5",
                      max_context_tokens=131072),
        CandidateDesc(name="deepseek", model="deepseek-v4-flash", fallback_model="",
                      max_context_tokens=128000),
    ]


@pytest.fixture(autouse=True)
def _isolate_unavailable_profiles():
    """Engine runs here may hit ban rungs; ban_hook=ban_profile writes to the
    process-global _UNAVAILABLE_PROFILES.  Restore it so test-order leaks
    cannot break the routing tests."""
    old = set(llm_client._UNAVAILABLE_PROFILES)
    yield
    llm_client._UNAVAILABLE_PROFILES.clear()
    llm_client._UNAVAILABLE_PROFILES.update(old)


class TestCallLLMEx:
    def test_success_passthrough(self):
        async def fake_transport(candidate, **kw):
            return "RESULT"

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "_ex_transport_factory",
                          lambda stream=False, on_token=None: fake_transport):
            result = asyncio.run(llm_client.call_llm_ex(
                lambda v: "P", output_contract="prose", expected_output_chars=100))
        assert result == "RESULT"

    def test_legacy_flag_bypasses_engine(self, monkeypatch):
        monkeypatch.setenv("LLM_RETRY_ENGINE", "legacy")
        with patch.object(llm_client, "call_llm",
                          AsyncMock(return_value={"success": True, "content": "C"})):
            result = asyncio.run(llm_client.call_llm_ex(lambda v: "P"))
        assert result == "C"

    def test_legacy_flag_failure_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_RETRY_ENGINE", "legacy")
        with patch.object(llm_client, "call_llm",
                          AsyncMock(return_value={"success": False, "message": "boom"})):
            with pytest.raises(RuntimeError, match="boom"):
                asyncio.run(llm_client.call_llm_ex(lambda v: "P"))

    def test_plain_string_prompt_builder_accepted(self):
        async def fake_transport(candidate, **kw):
            return "OK"

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "_ex_transport_factory",
                          lambda stream=False, on_token=None: fake_transport):
            result = asyncio.run(llm_client.call_llm_ex("RAW PROMPT"))
        assert result == "OK"

    def test_budget_and_base_max_tokens_wired(self):
        captured = {}

        class FakeEngine:
            def __init__(self, **kw):
                captured.update(kw)

            async def run(self, *, prompt_builder, output_contract):
                return "FINE"

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "_ex_transport_factory",
                          lambda stream=False, on_token=None: AsyncMock()), \
             patch("src.core.llm_client.RetryEngine", FakeEngine):
            asyncio.run(llm_client.call_llm_ex(lambda v: "P", expected_output_chars=21000))
        assert captured["base_max_tokens"] == int(21000 / 1.5 * 1.3)
        assert captured["budget"].max_seconds == pytest.approx(21000 / 25 + 180)
        assert captured["task_tag"] == ""

    def test_retry_engine_import_available(self):
        # call_llm_ex must reference the real RetryEngine (imported at module top or locally)
        assert hasattr(llm_client, "call_llm_ex")

    def test_all_asyncopenai_sites_disable_sdk_retries(self):
        repo_root = Path(__file__).resolve().parents[3]
        for rel in ("src/core/llm_client.py", "src/core/llm_client_pool.py"):
            source = (repo_root / rel).read_text(encoding="utf-8")
            n_constructors = source.count("AsyncOpenAI(")
            n_disabled = source.count("max_retries=0")
            assert n_constructors >= 1
            assert n_disabled >= n_constructors, (rel, n_constructors, n_disabled)

    def test_ban_profile_registers(self):
        try:
            llm_client.ban_profile("test_profile_x")
            assert "test_profile_x" in llm_client._UNAVAILABLE_PROFILES
        finally:
            llm_client._UNAVAILABLE_PROFILES.discard("test_profile_x")


class TestCallLLMExStreaming:
    def test_stream_forwards_tokens_and_buffers(self):
        async def fake_stream(prompt, **kw):
            for chunk in ("a", "b", "c"):
                yield chunk

        forwarded = []
        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "call_llm_stream", fake_stream):
            result = asyncio.run(llm_client.call_llm_ex(
                lambda v: "P", stream=True, on_token=forwarded.append))
        assert result == "abc"
        assert forwarded == ["a", "b", "c"]

    def test_stream_committed_after_partial_output_propagates(self):
        async def fake_stream(prompt, **kw):
            yield "tok"
            raise RuntimeError("connection dropped")

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "call_llm_stream", fake_stream):
            with pytest.raises(LLMStreamCommitted):
                asyncio.run(llm_client.call_llm_ex(lambda v: "P", stream=True))

    def test_stream_uncommitted_failure_still_retries(self):
        async def fake_stream(prompt, **kw):
            raise RuntimeError("429 too many requests")
            yield  # pragma: no cover - makes this an async generator

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "call_llm_stream", fake_stream):
            with pytest.raises(Exception):
                asyncio.run(llm_client.call_llm_ex(lambda v: "P", stream=True))

    def test_engine_stream_transport_is_single_shot(self):
        # Follow-up ⑦: the engine stream transport drives call_llm_stream
        # exactly ONCE per engine attempt (max_timeout_retries=0).  The
        # engine's TIMEOUT ladder owns retries; before the fix one engine
        # attempt could hit the provider up to 3x via the inner retry loop.
        calls = []

        async def fake_stream(prompt, **kw):
            calls.append(kw)
            if len(calls) == 1:
                raise TimeoutError("provider timed out")
            yield "engine retry produced a usable streaming answer"

        with patch.object(llm_client, "_retry_candidate_descs", _descs), \
             patch.object(llm_client, "call_llm_stream", fake_stream):
            result = asyncio.run(llm_client.call_llm_ex(lambda v: "P", stream=True))
        assert result == "engine retry produced a usable streaming answer"
        # TIMEOUT on the first engine attempt, ladder rung-0 retry succeeds
        # on the second -> 2 engine attempts -> exactly 2 transport calls.
        assert len(calls) == 2
        assert all(kw.get("max_timeout_retries") == 0 for kw in calls)

    def test_stream_inner_timeout_retry_param(self):
        # call_llm_stream's inner timeout loop honours max_timeout_retries:
        # 0 = single-shot (engine mode), default 2 = legacy behaviour kept
        # for direct callers (see test_stream_retries_same_profile_timeout_
        # before_provider_fallback in test_llm_client_stream_routing.py).
        calls = []

        class _TimeoutOpenAI:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": self})()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def create(self, **kwargs):
                calls.append(kwargs)
                raise TimeoutError("provider timed out")

        async def drain(gen):
            async for _ in gen:
                pass

        with patch("openai.AsyncOpenAI", _TimeoutOpenAI), \
             patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(TimeoutError, match="provider timed out"):
                asyncio.run(drain(llm_client.call_llm_stream(
                    "hello", api_key="k", base_url="http://x",
                    max_timeout_retries=0)))
            assert len(calls) == 1  # single-shot: no inner retry

            calls.clear()
            with pytest.raises(TimeoutError, match="provider timed out"):
                asyncio.run(drain(llm_client.call_llm_stream(
                    "hello", api_key="k", base_url="http://x")))
            assert len(calls) == 3  # legacy default: 1 + 2 inner retries


class TestCallLLMExLegacyContract:
    def test_legacy_flag_contract_builder(self, monkeypatch):
        monkeypatch.setenv("LLM_RETRY_ENGINE", "legacy")

        def builder(variations):
            assert variations.temperature is None
            return "LEGACY PROMPT"

        with patch.object(llm_client, "call_llm",
                          AsyncMock(return_value={"success": True, "content": "C"})) as mock_call:
            result = asyncio.run(llm_client.call_llm_ex(builder))
        assert result == "C"
        assert mock_call.await_args.args[0] == "LEGACY PROMPT"


class TestExTransportTemperature:
    """E1: kimi 只接受 temperature=1。base attempt（variation.temperature=None）
    必须把 candidate.profile 温度传给下层，而不是 settings 默认 0.7。"""

    def test_non_stream_base_attempt_uses_candidate_temperature(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)]
        captured = {}

        async def fake_api(**kw):
            captured.update(kw)
            return {"success": True, "content": "OK",
                    "choices": [{"message": {"content": "OK"}}]}

        transport = llm_client._ex_transport_factory(stream=False)
        with patch.object(llm_client, "_call_llm_api", fake_api):
            result = asyncio.run(transport(descs[0], prompt="P", model="kimi-k2.7",
                                           max_tokens=100, temperature=None))
        assert result == "OK"
        assert captured["temperature"] == 1

    def test_non_stream_variation_temperature_wins(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)]
        captured = {}

        async def fake_api(**kw):
            captured.update(kw)
            return {"success": True, "content": "OK",
                    "choices": [{"message": {"content": "OK"}}]}

        transport = llm_client._ex_transport_factory(stream=False)
        with patch.object(llm_client, "_call_llm_api", fake_api):
            asyncio.run(transport(descs[0], prompt="P", model="kimi-k2.7",
                                  max_tokens=100, temperature=0.1))
        assert captured["temperature"] == pytest.approx(0.1)

    def test_stream_base_attempt_uses_candidate_temperature(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)]
        captured = {}

        async def fake_stream(prompt, **kw):
            captured.update(kw)
            yield "OK"

        transport = llm_client._ex_transport_factory(stream=True)
        result = None
        async def run():
            return await transport(descs[0], prompt="P", model="kimi-k2.7",
                                   max_tokens=100, temperature=None)
        with patch.object(llm_client, "call_llm_stream", fake_stream):
            result = asyncio.run(run())
        assert result == "OK"
        assert captured["temperature"] == 1

    def test_stream_variation_temperature_wins(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)]
        captured = {}

        async def fake_stream(prompt, **kw):
            captured.update(kw)
            yield "OK"

        transport = llm_client._ex_transport_factory(stream=True)
        async def run():
            return await transport(descs[0], prompt="P", model="kimi-k2.7",
                                   max_tokens=100, temperature=0.1)
        with patch.object(llm_client, "call_llm_stream", fake_stream):
            result = asyncio.run(run())
        assert result == "OK"
        assert captured["temperature"] == pytest.approx(0.1)

    def test_candidate_without_temperature_falls_back_to_settings(self):
        # None 约束候选回落到 settings 默认（历史行为不变）
        descs = [CandidateDesc(name="mimo", model="mimo-v2.6-flash")]
        captured = {}
        mock_settings = MagicMock()
        mock_settings.llm.temperature = 0.7
        mock_settings.llm.max_tokens = 2048

        async def fake_api(**kw):
            captured.update(kw)
            return {"success": True, "content": "OK",
                    "choices": [{"message": {"content": "OK"}}]}

        transport = llm_client._ex_transport_factory(stream=False)
        with patch.object(llm_client, "_call_llm_api", fake_api), \
             patch.object(llm_client, "settings", mock_settings):
            asyncio.run(transport(descs[0], prompt="P", model="mimo-v2.6-flash",
                                  max_tokens=100, temperature=None))
        assert captured["temperature"] == pytest.approx(0.7)

    def test_retry_candidate_descs_carries_profile_temperature(self, monkeypatch):
        # Exclusive-selection contract: provider=kimi matches the registry
        # profile, which joins right behind the selection candidate and
        # carries the profile's parameter constraints.
        monkeypatch.setattr(llm_client.settings.llm, "provider", "kimi")
        monkeypatch.setattr(llm_client.settings.llm, "model", "selected-model-X")
        monkeypatch.setattr(llm_client.settings.llm, "base_url", "https://ark")
        monkeypatch.setattr(llm_client.settings.llm, "api_key", "sk-selected")

        class FakeProfile:
            name = "kimi"
            model = "kimi-k2.7"
            fallback_model = ""
            max_context_tokens = 131072
            api_key = "sk-test"
            base_url = "https://x"
            enabled = True
            provider = "moonshot"
            temperature = 1

        class FakeRegistry:
            def __init__(self, profiles):
                self.profiles = profiles

        class FakeRouter:
            def __init__(self):
                self.registry = FakeRegistry({"kimi": FakeProfile})

            def resolve_candidates(self, hint):
                return [FakeProfile()]

        fake_router = FakeRouter()
        with patch.object(llm_client, "_router", fake_router):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].name == "selection"
        assert descs[0].model == "selected-model-X"
        assert descs[1].name == "kimi"
        assert descs[1].temperature == 1


class TestExTransportTopP:
    """E2 (ses_d6417b3a): kimi-k3 rejects top_p != 0.95 with
    "invalid top_p: only 0.95 is allowed for this model" — on BOTH engine
    paths.  The candidate profile top_p must reach call_llm_stream and
    _call_llm_api instead of the settings default (1.0)."""

    def test_stream_transport_forwards_candidate_top_p(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k3", top_p=0.95)]
        captured = {}

        async def fake_stream(prompt, **kw):
            captured.update(kw)
            yield "OK"

        transport = llm_client._ex_transport_factory(stream=True)

        async def run():
            return await transport(descs[0], prompt="P", model="kimi-k3",
                                   max_tokens=100, temperature=None)

        with patch.object(llm_client, "call_llm_stream", fake_stream):
            result = asyncio.run(run())
        assert result == "OK"
        assert captured["top_p"] == pytest.approx(0.95)

    def test_non_stream_transport_forwards_candidate_top_p(self):
        descs = [CandidateDesc(name="kimi", model="kimi-k3", top_p=0.95)]
        captured = {}

        async def fake_api(**kw):
            captured.update(kw)
            return {"success": True, "content": "OK",
                    "choices": [{"message": {"content": "OK"}}]}

        transport = llm_client._ex_transport_factory(stream=False)
        with patch.object(llm_client, "_call_llm_api", fake_api):
            result = asyncio.run(transport(descs[0], prompt="P", model="kimi-k3",
                                           max_tokens=100, temperature=None))
        assert result == "OK"
        assert captured["top_p"] == pytest.approx(0.95)

    def test_candidate_without_top_p_passes_none(self):
        # None keeps the historical fallback chain inside call_llm_stream /
        # _call_llm_api (profile.top_p when profiled, else settings).
        descs = [CandidateDesc(name="mimo", model="mimo-v2.6-flash")]
        captured = {}

        async def fake_api(**kw):
            captured.update(kw)
            return {"success": True, "content": "OK",
                    "choices": [{"message": {"content": "OK"}}]}

        transport = llm_client._ex_transport_factory(stream=False)
        with patch.object(llm_client, "_call_llm_api", fake_api):
            asyncio.run(transport(descs[0], prompt="P", model="mimo-v2.6-flash",
                                  max_tokens=100, temperature=None))
        assert captured["top_p"] is None

    def test_call_llm_api_explicit_top_p_beats_settings(self):
        captured = {}

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": self})()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def create(self, **kwargs):
                captured.update(kwargs)

                class _Resp:
                    def model_dump(self):
                        return {"choices": [{"message": {"content": "OK"}}],
                                "usage": {}}

                return _Resp()

        mock_settings = MagicMock()
        mock_settings.llm.api_key = "sk-test"
        mock_settings.llm.base_url = "https://x"
        mock_settings.llm.top_p = 1.0
        mock_settings.llm.frequency_penalty = 0.0
        mock_settings.llm.presence_penalty = 0.0

        with patch("openai.AsyncOpenAI", _FakeOpenAI), \
             patch.object(llm_client, "settings", mock_settings):
            asyncio.run(llm_client._call_llm_api(
                "P", "kimi-k3", api_key="sk-test", base_url="https://x",
                top_p=0.95))
        assert captured["top_p"] == pytest.approx(0.95)

        captured.clear()
        with patch("openai.AsyncOpenAI", _FakeOpenAI), \
             patch.object(llm_client, "settings", mock_settings):
            asyncio.run(llm_client._call_llm_api(
                "P", "mimo", api_key="sk-test", base_url="https://x"))
        assert captured["top_p"] == pytest.approx(1.0)  # settings default

    def test_call_llm_stream_top_p_reaches_provider(self):
        calls = []

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": self})()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def create(self, **kwargs):
                calls.append(kwargs)

                async def _gen():
                    delta = type("Delta", (), {"content": "OK",
                                               "reasoning_content": None})()
                    chunk = type("Chunk", (), {})()
                    chunk.choices = [type("Choice", (), {"delta": delta})()]
                    yield chunk
                return _gen()

        async def drain(gen):
            async for _ in gen:
                pass

        # Explicit transport (model/api_key/base_url) -> unprofiled attempt:
        # None falls back to settings; explicit 0.95 wins over settings.
        with patch("openai.AsyncOpenAI", _FakeOpenAI):
            asyncio.run(drain(llm_client.call_llm_stream(
                "hello", model="kimi-k3", api_key="k",
                base_url="http://x", top_p=0.95)))
        assert calls[0]["top_p"] == pytest.approx(0.95)

    def test_retry_candidate_descs_carries_profile_top_p(self, monkeypatch):
        # Exclusive-selection contract: provider=kimi matches the registry
        # profile, which joins right behind the selection candidate.
        monkeypatch.setattr(llm_client.settings.llm, "provider", "kimi")
        monkeypatch.setattr(llm_client.settings.llm, "model", "selected-model-X")
        monkeypatch.setattr(llm_client.settings.llm, "base_url", "https://ark")
        monkeypatch.setattr(llm_client.settings.llm, "api_key", "sk-selected")

        class FakeProfile:
            name = "kimi"
            model = "kimi-k3"
            fallback_model = ""
            max_context_tokens = 131072
            api_key = "sk-test"
            base_url = "https://x"
            enabled = True
            provider = "moonshot"
            temperature = 1
            top_p = 0.95

        class FakeRegistry:
            def __init__(self, profiles):
                self.profiles = profiles

        class FakeRouter:
            def __init__(self):
                self.registry = FakeRegistry({"kimi": FakeProfile})

            def resolve_candidates(self, hint):
                return [FakeProfile()]

        with patch.object(llm_client, "_router", FakeRouter()):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].name == "selection"
        assert descs[1].name == "kimi"
        assert descs[1].top_p == pytest.approx(0.95)
