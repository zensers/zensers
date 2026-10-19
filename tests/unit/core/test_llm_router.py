import pytest
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry, RoutingHint
from src.core.llm_router import LLMRouter


def _make_registry():
    deepseek = LLMProfile(name="deepseek", model="gpt-4o", api_key="sk-deepseek", enabled=True)
    zhipu = LLMProfile(name="zhipu", provider="zhipu", model="deepseek-v4-flash", api_key="sk-zhipu", is_default=True, enabled=True)
    local = LLMProfile(name="local", model="qwen2.5", enabled=False)
    vision = LLMProfile(name="vision", model="gpt-4o-vision", api_key="sk-vision", enabled=True)
    return LLMProfileRegistry(
        profiles={"deepseek": deepseek, "zhipu": zhipu, "local": local, "vision": vision},
        default_profile="zhipu",
        fallback_chain=["deepseek", "zhipu", "local"],
        fixed_agent_routing={"quality_check": "deepseek", "data_collection": "zhipu"},
        action_routing={"analyze": "deepseek", "search": "zhipu", "vision": "vision"},
    )


class TestLLMRouterExplicitOverride:
    def test_explicit_profile_name_returns_that_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="deepseek")
        result = router.resolve(hint)
        assert result.name == "deepseek"

    def test_force_profile_uses_disabled_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="local", force_profile=True)
        result = router.resolve(hint)
        assert result.name == "local"

    def test_non_force_skips_disabled_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="local")
        result = router.resolve(hint)
        assert result.name == "zhipu"

    def test_nonexistent_profile_falls_to_default(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="nonexistent")
        result = router.resolve(hint)
        assert result.name == "zhipu"


class TestLLMRouterFixedAgentMapping:
    def test_known_agent_type_returns_mapped_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="quality_check")
        result = router.resolve(hint)
        assert result.name == "deepseek"

    def test_unknown_agent_type_falls_to_default(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="unknown_agent")
        result = router.resolve(hint)
        assert result.name == "zhipu"


class TestLLMRouterActionMapping:
    def test_known_action_returns_mapped_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="analyze")
        result = router.resolve(hint)
        assert result.name == "deepseek"

    def test_known_secondary_action_returns_zhipu_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="search")
        result = router.resolve(hint)
        assert result.name == "zhipu"

    def test_vision_action_returns_vision_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="vision")
        result = router.resolve(hint)
        assert result.name == "vision"


