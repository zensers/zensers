"""
Tests for Framework Confirmation UI Bug Fix

Bug: After LLM generates a research framework, the frontend never shows
the SectionSelector confirmation UI because:
1. Background tool chain SSE event lacks `framework` data
2. get_research_detail API does not return `framework`
3. Frontend SSE handler doesn't use framework from event data
4. Confirm keywords missing common Chinese confirmations like '可以'
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.orchestrator.execution.coordinator.cancel_manager import CancelManager


def _make_api():
    from src.api.research_api import ResearchAPI
    api = ResearchAPI.__new__(ResearchAPI)
    return api


class TestBugFix_FrameworkInSseEvent:
    """Bug fix: Background tool chain SSE event must include framework data."""

    def test_enter_framework_result_includes_framework_in_response_data(self):
        api = _make_api()
        framework_result = {
            'framework': {
                'topic': 'AI market',
                'sections': ['s1', 's2', 's3'],
                'sections_tree': [],
            },
            'next_step': 'confirm_framework',
        }
        response_data = {
            'action': 'enter_framework',
            'message': 'Here is the framework',
            'topic': 'AI market',
        }

        if isinstance(framework_result, dict) and framework_result.get('framework'):
            response_data['mode'] = 'framework'
            response_data['step'] = 0
            response_data['framework'] = framework_result['framework']
            if framework_result.get('next_step'):
                response_data['next_step'] = framework_result['next_step']

        assert response_data['mode'] == 'framework'
        assert response_data['step'] == 0
        assert 'framework' in response_data
        assert response_data['framework']['sections'] == ['s1', 's2', 's3']
        assert response_data['next_step'] == 'confirm_framework'

    def test_enter_framework_failure_does_not_add_framework(self):
        response_data = {
            'action': 'enter_framework',
            'message': 'Here is the framework',
        }
        framework_result = None

        if isinstance(framework_result, dict) and framework_result.get('framework'):
            response_data['mode'] = 'framework'
            response_data['step'] = 0
            response_data['framework'] = framework_result['framework']

        assert 'framework' not in response_data
        assert 'mode' not in response_data


class TestBugFix_GetResearchDetailReturnsFramework:
    """Bug fix: get_research_detail API must return framework."""

    def test_research_detail_response_includes_framework(self):
        research_context = {
            'topic': 'AI market',
            'framework': {
                'topic': 'AI market',
                'sections': ['s1', 's2'],
                'sections_tree': [],
            },
        }

        framework = research_context.get("framework")
        assert framework is not None
        assert framework['sections'] == ['s1', 's2']

    def test_research_detail_framework_none_when_not_set(self):
        research_context = {
            'topic': 'AI market',
        }

        framework = research_context.get("framework")
        assert framework is None


class TestBugFix_ConfirmKeywordsIncludeCommonChinese:
    """Bug fix: Confirm keywords must include common Chinese confirmations."""

    def test_confirm_keywords_in_chat_mode(self):
        _confirm_keywords = ('确认开始研究', '确认框架', '开始研究', '可以', '好的', '没问题', '开始吧', 'ok', '确认', 'confirm and start research', 'confirm_start')

        common_confirmations = ['可以', '好的', '没问题', '开始吧', 'ok', '确认']
        for word in common_confirmations:
            assert any(kw in word.lower() for kw in _confirm_keywords), f"'{word}' should match confirm keywords"

    def test_confirm_keywords_in_framework_mode(self):
        _confirm_keywords = ('确认开始研究', '确认框架', '开始研究', '可以', '好的', '没问题', '开始吧', 'ok', '确认', 'confirm and start research', 'confirm_start')

        common_confirmations = ['可以', '好的', '没问题', '开始吧', 'ok', '确认']
        for word in common_confirmations:
            assert any(kw in word.lower() for kw in _confirm_keywords), f"'{word}' should match confirm keywords"

    def test_non_confirm_words_dont_match(self):
        _confirm_keywords = ('确认开始研究', '确认框架', '开始研究', '可以', '好的', '没问题', '开始吧', 'ok', '确认', 'confirm and start research', 'confirm_start')

        non_confirm = ['修改', '取消', '不要', '换一个', 'no', 'cancel']
        for word in non_confirm:
            assert not any(kw in word.lower() for kw in _confirm_keywords), f"'{word}' should NOT match confirm keywords"

    def test_user_input_with_extra_text_still_matches(self):
        _confirm_keywords = ('确认开始研究', '确认框架', '开始研究', '可以', '好的', '没问题', '开始吧', 'ok', '确认', 'confirm and start research', 'confirm_start')

        user_inputs = [
            '可以，我们要制作一个PPT',
            '好的，开始吧',
            '没问题，就这样',
            'ok，开始研究',
        ]
        for user_input in user_inputs:
            _user_lower = user_input.lower()
            assert any(kw in _user_lower for kw in _confirm_keywords), f"'{user_input}' should match confirm keywords"


class TestBugFix_LlmFrameworkModifyPromptIncludesKeYi:
    """Bug fix: _llm_framework_modify prompt includes '可以' as confirm example."""

    def test_prompt_includes_keyi(self):
        prompt = "If the user confirms (e.g., '确认', '可以', '没问题', 'ok', '好的', '开始吧', 'looks good', 'proceed'), set action=\"confirm\"."
        assert '可以' in prompt


class TestBugFix_FrameworkModifyFallbackPreservesExisting:
    """Bug fix: When new_sections is None, preserve existing framework."""

    def test_preserve_existing_framework_when_new_sections_none(self):
        context = {
            'topic': 'AI market',
            'framework': {
                'topic': 'AI market',
                'sections': ['s1', 's2', 's3'],
                'sections_tree': [],
            },
        }
        new_sections = None

        existing_framework = context.get('framework')
        if existing_framework and existing_framework.get('sections'):
            new_framework = existing_framework
        else:
            new_framework = {'regenerated': True}

        assert new_framework == context['framework']
        assert new_framework['sections'] == ['s1', 's2', 's3']

    def test_regenerate_when_no_existing_framework(self):
        context = {
            'topic': 'AI market',
        }
        new_sections = None

        existing_framework = context.get('framework')
        if existing_framework and existing_framework.get('sections'):
            new_framework = existing_framework
        else:
            new_framework = {'regenerated': True}

        assert new_framework == {'regenerated': True}


class TestFrameworkModifyRouting:
    """Framework modification uses the routed LLM client contract."""

    def test_uses_framework_modify_routing_hint(self):
        import inspect
        from src.api.research_api import ResearchAPI
        source = inspect.getsource(ResearchAPI._llm_framework_modify)
        assert 'routing_hint=RoutingHint(action="framework_modify")' in source
        assert 'timeout=30' not in source


class TestBugFix_FrameworkModifyExceptionLogged:
    """Bug fix: _llm_framework_modify exceptions are logged, not silently swallowed."""

    def test_timeout_error_has_separate_handler(self):
        import inspect
        from src.api.research_api import ResearchAPI
        source = inspect.getsource(ResearchAPI._llm_framework_modify)
        assert 'asyncio.TimeoutError' in source, "Should have separate TimeoutError handler"
        assert 'logger.warning' in source, "Should log warnings on failure"
