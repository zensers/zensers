import pytest
import json
from pathlib import Path
from unittest.mock import patch
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry
from src.config.settings import Settings


@pytest.fixture(autouse=True)
def reset_settings(tmp_path):
    Settings._reset_instance()
    s = Settings()
    s._llm_profiles_persist_path = str(tmp_path / "llm_profiles.json")
    s.llm_profiles = LLMProfileRegistry(default_profile="migrated")
    s._migrate_legacy_to_profile()
    yield
    Settings._reset_instance()


class TestProfileDiskPersistence:
    def test_persist_profiles_writes_json(self, tmp_path):
        persist_path = str(tmp_path / "llm_profiles.json")
        s = Settings()
        s._llm_profiles_persist_path = persist_path
        s.add_llm_profile(LLMProfile(name="deepseek", model="gpt-4o", api_key="sk-s"))
        s._persist_llm_profiles()
        data = json.loads(Path(persist_path).read_text(encoding="utf-8"))
        assert "profiles" in data
        assert "deepseek" in data["profiles"]
        assert data["profiles"]["deepseek"]["model"] == "gpt-4o"

    def test_load_profiles_from_disk(self, tmp_path):
        persist_path = str(tmp_path / "llm_profiles.json")
        data = {
            "default_profile": "zhipu",
            "fallback_chain": ["deepseek", "zhipu"],
            "fixed_agent_routing": {"quality_check": "deepseek"},
            "action_routing": {"analyze": "deepseek"},
            "profiles": {
                "zhipu": {"name": "zhipu", "model": "gpt-4o-mini", "api_key": "sk-f", "base_url": "https://f.api/v1"},
                "deepseek": {"name": "deepseek", "model": "gpt-4o", "api_key": "sk-s", "base_url": "https://s.api/v1"},
            },
        }
        Path(persist_path).write_text(json.dumps(data), encoding="utf-8")
        s = Settings()
        s._llm_profiles_persist_path = persist_path
        s._load_llm_profiles_from_disk()
        assert "zhipu" in s.llm_profiles.profiles
        assert "deepseek" in s.llm_profiles.profiles
        assert s.llm_profiles.default_profile == "zhipu"
        assert s.llm_profiles.profiles["deepseek"].model == "gpt-4o"

    def test_persist_and_load_roundtrip(self, tmp_path):
        persist_path = str(tmp_path / "llm_profiles.json")
        s = Settings()
        s._llm_profiles_persist_path = persist_path
        s.add_llm_profile(LLMProfile(name="deepseek", model="gpt-4o", api_key="sk-s", base_url="https://s.api/v1"))
        s.add_llm_profile(LLMProfile(name="zhipu", model="gpt-4o-mini", api_key="sk-f", base_url="https://f.api/v1"))
        s._persist_llm_profiles()

        Settings._reset_instance()
        s2 = Settings()
        s2._llm_profiles_persist_path = persist_path
        s2._load_llm_profiles_from_disk()
        assert "deepseek" in s2.llm_profiles.profiles
        assert "zhipu" in s2.llm_profiles.profiles
        assert s2.llm_profiles.profiles["deepseek"].model == "gpt-4o"

    def test_no_persist_path_skips_silently(self):
        s = Settings()
        s._llm_profiles_persist_path = ""
        s._persist_llm_profiles()

    def test_corrupt_json_skips_with_warning(self, tmp_path):
        persist_path = str(tmp_path / "llm_profiles.json")
        Path(persist_path).write_text("{bad json", encoding="utf-8")
        s = Settings()
        s._llm_profiles_persist_path = persist_path
        s._load_llm_profiles_from_disk()
        assert "migrated" in s.llm_profiles.profiles


class TestLegacyMigration:
    def test_migrate_creates_migrated_profile_from_llm_config(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_CHEAP_MODEL", raising=False)
        monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
        monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
        llm_path = str(tmp_path / "llm_config.json")
        data = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-legacy",
            "api_endpoint": "https://legacy.api/v1",
            "temperature": 0.5,
            "max_tokens": 8192,
            "cheap_model": "gpt-3.5-turbo",
        }
        Path(llm_path).write_text(json.dumps(data), encoding="utf-8")
        Settings._reset_instance()
        s = Settings()
        s._llm_config_persist_path = llm_path
        s._load_llm_config_from_disk()
        # The normal Settings instance already contains YAML-defined
        # profiles.  Isolate the legacy migration contract so the test does
        # not depend on the repository's configured profile set.
        s.llm_profiles = LLMProfileRegistry(default_profile="migrated")
        s._migrate_legacy_to_profile()
        migrated = s.llm_profiles.profiles["migrated"]
        assert migrated.model == "gpt-4o"
        assert migrated.api_key == "sk-legacy"
        assert migrated.base_url == "https://legacy.api/v1"
        assert migrated.fallback_model == "gpt-3.5-turbo"
        assert migrated.temperature == 0.5
        assert migrated.max_tokens == 8192

    def test_migrate_skips_if_migrated_already_exists(self):
        s = Settings()
        assert "migrated" in s.llm_profiles.profiles
        original_model = s.llm_profiles.profiles["migrated"].model
        s._migrate_legacy_to_profile()
        assert s.llm_profiles.profiles["migrated"].model == original_model
