"""LLM Config API 端点测试"""

import pytest
import os
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """创建只包含 LLM config 路由的测试 app"""
    from fastapi import FastAPI
    from typing import Dict, Any

    app = FastAPI()

    @app.get("/api/v1/llm/config")
    async def get_llm_config():
        from src.config.settings import Settings
        s = Settings(config_path="nonexistent.toml")
        return {
            "provider": s.llm.provider,
            "model": s.llm.model,
            "apiEndpoint": s.llm.base_url,
            "apiKey": s.llm.api_key,
            "temperature": s.llm.temperature,
            "maxTokens": s.llm.max_tokens,
            "topP": s.llm.top_p,
            "frequencyPenalty": s.llm.frequency_penalty,
            "presencePenalty": s.llm.presence_penalty,
            "hasApiKey": bool(s.llm.api_key),
        }

    @app.post("/api/v1/llm/config")
    async def update_llm_config(config: Dict[str, Any]):
        from src.config.settings import Settings
        s = Settings(config_path="nonexistent.toml")
        s.update_from_request(config)
        return {
            "provider": s.llm.provider,
            "model": s.llm.model,
            "apiEndpoint": s.llm.base_url,
            "apiKey": s.llm.api_key,
            "temperature": s.llm.temperature,
            "maxTokens": s.llm.max_tokens,
            "topP": s.llm.top_p,
            "frequencyPenalty": s.llm.frequency_penalty,
            "presencePenalty": s.llm.presence_penalty,
            "hasApiKey": bool(s.llm.api_key),
        }

    @app.post("/api/v1/llm/config/reset")
    async def reset_llm_config():
        from src.config.settings import Settings
        s = Settings(config_path="nonexistent.toml")
        s.reset_llm_to_env()
        return {
            "provider": s.llm.provider,
            "model": s.llm.model,
            "apiEndpoint": s.llm.base_url,
            "apiKey": s.llm.api_key,
            "temperature": s.llm.temperature,
            "maxTokens": s.llm.max_tokens,
            "topP": s.llm.top_p,
            "frequencyPenalty": s.llm.frequency_penalty,
            "presencePenalty": s.llm.presence_penalty,
            "hasApiKey": bool(s.llm.api_key),
        }

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


_ENV_DEFAULTS = {
    "LLM_PROVIDER": "test-provider",
    "LLM_MODEL": "test-model",
    "LLM_API_KEY": "test-api-key",
    "LLM_BASE_URL": "https://test.api.com/v1",
    "LLM_CHEAP_MODEL": "test-cheap",
    "LLM_EMBEDDING_MODEL": "test-embedding",
    "DB_USER": "",
    "DB_PASSWORD": "",
}


class TestGetLLMConfig:
    """GET /api/v1/llm/config"""

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_get_config_returns_all_fields(self, client):
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "test-provider"
        assert data["model"] == "test-model"
        assert data["apiEndpoint"] == "https://test.api.com/v1"
        assert data["apiKey"] == "test-api-key"
        assert data["hasApiKey"] is True
        assert isinstance(data["temperature"], float)
        assert isinstance(data["maxTokens"], int)
        assert isinstance(data["topP"], float)

    @patch.dict(os.environ, {k: v for k, v in _ENV_DEFAULTS.items() if k != "LLM_API_KEY"}, clear=True)
    def test_get_config_has_api_key_false_when_empty(self, client):
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        assert resp.json()["hasApiKey"] is False
        assert resp.json()["apiKey"] == ""


class TestUpdateLLMConfig:
    """POST /api/v1/llm/config"""

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_all_fields(self, client):
        payload = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "sk-ant-xxx",
            "api_endpoint": "https://api.anthropic.com/v1",
            "temperature": 0.3,
            "max_tokens": 8192,
            "top_p": 0.95,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.2,
        }
        resp = client.post("/api/v1/llm/config", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-3-5-sonnet-20241022"
        assert data["apiKey"] == "sk-ant-xxx"
        assert data["apiEndpoint"] == "https://api.anthropic.com/v1"
        assert data["temperature"] == 0.3
        assert data["maxTokens"] == 8192
        assert data["topP"] == 0.95
        assert data["frequencyPenalty"] == 0.5
        assert data["presencePenalty"] == 0.2
        assert data["hasApiKey"] is True

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_partial(self, client):
        resp = client.post("/api/v1/llm/config", json={"temperature": 0.1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["temperature"] == 0.1
        assert data["provider"] == _ENV_DEFAULTS["LLM_PROVIDER"]

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_empty_body(self, client):
        resp = client.post("/api/v1/llm/config", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == _ENV_DEFAULTS["LLM_PROVIDER"]

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_empty_string_clears_api_key(self, client):
        resp = client.post("/api/v1/llm/config", json={"api_key": ""})
        assert resp.status_code == 200
        assert resp.json()["apiKey"] == ""


class TestResetLLMConfig:
    """POST /api/v1/llm/config/reset"""

    @patch.dict(os.environ, {
        **_ENV_DEFAULTS,
        "LLM_PROVIDER": "deepseek",
        "LLM_MODEL": "deepseek-v4-pro",
        "LLM_API_KEY": "sk-reset-key",
    }, clear=True)
    def test_reset_restores_env_values(self, client):
        # Change to something else first
        client.post("/api/v1/llm/config", json={
            "provider": "openai",
            "model": "gpt-4o",
        })

        resp = client.post("/api/v1/llm/config/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-v4-pro"
        assert data["apiKey"] == "sk-reset-key"
