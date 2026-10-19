import pytest
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry, RoutingHint


class TestLLMProfile:
    def test_default_values(self):
        profile = LLMProfile(name="test")
        assert profile.name == "test"
        assert profile.display_name == ""
        assert profile.provider == "openai"
        assert profile.api_key == ""
        assert profile.base_url == "https://api.openai.com/v1"
        assert profile.model == "gpt-4o"
        assert profile.temperature == 0.7
        assert profile.max_tokens == 4096
        assert profile.top_p == 1.0
        assert profile.frequency_penalty == 0.0
        assert profile.presence_penalty == 0.0
        assert profile.max_context_tokens == 128000
        assert profile.cost_limit_per_call == 0.0
        assert profile.is_default is False
        assert profile.enabled is True
        assert profile.created_at == ""
        assert profile.updated_at == ""

    def test_custom_values(self):
        profile = LLMProfile(
            name="deepseek",
            display_name="GPT-4o DeepSeek",
            provider="openai",
            api_key="sk-xxx",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            temperature=0.3,
            max_tokens=8000,
            cost_limit_per_call=0.5,
        )
        assert profile.name == "deepseek"
        assert profile.display_name == "GPT-4o DeepSeek"
        assert profile.temperature == 0.3
        assert profile.max_tokens == 8000
        assert profile.cost_limit_per_call == 0.5


class TestLLMProfileRegistry:
    def test_default_values(self):
        registry = LLMProfileRegistry()
        assert registry.profiles == {}
        assert registry.default_profile == "mimo"
        assert registry.fallback_chain == ["mimo", "deepseek", "local"]
        assert registry.fixed_agent_routing == {}
        assert registry.action_routing == {}

    def test_with_profiles(self):
        deepseek = LLMProfile(name="deepseek", model="gpt-4o")
        zhipu = LLMProfile(name="zhipu", model="deepseek-v4-flash", is_default=True)
        registry = LLMProfileRegistry(
            profiles={"deepseek": deepseek, "zhipu": zhipu},
            default_profile="zhipu",
            fallback_chain=["deepseek", "zhipu"],
        )
        assert len(registry.profiles) == 2
        assert registry.profiles["deepseek"].model == "gpt-4o"
        assert registry.default_profile == "zhipu"


class TestRoutingHint:
    def test_default_values(self):
        hint = RoutingHint()
        assert hint.agent_type is None
        assert hint.action is None
        assert hint.profile_name is None
        assert hint.force_profile is False

    def test_custom_values(self):
        hint = RoutingHint(agent_type="quality_check", action="analyze")
        assert hint.agent_type == "quality_check"
        assert hint.action == "analyze"

    def test_explicit_override(self):
        hint = RoutingHint(profile_name="deepseek", force_profile=True)
        assert hint.profile_name == "deepseek"
        assert hint.force_profile is True
