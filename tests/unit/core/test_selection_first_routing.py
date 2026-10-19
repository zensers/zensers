# tests/unit/core/test_selection_first_routing.py
# -*- coding: utf-8 -*-
"""Selection-first routing (EXCLUSIVE): the user's UI provider/model selection
(settings.llm.provider/model/base_url/api_key) is the ONLY serving candidate.
When the selected provider maps to an enabled+keyed registry profile, that
profile joins as the second candidate (parameter constraints).  The profile
chain is NOT a fallback — polling unselected providers' keys would silently
spend their quotas and blur which provider failed (user ruling 2026-10-17).

Rollback hatch: env LLM_SELECTION_FIRST=0 restores the pure chain order.
"""
import asyncio
from unittest.mock import patch

import pytest

from src.core import llm_client
from src.core.llm_retry import CandidateDesc


class FakeProfile:
    """Mimics LLMProfile for _retry_candidate_descs/_profile_to_candidate_desc."""

    def __init__(self, name, model, base_url, *, api_key="sk-x",
                 temperature=None, top_p=None, enabled=True,
                 provider="openai", fallback_model="", max_context_tokens=131072):
        self.name = name
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.temperature = temperature
        self.top_p = top_p
        self.enabled = enabled
        self.provider = provider
        self.fallback_model = fallback_model
        self.max_context_tokens = max_context_tokens


class FakeRegistry:
    def __init__(self, profiles):
        self.profiles = profiles


class FakeRouter:
    """Router whose resolve_candidates returns the registry fallback chain."""

    def __init__(self, profiles, chain):
        self.registry = FakeRegistry(profiles)
        self._chain = chain

    def resolve_candidates(self, hint):
        return [self.registry.profiles[name] for name in self._chain]


CHAIN = ["mimo", "deepseek", "kimi"]


def _chain_profiles():
    return {
        "mimo": FakeProfile("mimo", "mimo-v2.6-flash",
                            "https://token-plan-cn.xiaomimimo.com/v1",
                            api_key="sk-mimo"),
        "deepseek": FakeProfile("deepseek", "deepseek-v4-flash",
                                "https://api.deepseek.com",
                                api_key="sk-ds"),
        "kimi": FakeProfile("kimi", "kimi-k3", "https://api.moonshot.cn/v1",
                            api_key="sk-kimi", temperature=1, top_p=0.95),
    }


@pytest.fixture(autouse=True)
def _isolate_unavailable_profiles():
    """ban_hook=ban_profile writes to the process-global set; restore it."""
    old = set(llm_client._UNAVAILABLE_PROFILES)
    yield
    llm_client._UNAVAILABLE_PROFILES.clear()
    llm_client._UNAVAILABLE_PROFILES.update(old)


@pytest.fixture
def selection_llm(monkeypatch):
    """Simulate a UI selection of Ark/volcengine (the production gap)."""
    monkeypatch.setattr(llm_client.settings.llm, "provider", "volcengine")
    monkeypatch.setattr(llm_client.settings.llm, "model", "selected-model-X")
    monkeypatch.setattr(llm_client.settings.llm, "api_key", "sk-selected-key")
    monkeypatch.setattr(llm_client.settings.llm, "base_url",
                        "https://ark.cn-beijing.volces.com/api/v3")
    monkeypatch.setattr(llm_client.settings.llm, "temperature", 0.7)
    monkeypatch.setattr(llm_client.settings.llm, "top_p", 1.0)


