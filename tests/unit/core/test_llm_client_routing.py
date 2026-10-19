import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry, RoutingHint


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


def _make_registry():
    deepseek = LLMProfile(name="deepseek", api_key="sk-deepseek", base_url="https://deepseek.api/v1", model="gpt-4o", fallback_model="gpt-4o-mini")
    zhipu = LLMProfile(name="zhipu", api_key="sk-zhipu", base_url="https://zhipu.api/v1", model="gpt-4o-mini", fallback_model="gpt-3.5-turbo")
    default = LLMProfile(name="migrated", api_key="sk-default", base_url="https://default.api/v1", model="test-model", fallback_model="test-fallback")
    return LLMProfileRegistry(profiles={"deepseek": deepseek, "zhipu": zhipu, "migrated": default}, default_profile="migrated", fallback_chain=["deepseek", "zhipu", "migrated"])


class TestRoutingHintLegacyPath:
    @pytest.mark.asyncio
    async def test_no_hint_no_router_uses_settings(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "test-model"
                assert call_kwargs["api_key"] == "test-key"

    @pytest.mark.asyncio
    async def test_hint_none_uses_settings(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test", routing_hint=None)
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "test-model"


class TestRoutingHintWithRouter:
    @pytest.mark.asyncio
    async def test_hint_routes_to_profile(self):
        registry = _make_registry()
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, _router, _client_pool
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "routed"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(action="deep_analysis")
                result = await call_llm(prompt="test", routing_hint=hint)
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "gpt-4o"
                assert call_kwargs["api_key"] == "sk-deepseek"

    @pytest.mark.asyncio
    async def test_hint_with_explicit_profile_name(self):
        registry = _make_registry()
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "fast"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(profile_name="zhipu")
                result = await call_llm(prompt="test", routing_hint=hint)
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "gpt-4o-mini"
                assert call_kwargs["api_key"] == "sk-zhipu"

    @pytest.mark.asyncio
    async def test_hint_unmatched_falls_back_to_default_profile(self):
        registry = _make_registry()
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "default"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(action="unknown_action")
                result = await call_llm(prompt="test", routing_hint=hint)
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "test-model"
                assert call_kwargs["api_key"] == "sk-default"

    @pytest.mark.asyncio
    async def test_hint_with_no_router_falls_back_to_settings(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import _router
            import src.core.llm_client as mod
            orig = mod._router
            mod._router = None
            try:
                with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                    mock_api.return_value = {"choices": [{"message": {"content": "legacy"}}], "usage": {}}
                    from src.core.llm_client import call_llm
                    hint = RoutingHint(action="deep_analysis")
                    result = await call_llm(prompt="test", routing_hint=hint)
                    assert result["success"] is True
                    call_kwargs = mock_api.call_args[1]
                    assert call_kwargs["model"] == "test-model"
            finally:
                mod._router = orig

    @pytest.mark.asyncio
    async def test_explicit_params_override_hint(self):
        registry = _make_registry()
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "override"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(profile_name="zhipu")
                result = await call_llm(prompt="test", routing_hint=hint, model="my-custom-model", api_key="my-key")
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "my-custom-model"
                assert call_kwargs["api_key"] == "my-key"
                assert call_kwargs["base_url"] == "https://zhipu.api/v1"

    @pytest.mark.asyncio
    async def test_hint_fills_non_overridden_fields(self):
        registry = _make_registry()
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(profile_name="zhipu")
                result = await call_llm(prompt="test", routing_hint=hint, model="my-custom-model")
                assert result["success"] is True
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["model"] == "my-custom-model"
                assert call_kwargs["api_key"] == "sk-zhipu"
                assert call_kwargs["base_url"] == "https://zhipu.api/v1"

    @pytest.mark.asyncio
    async def test_zhipu_auth_failure_skips_profile_fallback_and_uses_mimo(self):
        """401 from optional zhipu must fail over directly to healthy mimo."""
        import src.core.llm_client as mod

        zhipu = LLMProfile(
            name="zhipu", provider="zhipu", api_key="expired",
            base_url="https://zhipu.api/v1", model="glm", fallback_model="glm-fast",
        )
        mimo = LLMProfile(
            name="mimo", provider="mimo", api_key="mimo-key",
            base_url="https://mimo.api/v1", model="mimo-v2.5",
        )
        registry = LLMProfileRegistry(
            profiles={"zhipu": zhipu, "mimo": mimo},
            default_profile="zhipu", fallback_chain=["zhipu", "mimo"],
        )
        mod._UNAVAILABLE_PROFILES.discard("zhipu")
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, call_llm
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = [
                    RuntimeError("401 Unauthorized"),
                    {"choices": [{"message": {"content": "mimo-ok"}}], "usage": {}},
                ]
                result = await call_llm(
                    prompt="test", routing_hint=RoutingHint(profile_name="zhipu"),
                )

        assert result["success"] is True
        assert result.get("fallback_used") is True
        assert result.get("fallback_profile") == "mimo"
        assert mock_api.call_count == 2
        assert mock_api.call_args_list[1].kwargs["model"] == "mimo-v2.5"
        assert mock_api.call_args_list[1].kwargs["api_key"] == "mimo-key"
        assert all(call.kwargs["model"] != "glm-fast" for call in mock_api.call_args_list)

    @pytest.mark.asyncio
    async def test_empty_primary_profile_response_uses_next_profile(self):
        """An empty successful HTTP response must activate profile failover."""
        import src.core.llm_client as mod

        zhipu = LLMProfile(
            name="zhipu", provider="zhipu", api_key="key-z",
            base_url="https://zhipu.api/v1", model="glm",
        )
        mimo = LLMProfile(
            name="mimo", provider="mimo", api_key="key-m",
            base_url="https://mimo.api/v1", model="mimo-v2.5",
        )
        registry = LLMProfileRegistry(
            profiles={"zhipu": zhipu, "mimo": mimo},
            default_profile="zhipu", fallback_chain=["zhipu", "mimo"],
        )
        mod._UNAVAILABLE_PROFILES.discard("zhipu")
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, call_llm
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = [
                    {"choices": [{"message": {"content": ""}}], "usage": {}},
                    {"choices": [{"message": {"content": ""}}], "usage": {}},
                    {"choices": [{"message": {"content": "mimo after empty"}}], "usage": {}},
                ]
                result = await call_llm(prompt="test", routing_hint=RoutingHint(profile_name="zhipu"))

        assert result["success"] is True
        assert result["content"] == "mimo after empty"
        assert result.get("fallback_profile") == "mimo"
        assert mock_api.call_args_list[2].kwargs["model"] == "mimo-v2.5"

    @pytest.mark.asyncio
    async def test_empty_primary_profile_response_retries_same_profile_once(self):
        registry = LLMProfileRegistry(
            profiles={"mimo": LLMProfile(
                name="mimo", provider="mimo", api_key="key-m",
                base_url="https://mimo.api/v1", model="mimo-v2.5",
            )},
            default_profile="mimo", fallback_chain=["mimo"],
        )
        import src.core.llm_client as mod
        mod._UNAVAILABLE_PROFILES.discard("mimo")
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, call_llm
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = [
                    {"choices": [{"message": {"content": ""}}], "usage": {}},
                    {"choices": [{"message": {"content": "mimo retry ok"}}], "usage": {}},
                ]
                result = await call_llm(prompt="test", routing_hint=RoutingHint(action="intent_analysis"))

        assert result["success"] is True
        assert result["content"] == "mimo retry ok"
        assert mock_api.call_count == 2

    @pytest.mark.asyncio
    async def test_profile_concurrency_gate_limits_inflight_calls(self):
        profile = LLMProfile(
            name="mimo", provider="mimo", api_key="key-m",
            base_url="https://mimo.api/v1", model="mimo-v2.5",
            max_concurrency=1,
        )
        registry = LLMProfileRegistry(
            profiles={"mimo": profile}, default_profile="mimo", fallback_chain=["mimo"],
        )
        import src.core.llm_client as mod
        mod._UNAVAILABLE_PROFILES.discard("mimo")
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, call_llm
            init_llm_infrastructure(registry)
            active = 0
            peak = 0

            async def fake_api(**kwargs):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

            with patch("src.core.llm_client._call_llm_api", new=fake_api):
                results = await asyncio.gather(*[
                    call_llm(prompt=f"test-{i}", routing_hint=RoutingHint(action="intent_analysis"))
                    for i in range(3)
                ])

        assert all(result["success"] for result in results)
        assert peak == 1

    @pytest.mark.asyncio
    async def test_unhinted_call_uses_default_profile_fallback_chain(self):
        """Legacy call_llm() callers must not bypass the configured router."""
        import src.core.llm_client as mod

        zhipu = LLMProfile(
            name="zhipu", provider="zhipu", api_key="expired",
            base_url="https://zhipu.api/v1", model="glm",
        )
        mimo = LLMProfile(
            name="mimo", provider="mimo", api_key="mimo-key",
            base_url="https://mimo.api/v1", model="mimo-v2.5",
        )
        registry = LLMProfileRegistry(
            profiles={"zhipu": zhipu, "mimo": mimo},
            default_profile="zhipu", fallback_chain=["zhipu", "mimo"],
        )
        mod._UNAVAILABLE_PROFILES.discard("zhipu")
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure, call_llm
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = [
                    RuntimeError("401 Unauthorized"),
                    {"choices": [{"message": {"content": "mimo-ok"}}], "usage": {}},
                ]
                result = await call_llm(prompt="test")

        assert result["success"] is True
        assert result.get("fallback_profile") == "mimo"
        assert mock_api.call_args_list[1].kwargs["model"] == "mimo-v2.5"


class TestInitLlmInfrastructure:
    def test_init_creates_router_and_pool(self):
        registry = _make_registry()
        from src.core.llm_client import init_llm_infrastructure, _router, _client_pool
        import src.core.llm_client as mod
        init_llm_infrastructure(registry)
        assert mod._router is not None
        assert mod._client_pool is not None


class TestCostLimitPerCall:
    @pytest.mark.asyncio
    async def test_cost_limit_per_call_skips_to_next_candidate(self):
        expensive = LLMProfile(
            name="expensive", api_key="sk-exp", base_url="https://exp.api/v1",
            model="gpt-4o", cost_limit_per_call=0.001,
        )
        cheap = LLMProfile(
            name="cheap", api_key="sk-cheap", base_url="https://cheap.api/v1",
            model="gpt-4o-mini", cost_limit_per_call=0.0,
        )
        registry = LLMProfileRegistry(
            profiles={"expensive": expensive, "cheap": cheap},
            default_profile="cheap",
        )
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(profile_name="expensive")
                result = await call_llm(prompt="test", max_tokens=4096, routing_hint=hint)
                assert result["success"] is True
                assert result.get("fallback_used") is True
                assert result.get("fallback_profile") == "cheap"

    @pytest.mark.asyncio
    async def test_cost_limit_per_call_zero_allows_call(self):
        no_limit = LLMProfile(
            name="no_limit", api_key="sk-nl", base_url="https://nl.api/v1",
            model="gpt-4o", cost_limit_per_call=0.0,
        )
        registry = LLMProfileRegistry(
            profiles={"no_limit": no_limit, "migrated": LLMProfile(name="migrated", api_key="sk-d", base_url="https://d.api/v1")},
            default_profile="migrated",
        )
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import init_llm_infrastructure
            init_llm_infrastructure(registry)
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                hint = RoutingHint(profile_name="no_limit")
                result = await call_llm(prompt="test", routing_hint=hint)
                assert result["success"] is True