class TestLLMRouterKeywordAutoClassification:
    def test_reasoning_keyword_maps_to_first_in_fallback_chain(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="generate_report")
        result = router.resolve(hint)
        assert result.name == "deepseek"

    def test_utility_keyword_maps_to_last_enabled_in_fallback_chain(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="extract_data")
        result = router.resolve(hint)
        assert result.name == "zhipu"

    def test_unknown_action_no_keyword_match_falls_to_default(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(action="custom_thing")
        result = router.resolve(hint)
        assert result.name == "zhipu"


class TestLLMRouterDefaultFallback:
    def test_failed_explicit_profile_fallback_target_is_configured_default(self):
        primary = LLMProfile(name="primary", provider="custom", api_key="primary-key", enabled=True)
        optional = LLMProfile(name="optional", provider="custom", api_key="optional-key", enabled=True)
        registry = LLMProfileRegistry(
            profiles={"optional": optional, "primary": primary},
            default_profile="primary",
            fallback_chain=["optional", "primary"],
        )
        candidates = LLMRouter(registry).resolve_candidates(
            RoutingHint(profile_name="optional")
        )
        assert [profile.name for profile in candidates[:2]] == ["optional", "primary"]

    def test_repository_baseline_mimo_is_selected_when_zhipu_placeholder_exists(self):
        registry = LLMProfileRegistry(
            profiles={
                "mimo": LLMProfile(name="mimo", provider="mimo", api_key="mimo-key", enabled=True),
                "zhipu": LLMProfile(name="zhipu", provider="zhipu", api_key="${ZHIPU_API_KEY}", enabled=True),
            },
            default_profile="zhipu",
            fallback_chain=["zhipu", "mimo"],
        )
        result = LLMRouter(registry).resolve(RoutingHint())
        assert result.name == "mimo"

    def test_unresolved_environment_placeholder_is_not_routable(self):
        registry = LLMProfileRegistry(
            profiles={
                "zhipu": LLMProfile(
                    name="zhipu", provider="zhipu", api_key="${ZHIPU_API_KEY}", enabled=True
                ),
                "mimo": LLMProfile(
                    name="mimo", provider="mimo", api_key="mimo-key", enabled=True
                ),
            },
            default_profile="zhipu",
            fallback_chain=["zhipu", "mimo"],
        )
        router = LLMRouter(registry)
        candidates = router.resolve_candidates(RoutingHint())
        assert [profile.name for profile in candidates] == ["mimo"]

    def test_empty_hint_returns_default_profile(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint()
        result = router.resolve(hint)
        assert result.name == "zhipu"

    def test_no_enabled_profiles_raises_error(self):
        empty_registry = LLMProfileRegistry(
            profiles={
                "deepseek": LLMProfile(name="deepseek", enabled=False),
                "zhipu": LLMProfile(name="zhipu", enabled=False),
            },
            default_profile="zhipu",
        )
        router = LLMRouter(empty_registry)
        hint = RoutingHint()
        with pytest.raises(RuntimeError, match="No enabled LLM profile available"):
            router.resolve(hint)

    def test_default_disabled_falls_to_any_enabled(self):
        registry = LLMProfileRegistry(
            profiles={
                "zhipu": LLMProfile(name="zhipu", is_default=True, enabled=False),
                "deepseek": LLMProfile(name="deepseek", api_key="sk-deepseek", enabled=True),
            },
            default_profile="zhipu",
        )
        router = LLMRouter(registry)
        hint = RoutingHint()
        result = router.resolve(hint)
        assert result.name == "deepseek"


class TestLLMRouterPriorityOrder:
    def test_explicit_override_takes_priority_over_agent_mapping(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="quality_check", profile_name="zhipu")
        result = router.resolve(hint)
        assert result.name == "zhipu"

    def test_agent_mapping_takes_priority_over_action_mapping(self):
        registry = _make_registry()
        registry.fixed_agent_routing["quality_check"] = "deepseek"
        registry.action_routing["quality_check"] = "zhipu"
        router = LLMRouter(registry)
        hint = RoutingHint(agent_type="quality_check", action="quality_check")
        result = router.resolve(hint)
        assert result.name == "deepseek"


class TestLLMRouterResolveCandidates:
    def test_candidates_deduplication(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="quality_check", action="analyze")
        candidates = router.resolve_candidates(hint)
        names = [c.name for c in candidates]
        assert len(names) == len(set(names))

    def test_candidates_first_is_best_match(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="quality_check")
        candidates = router.resolve_candidates(hint)
        assert candidates[0].name == "deepseek"

    def test_candidates_includes_default_as_fallback(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="nonexistent")
        candidates = router.resolve_candidates(hint)
        names = [c.name for c in candidates]
        assert "zhipu" in names

    def test_candidates_skips_disabled(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint()
        candidates = router.resolve_candidates(hint)
        names = [c.name for c in candidates]
        assert "local" not in names

    def test_candidates_empty_when_all_disabled(self):
        empty_registry = LLMProfileRegistry(
            profiles={
                "deepseek": LLMProfile(name="deepseek", enabled=False),
                "zhipu": LLMProfile(name="zhipu", enabled=False),
            },
            default_profile="zhipu",
        )
        router = LLMRouter(empty_registry)
        hint = RoutingHint()
        candidates = router.resolve_candidates(hint)
        assert candidates == []

    def test_force_profile_includes_disabled_in_candidates(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(profile_name="local", force_profile=True)
        candidates = router.resolve_candidates(hint)
        assert candidates[0].name == "local"

    def test_candidates_after_primary_includes_other_enabled_profiles(self):
        router = LLMRouter(_make_registry())
        hint = RoutingHint(agent_type="quality_check")
        candidates = router.resolve_candidates(hint)
        names = [c.name for c in candidates]
        assert names[0] == "deepseek"
        assert "zhipu" in names
        assert "vision" in names
