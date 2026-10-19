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


class TestEngineRetryHelperTokenBudget:
    """Output-size budgeting now lives in call_llm_ex (base_max_tokens +
    Budget.scale_to); the research_api helper only forwards the size hint."""

    @pytest.mark.asyncio
    async def test_forwards_expected_output_chars(self):
        from src.api.research_api import _llm_call_with_engine_retry
        captured = {}

        async def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return {"message": "ok"}

        with patch('src.api.research_api.call_llm_ex', side_effect=fake_ex):
            result = await _llm_call_with_engine_retry(
                prompt_builder="P", expected_output_chars=9999)

        assert captured.get('expected_output_chars') == 9999, \
               f"size hint should be forwarded to the engine, got: {captured}"
        assert result == {"message": "ok"}

    @pytest.mark.asyncio
    async def test_default_expected_output_chars(self):
        from src.api.research_api import _llm_call_with_engine_retry
        captured = {}

        async def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return {"message": "ok"}

        with patch('src.api.research_api.call_llm_ex', side_effect=fake_ex):
            await _llm_call_with_engine_retry(prompt_builder="P")

        assert captured.get('expected_output_chars') == 1500, \
               f"default size hint should be 1500, got: {captured}"


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
    async def test_infer_uses_intrinsic_call_llm(self):
        api = self._make_api()
        mock_session = {
            'research_context': {'topic': 'AI market'},
            'conversation_history': [{'role': 'user', 'content': 'Tell me about AI'}],
            'language': 'en',
        }

        mock_call_llm = AsyncMock(return_value={
            'success': True, 'content': '["Market Size", "Competition"]'
        })

        with patch('src.api.research_api.session_manager') as mock_sm:
            mock_sm.get.return_value = mock_session
            with patch('src.core.llm_client.call_llm', mock_call_llm):
                result = await api._infer_framework_sections_from_conversation('sess1')

        call_args = mock_call_llm.call_args
        assert call_args is not None, "call_llm was not called"
        assert call_args.kwargs["routing_hint"].action == "section_inference"
        assert result == ["Market Size", "Competition"]


class TestNoHardcodedMaxTokensAnywhere:
    def test_no_numeric_max_tokens_in_source(self):
        from src.api.research_api import ResearchAPI
        import inspect
        source = inspect.getsource(ResearchAPI)
        import re
        matches = re.findall(r'max_tokens\s*=\s*\d+', source)
        assert len(matches) == 0, \
               f"Found hardcoded max_tokens in ResearchAPI source: {matches}"
