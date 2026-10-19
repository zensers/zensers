from typing import List, Optional
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry, RoutingHint


class LLMRouter:
    REASONING_KEYWORDS = {
        "analyze", "analysis", "generate", "write", "review", "plan",
        "synthesize", "reason", "evaluate", "assess", "judge", "critique",
        "summarize", "interpret", "recommend", "decide", "compare",
    }
    UTILITY_KEYWORDS = {
        "search", "scrape", "format", "translate", "extract", "parse",
        "classify", "count", "lookup", "fetch", "validate", "check",
        "embed", "tokenize", "convert",
    }

    def __init__(self, registry: LLMProfileRegistry):
        self.registry = registry

    @staticmethod
    def _has_usable_api_key(profile: LLMProfile) -> bool:
        """Treat unresolved YAML environment placeholders as missing keys."""
        key = str(profile.api_key or "").strip()
        return bool(key) and not (key.startswith("${") and key.endswith("}"))

    def resolve(self, hint: RoutingHint) -> LLMProfile:
        candidates = self.resolve_candidates(hint)
        if candidates:
            return candidates[0]
        raise RuntimeError("No enabled LLM profile available")

    def resolve_candidates(self, hint: RoutingHint) -> List[LLMProfile]:
        seen = set()
        candidates = []

        def _add(profile: Optional[LLMProfile], force: bool = False):
            if not profile or profile.name in seen or not (force or profile.enabled):
                return
            # Local/Ollama endpoints do not require an API key.  Remote
            # profiles without a key are configuration errors, not usable
            # fallback candidates; routing them only creates repeated 401s.
            provider = str(profile.provider or "").lower()
            if not force and provider not in {"local", "ollama"} and not self._has_usable_api_key(profile):
                return
            if profile.name not in seen:
                seen.add(profile.name)
                candidates.append(profile)

        if hint.profile_name:
            profile = self.registry.profiles.get(hint.profile_name)
            _add(profile, force=hint.force_profile)

        if hint.agent_type:
            profile_name = self.registry.fixed_agent_routing.get(hint.agent_type)
            if profile_name:
                _add(self.registry.profiles.get(profile_name))

        if hint.action:
            profile_name = self.registry.action_routing.get(hint.action)
            if profile_name:
                _add(self.registry.profiles.get(profile_name))

        if hint.action:
            action_lower = hint.action.lower()
            if any(kw in action_lower for kw in self.REASONING_KEYWORDS):
                for name in self.registry.fallback_chain:
                    _add(self.registry.profiles.get(name))
            elif any(kw in action_lower for kw in self.UTILITY_KEYWORDS):
                for name in reversed(self.registry.fallback_chain):
                    _add(self.registry.profiles.get(name))

        default = self.registry.profiles.get(self.registry.default_profile)
        _add(default)

        for profile in self.registry.profiles.values():
            _add(profile)

        return candidates
