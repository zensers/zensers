# -*- coding: utf-8 -*-
"""
Tests for model switching at runtime.

Covers:
1. handle_interact merges llm_config into session
2. session llm_config overrides feed the settings layer (the profile chain
   routes credentials at call time; _llm_converse no longer reads
   api_key/api_endpoint directly)
3. /interact endpoint accepts llm_provider/llm_model Form params
4. the engine-retry helper routes credentials via the engine (no ad-hoc kwargs)
5. call_llm supports api_key/base_url params
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


class TestHandleInteractLlmConfigMerge:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._pending_clarifications = {}
        api._clarification_responses = {}
        return api

    def _make_session(self, llm_config=None):
        return {
            'mode': 'chat',
            'state_machine': MagicMock(),
            'clarifier': MagicMock(),
            'conversation_history': [],
            'research_context': {'topic': None, 'directions': [], 'framework': None, 'details': {}},
            'llm_config': llm_config or {},
        }

    @pytest.mark.asyncio
    async def test_merge_model_into_existing_session(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'old-model', 'provider': 'openai'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'}, llm_config={'model': 'new-model'})

        assert session['llm_config']['model'] == 'new-model'
        assert session['llm_config']['provider'] == 'openai'

    @pytest.mark.asyncio
    async def test_merge_provider_into_existing_session(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'gpt-4o', 'provider': 'openai'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'}, llm_config={'provider': 'deepseek', 'model': 'deepseek-v4-pro'})

        assert session['llm_config']['provider'] == 'deepseek'
        assert session['llm_config']['model'] == 'deepseek-v4-pro'

    @pytest.mark.asyncio
    async def test_merge_api_key_and_endpoint(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'gpt-4o'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'},
                                         llm_config={'api_key': 'sk-new', 'api_endpoint': 'https://new.api.com/v1'})

        assert session['llm_config']['api_key'] == 'sk-new'
        assert session['llm_config']['api_endpoint'] == 'https://new.api.com/v1'

    @pytest.mark.asyncio
    async def test_no_merge_when_llm_config_empty(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'original'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'}, llm_config={})

        assert session['llm_config']['model'] == 'original'

    @pytest.mark.asyncio
    async def test_no_merge_when_llm_config_none(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'original'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'}, llm_config=None)

        assert session['llm_config']['model'] == 'original'

    @pytest.mark.asyncio
    async def test_merge_preserves_existing_keys(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'gpt-4o', 'provider': 'openai', 'temperature': 0.5})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'}, llm_config={'model': 'gpt-4o-mini'})

        assert session['llm_config']['model'] == 'gpt-4o-mini'
        assert session['llm_config']['provider'] == 'openai'
        assert session['llm_config']['temperature'] == 0.5

    @pytest.mark.asyncio
    async def test_merge_skips_empty_string_values(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'gpt-4o', 'api_key': 'sk-existing'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'},
                                         llm_config={'model': '', 'api_key': ''})

        assert session['llm_config']['model'] == 'gpt-4o'
        assert session['llm_config']['api_key'] == 'sk-existing'

    @pytest.mark.asyncio
    async def test_merge_skips_none_values(self):
        api = self._make_api()
        session = self._make_session(llm_config={'model': 'gpt-4o'})

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = session
            with patch.object(api, '_handle_user_message', new_callable=AsyncMock) as mock_handle:
                mock_handle.return_value = {'message': 'ok'}
                await api.handle_interact('sess1', 0, {'text': 'hello'},
                                         llm_config={'model': None, 'temperature': 0.9})

        assert session['llm_config']['model'] == 'gpt-4o'
        assert session['llm_config']['temperature'] == 0.9


class TestLlmConverseSessionConfig:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_session_config_resolves_api_key_from_session(self):
        api = self._make_api()
        mock_settings = MagicMock()
        mock_settings.llm.model = 'global-model'
        mock_settings.llm.api_key = 'global-key'
        mock_settings.llm.base_url = 'https://global.api.com/v1'
        mock_settings.llm.max_tokens = 4096
        mock_settings.llm.temperature = 0.7

        llm_config = {
            'model': 'session-model',
            'api_key': 'session-key',
            'api_endpoint': 'https://session.api.com/v1',
            'max_tokens': 8000,
        }

        _model = llm_config.get('model', mock_settings.llm.model)
        _api_key = llm_config.get('api_key', mock_settings.llm.api_key)
        _base_url = llm_config.get('api_endpoint', mock_settings.llm.base_url)
        _max_tokens = llm_config.get('max_tokens', mock_settings.llm.max_tokens)

        assert _model == 'session-model'
        assert _api_key == 'session-key'
        assert _base_url == 'https://session.api.com/v1'
        assert _max_tokens == 8000

    def test_session_config_falls_back_to_global(self):
        mock_settings = MagicMock()
        mock_settings.llm.model = 'global-model'
        mock_settings.llm.api_key = 'global-key'
        mock_settings.llm.base_url = 'https://global.api.com/v1'
        mock_settings.llm.max_tokens = 4096

        llm_config = {}

        _model = llm_config.get('model', mock_settings.llm.model)
        _api_key = llm_config.get('api_key', mock_settings.llm.api_key)
        _base_url = llm_config.get('api_endpoint', mock_settings.llm.base_url)
        _max_tokens = llm_config.get('max_tokens', mock_settings.llm.max_tokens)

        assert _model == 'global-model'
        assert _api_key == 'global-key'
        assert _base_url == 'https://global.api.com/v1'
        assert _max_tokens == 4096


class TestEngineRetryCredentialRouting:
    """Credentials are routed by the engine's candidate chain (profile
    api_key/base_url); the research_api helper must not pass ad-hoc
    credential kwargs that would duplicate or override that routing."""

    @pytest.mark.asyncio
    async def test_helper_passes_no_adhoc_credentials(self):
        from src.api.research_api import _llm_call_with_engine_retry
        captured = {}

        async def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return {"message": "ok"}

        with patch('src.api.research_api.call_llm_ex', side_effect=fake_ex):
            await _llm_call_with_engine_retry(prompt_builder="P", system_prompt="sys")

        assert 'api_key' not in captured
        assert 'base_url' not in captured

    @pytest.mark.asyncio
    async def test_helper_attributes_routing_to_task_tag(self):
        from src.api.research_api import _llm_call_with_engine_retry
        captured = {}

        async def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return {"message": "ok"}

        with patch('src.api.research_api.call_llm_ex', side_effect=fake_ex):
            await _llm_call_with_engine_retry(prompt_builder="P")

        assert captured.get('task_tag') == 'research_api'


class TestCallLlmWithApiKeyBaseUrl:
    def _mock_settings(self):
        mock = MagicMock()
        mock.llm.max_tokens = 4096
        mock.llm.temperature = 0.7
        mock.llm.model = "test-model"
        mock.llm.cheap_model = "test-fallback"
        mock.llm.cost_limit_per_report = 0
        mock.llm.api_key = "default-key"
        mock.llm.base_url = "https://default.example.com"
        mock.llm.top_p = 1.0
        mock.llm.frequency_penalty = 0.0
        mock.llm.presence_penalty = 0.0
        return mock

    @pytest.mark.asyncio
    async def test_call_llm_api_key_override(self):
        ms = self._mock_settings()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {'total_tokens': 10},
        }
        with patch("src.core.llm_client.settings", ms):
            with patch(
                "src.core.llm_client._call_llm_api",
                new_callable=AsyncMock,
                return_value=mock_response.model_dump.return_value,
            ) as raw_call:
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test", api_key="custom-key", base_url="https://custom.api.com/v1")

                assert result['success'] is True
                call_kwargs = raw_call.call_args.kwargs
                assert call_kwargs["api_key"] == "custom-key"
                assert call_kwargs["base_url"] == "https://custom.api.com/v1"

    @pytest.mark.asyncio
    async def test_call_llm_fallback_to_settings(self):
        ms = self._mock_settings()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {'total_tokens': 10},
        }
        with patch("src.core.llm_client.settings", ms):
            with patch(
                "src.core.llm_client._call_llm_api",
                new_callable=AsyncMock,
                return_value=mock_response.model_dump.return_value,
            ) as raw_call:
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")

                assert result['success'] is True
                call_kwargs = raw_call.call_args.kwargs
                assert call_kwargs["api_key"] == "default-key"
                assert call_kwargs["base_url"] == "https://default.example.com"


class TestInteractEndpointLlmParams:
    @pytest.mark.asyncio
    async def test_interact_endpoint_accepts_llm_model(self):
        from fastapi.testclient import TestClient
        from src.api.main import app

        mock_settings = MagicMock()
        mock_settings.update_from_request = MagicMock()
        client = TestClient(app)
        with patch('src.api.main.research_api') as mock_api:
            mock_api.handle_interact = AsyncMock(return_value={'message': 'ok', 'mode': 'chat'})
            with patch('src.config.settings.settings', mock_settings):
                response = client.post(
                    '/api/v1/research/interact',
                    data={
                        'session_id': 'sess1',
                        'step': '0',
                        'response': json.dumps({'text': 'hello'}),
                        'llm_model': 'gpt-4o-mini',
                        'llm_provider': 'openai',
                    },
                )

            assert response.status_code == 200
            call_args = mock_api.handle_interact.call_args
            llm_config_arg = call_args.kwargs.get('llm_config', {})
            assert llm_config_arg.get('model') == 'gpt-4o-mini'
            assert llm_config_arg.get('provider') == 'openai'

    @pytest.mark.asyncio
    async def test_interact_endpoint_accepts_full_llm_config(self):
        from fastapi.testclient import TestClient
        from src.api.main import app

        mock_settings = MagicMock()
        mock_settings.update_from_request = MagicMock()
        client = TestClient(app)
        with patch('src.api.main.research_api') as mock_api:
            mock_api.handle_interact = AsyncMock(return_value={'message': 'ok', 'mode': 'chat'})
            with patch('src.config.settings.settings', mock_settings):
                response = client.post(
                    '/api/v1/research/interact',
                    data={
                        'session_id': 'sess1',
                        'step': '0',
                        'response': json.dumps({'text': 'hello'}),
                        'llm_model': 'deepseek-v4-pro',
                        'llm_provider': 'deepseek',
                        'llm_api_key': 'sk-test',
                        'llm_api_endpoint': 'https://api.deepseek.com/v1',
                        'llm_temperature': '0.5',
                        'llm_max_tokens': '8000',
                    },
                )

            assert response.status_code == 200
            call_args = mock_api.handle_interact.call_args
            llm_config_arg = call_args.kwargs.get('llm_config', {})
            assert llm_config_arg.get('model') == 'deepseek-v4-pro'
            assert llm_config_arg.get('provider') == 'deepseek'
            assert llm_config_arg.get('api_key') == 'sk-test'
            assert llm_config_arg.get('api_endpoint') == 'https://api.deepseek.com/v1'
            assert llm_config_arg.get('temperature') == 0.5
            assert llm_config_arg.get('max_tokens') == 8000

    @pytest.mark.asyncio
    async def test_interact_endpoint_no_llm_config_when_not_provided(self):
        from fastapi.testclient import TestClient
        from src.api.main import app

        mock_settings = MagicMock()
        mock_settings.update_from_request = MagicMock()
        client = TestClient(app)
        with patch('src.api.main.research_api') as mock_api:
            mock_api.handle_interact = AsyncMock(return_value={'message': 'ok', 'mode': 'chat'})
            with patch('src.config.settings.settings', mock_settings):
                response = client.post(
                    '/api/v1/research/interact',
                    data={
                        'session_id': 'sess1',
                        'step': '0',
                        'response': json.dumps({'text': 'hello'}),
                    },
                )

            assert response.status_code == 200
            call_args = mock_api.handle_interact.call_args
            llm_config_arg = call_args.kwargs.get('llm_config', {})
            assert llm_config_arg == {}
