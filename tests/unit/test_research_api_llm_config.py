# -*- coding: utf-8 -*-
"""
Integration tests for ResearchAPI LLM call paths.

Verifies that max_tokens is read from config (not hardcoded)
in all LLM invocation branches, and that the module imports cleanly.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestResearchAPIImportSmoke:
    def test_module_imports_without_syntax_error(self):
        import src.api.research_api


class TestRetryJsonOnlyMaxTokens:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    @pytest.mark.asyncio
    async def test_uses_config_max_tokens(self):
        api = self._make_api()
        llm_config = {'model': 'test-model', 'max_tokens': 9999}
        mock_settings = MagicMock()
        mock_settings.llm.model = 'default-model'
        mock_settings.llm.max_tokens = 4096

        mock_call_llm = AsyncMock(return_value={'success': True, 'content': '{"message":"ok"}'})
        with patch('src.api.research_api.call_llm', mock_call_llm):
            with patch('src.api.research_api.asyncio.wait_for', side_effect=lambda coro, timeout: coro):
                with patch('src.api.research_api.app_settings', mock_settings, create=True):
                    result = await api._retry_json_only('sys', llm_config, 'sess1')

        call_kwargs = mock_call_llm.call_args.kwargs if mock_call_llm.call_args else {}
        assert call_kwargs.get('max_tokens') == 9999, \
               f"max_tokens should come from llm_config, got: {call_kwargs}"

    @pytest.mark.asyncio
    async def test_falls_back_to_settings_max_tokens(self):
        api = self._make_api()
        llm_config = {'model': 'test-model'}
        mock_settings = MagicMock()
        mock_settings.llm.model = 'default-model'
        mock_settings.llm.max_tokens = 4096

        mock_call_llm = AsyncMock(return_value={'success': True, 'content': '{"message":"ok"}'})
        with patch('src.api.research_api.call_llm', mock_call_llm):
            with patch('src.api.research_api.asyncio.wait_for', side_effect=lambda coro, timeout: coro):
                with patch('src.api.research_api.app_settings', mock_settings, create=True):
                    result = await api._retry_json_only('sys', llm_config, 'sess1')

        call_kwargs = mock_call_llm.call_args.kwargs if mock_call_llm.call_args else {}
        assert call_kwargs.get('max_tokens') == 4096, \
               f"max_tokens should fall back to app_settings.llm.max_tokens (4096), got: {call_kwargs}"


class TestToolResultSynthesisMaxTokens:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    @pytest.mark.asyncio
    async def test_no_hardcoded_max_tokens_in_synthesis(self):
        from src.api.research_api import ResearchAPI
        import inspect
        source = inspect.getsource(ResearchAPI)
        import re
        matches = re.findall(r'max_tokens\s*=\s*(\d+)', source)
        assert len(matches) == 0, \
               f"Found hardcoded max_tokens values in ResearchAPI: {matches}. All should use config."


class TestFrameworkSectionInferenceMaxTokens:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    @pytest.mark.asyncio
    async def test_infer_uses_settings_max_tokens(self):
        api = self._make_api()
        mock_settings = MagicMock()
        mock_settings.llm.model = 'default-model'
        mock_settings.llm.max_tokens = 4096

        mock_session = {
            'research_context': {'topic': 'AI market'},
            'conversation_history': [{'role': 'user', 'content': 'Tell me about AI'}],
            'language': 'en',
        }

        llm_skill_instance = AsyncMock()
        llm_skill_instance.execute.return_value = {
            'success': True, 'content': '["Market Size", "Competition"]'
        }
        mock_llm_class = MagicMock(return_value=llm_skill_instance)

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = mock_session
            with patch('src.skills.llm_skill.LLMSkill', mock_llm_class):
                with patch('src.config.settings.settings', mock_settings):
                    result = await api._infer_framework_sections_from_conversation('sess1')

        call_args = llm_skill_instance.execute.call_args
        assert call_args is not None, "llm_skill.execute was not called"
        max_tokens_used = call_args.kwargs.get('max_tokens')
        assert max_tokens_used == 4096, \
               f"max_tokens should use app_settings.llm.max_tokens (4096), got: {max_tokens_used}"


class TestNoHardcodedMaxTokensAnywhere:
    def test_no_numeric_max_tokens_in_source(self):
        from src.api.research_api import ResearchAPI
        import inspect
        source = inspect.getsource(ResearchAPI)
        import re
        matches = re.findall(r'max_tokens\s*=\s*\d+', source)
        assert len(matches) == 0, \
               f"Found hardcoded max_tokens in ResearchAPI source: {matches}"