class TestSelectionFirstCandidateOrder:
    def test_selection_candidate_prepended_before_chain(self, selection_llm):
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].name == "selection"
        assert descs[0].model == "selected-model-X"
        assert descs[0].base_url == "https://ark.cn-beijing.volces.com/api/v3"
        assert descs[0].api_key == "sk-selected-key"
        # EXCLUSIVE: selection only — the chain is not a fallback.
        assert [d.name for d in descs[1:]] == []

    def test_selection_carries_no_fallback_model(self, selection_llm):
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].fallback_model == ""

    def test_provider_matching_profile_inserted_at_position_1(self, monkeypatch,
                                                              selection_llm):
        # User selected provider=kimi -> the kimi profile (with its parameter
        # constraints temperature=1 / top_p=0.95) goes right behind selection;
        # the kimi chain entry is deduped away.
        monkeypatch.setattr(llm_client.settings.llm, "provider", "kimi")
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].name == "selection"
        assert descs[1].name == "kimi"
        assert descs[1].model == "kimi-k3"
        assert descs[1].base_url == "https://api.moonshot.cn/v1"
        assert descs[1].temperature == 1
        assert descs[1].top_p == pytest.approx(0.95)
        # EXCLUSIVE: 链上其余成员不再被轮询
        assert [d.name for d in descs[2:]] == []

    def test_provider_profile_disabled_is_skipped(self, monkeypatch, selection_llm):
        profiles = _chain_profiles()
        profiles["kimi"] = FakeProfile("kimi", "kimi-k3",
                                       "https://api.moonshot.cn/v1",
                                       api_key="sk-kimi", enabled=False)
        monkeypatch.setattr(llm_client.settings.llm, "provider", "kimi")
        with patch.object(llm_client, "_router", FakeRouter(profiles, CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["selection"]

    def test_provider_profile_without_usable_key_is_skipped(self, monkeypatch,
                                                            selection_llm):
        # Production case: the volcengine registry profile has NO api_key, so
        # it must NOT be inserted; the selection candidate itself (carrying
        # the settings.llm key) is the volcengine attempt.
        profiles = _chain_profiles()
        profiles["volcengine"] = FakeProfile("volcengine", "doubao-1.5-pro-32k",
                                             "https://ark.cn-beijing.volces.com/api/v3",
                                             api_key="")
        with patch.object(llm_client, "_router", FakeRouter(profiles, CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["selection"]

    def test_unresolved_placeholder_key_is_skipped(self, monkeypatch, selection_llm):
        profiles = _chain_profiles()
        profiles["volcengine"] = FakeProfile("volcengine", "doubao-1.5-pro-32k",
                                             "https://ark.cn-beijing.volces.com/api/v3",
                                             api_key="${ARK_API_KEY}")
        with patch.object(llm_client, "_router", FakeRouter(profiles, CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["selection"]

    def test_dedupe_selection_vs_first_chain_profile(self, monkeypatch,
                                                     selection_llm):
        # Selection model+base_url identical to the provider profile ->
        # the provider profile is dropped, no duplicate entry.
        monkeypatch.setattr(llm_client.settings.llm, "provider", "kimi")
        monkeypatch.setattr(llm_client.settings.llm, "model", "kimi-k3")
        monkeypatch.setattr(llm_client.settings.llm, "base_url",
                            "https://api.moonshot.cn/v1")
        monkeypatch.setattr(llm_client.settings.llm, "api_key", "sk-kimi")
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["selection"]

    def test_no_selection_keeps_pure_chain(self, monkeypatch):
        monkeypatch.setattr(llm_client.settings.llm, "model", "")
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["mimo", "deepseek", "kimi"]

    def test_whitespace_only_model_keeps_pure_chain(self, monkeypatch):
        monkeypatch.setattr(llm_client.settings.llm, "model", "   ")
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["mimo", "deepseek", "kimi"]

    def test_env_off_restores_chain_only(self, monkeypatch, selection_llm):
        monkeypatch.setenv("LLM_SELECTION_FIRST", "0")
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["mimo", "deepseek", "kimi"]

    def test_env_default_is_on(self, monkeypatch, selection_llm):
        monkeypatch.delenv("LLM_SELECTION_FIRST", raising=False)
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)):
            descs = llm_client._retry_candidate_descs()
        assert descs[0].name == "selection"

    def test_provider_preference_requires_router_registry(self, selection_llm):
        # Router without a registry attribute (legacy fakes / init failure):
        # provider lookup degrades gracefully, selection still prepended.
        class RegistryLessRouter:
            def resolve_candidates(self, hint):
                return [_chain_profiles()[name] for name in CHAIN]

        with patch.object(llm_client, "_router", RegistryLessRouter()):
            descs = llm_client._retry_candidate_descs()
        assert [d.name for d in descs] == ["selection"]


class TestSelectionFirstIntegration:
    """call_llm_ex must send attempt 1 to the selection candidate before any
    chain profile."""

    def _run_ex(self):
        return asyncio.run(llm_client.call_llm_ex(
            lambda v: "P", output_contract="prose", expected_output_chars=100,
            task_tag="selection_first_test"))

    def test_attempt1_hits_selection_candidate(self, selection_llm):
        calls = []

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            calls.append((candidate.name, candidate.model, model))
            return "SELECTED OK"

        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)), \
             patch.object(llm_client, "_ex_transport_factory",
                          lambda stream=False, on_token=None: transport):
            result = self._run_ex()
        assert result == "SELECTED OK"
        assert calls == [("selection", "selected-model-X", "selected-model-X")]

    def test_selection_failure_is_exhausted_without_chain(self, selection_llm):
        """EXCLUSIVE: 选中的供应商失败 → 直接预算耗尽，不轮询未选的供应商"""
        calls = []

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            calls.append((candidate.name, model))
            if candidate.name == "selection":
                raise RuntimeError("401 unauthorized: invalid api key")
            return "CHAIN OK"

        from src.core.llm_retry import LLMBudgetExhausted
        with patch.object(llm_client, "_router",
                          FakeRouter(_chain_profiles(), CHAIN)), \
             patch.object(llm_client, "_ex_transport_factory",
                          lambda stream=False, on_token=None: transport):
            with pytest.raises(LLMBudgetExhausted):
                self._run_ex()
        # AUTH on the selection -> ban; no chain candidates exist -> exhausted.
        assert calls == [("selection", "selected-model-X")]
