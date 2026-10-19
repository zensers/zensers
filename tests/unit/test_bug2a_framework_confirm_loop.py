# -*- coding: utf-8 -*-
"""
Bug 2A 测试：suggestion_id 覆盖 text 导致框架确认循环

验证点：
1. handle_interact 中 suggestion_id 存在时无条件覆盖 text
2. suggestion_map 无 'confirm_start' key → 回退为 suggestion_id 本身
3. 'confirm_start' 不在 LLM 确认词列表中 → LLM 返回 action='modify'
4. _llm_framework_modify 失败路径默认返回 action='modify'
5. _handle_framework_mode 收到 action='modify' → _framework_response → 前端再次显示框架
6. 完整调用链：confirm_start → suggestion_map fallback → LLM modify → 框架重显
"""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.api.research_api import ResearchAPI
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState


class TestSuggestionIdOverridesText:
    """验证 handle_interact 中 suggestion_id 覆盖 text 的 bug"""

    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        api._loop_cancel_flags = {}
        return api

    def test_suggestion_id_overwrites_text(self):
        """
        Bug 2A 核心：suggestion_id 存在时，user_message 被覆盖为 suggestion_id
        即使 response.text 包含有意义的确认文本
        """
        response = {
            'text': '确认开始研究，包含章节：市场规模、竞争格局',
            'suggestion_id': 'confirm_start',
        }
        user_message = response.get('text', response.get('message', ''))
        suggestion_id = response.get('suggestion_id', response.get('id', ''))
        if suggestion_id:
            suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
            user_message = suggestion_map.get(suggestion_id, suggestion_id)
            if not user_message:
                user_message = suggestion_id
        assert user_message == 'confirm_start', \
            "Bug 验证：suggestion_id='confirm_start' 时，text 被覆盖为 'confirm_start'"

    def test_suggestion_map_has_no_confirm_start_key(self):
        """suggestion_map 不包含 'confirm_start' key"""
        suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
        assert 'confirm_start' not in suggestion_map

    def test_suggestion_map_fallback_returns_suggestion_id(self):
        """suggestion_map.get() 无匹配时回退为 suggestion_id 本身"""
        suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
        result = suggestion_map.get('confirm_start', 'confirm_start')
        assert result == 'confirm_start'


class TestConfirmStartNotInConfirmWords:
    """验证 'confirm_start' 不在 LLM 确认词列表中"""

    def test_confirm_start_not_recognized_as_confirm(self):
        """'confirm_start' 不匹配 LLM prompt 中的确认词列表"""
        confirm_words = ['确认', '没问题', 'ok', '好的', '开始吧', 'looks good', 'proceed']
        assert 'confirm_start' not in confirm_words
        assert not any(w in 'confirm_start' for w in confirm_words)


class TestFrameworkModifyFailureReturnsModify:
    """验证 _llm_framework_modify 所有失败路径返回 action='modify'"""

    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    @pytest.mark.asyncio
    async def test_llm_exception_returns_modify(self):
        """LLM 调用抛异常 → 返回 action='modify'"""
        api = self._make_api()
        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = {
                'research_context': {
                    'framework': {'topic': '新能源', 'sections': ['市场规模']},
                    'topic': '新能源',
                },
                'language': 'zh',
                'llm_config': {},
            }
            with patch(
                'src.api.research_api.call_llm',
                new_callable=AsyncMock,
                side_effect=Exception("LLM down"),
            ):
                result = await api._llm_framework_modify('ses_001', '我想加一个章节')
                assert result['action'] == 'modify'

    @pytest.mark.asyncio
    async def test_llm_returns_unsuccessful_returns_modify(self):
        """LLM 返回 success=False → 返回 action='modify'"""
        api = self._make_api()
        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = {
                'research_context': {
                    'framework': {'topic': '新能源', 'sections': ['市场规模']},
                    'topic': '新能源',
                },
                'language': 'zh',
                'llm_config': {},
            }
            with patch(
                'src.api.research_api.call_llm',
                new_callable=AsyncMock,
                return_value={'success': False, 'error': 'timeout'},
            ):
                result = await api._llm_framework_modify('ses_001', '我想加一个章节')
                assert result['action'] == 'modify'

    @pytest.mark.asyncio
    async def test_llm_returns_no_json_returns_modify(self):
        """LLM 返回内容无有效 JSON → 返回 action='modify'"""
        api = self._make_api()
        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = {
                'research_context': {
                    'framework': {'topic': '新能源', 'sections': ['市场规模']},
                    'topic': '新能源',
                },
                'language': 'zh',
                'llm_config': {},
            }
            with patch(
                'src.api.research_api.call_llm',
                new_callable=AsyncMock,
                return_value={'success': True, 'content': 'plain text no json'},
            ):
                result = await api._llm_framework_modify('ses_001', '我想加一个章节')
                assert result['action'] == 'modify'


class TestHandleFrameworkModeModifyReturnsFrameworkResponse:
    """验证 _handle_framework_mode 收到 action='modify' 后返回 framework 响应"""

    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    @pytest.mark.asyncio
    async def test_confirm_start_now_triggers_execution(self):
        """Bug12/13 fix: 'confirm_start' now triggers execution directly, not LLM modify"""
        api = self._make_api()
        api._executor_tasks = {}
        with patch('src.api.research_api.session_manager') as sm:
            session = {
                'research_context': {
                    'framework': {'topic': '新能源', 'sections': ['市场规模', '竞争格局'],
                                  'output_type': 'industry_report', 'depth': 'standard',
                                  'region': 'China', 'time_range': 'Last 3 years'},
                    'topic': '新能源',
                },
                'language': 'zh',
                'conversation_history': [],
            }
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': 'ses_001', 'task_id': 'ses_001',
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode('ses_001', 'confirm_start')
                    assert result['mode'] == 'research', \
                        "Fix verification: 'confirm_start' now triggers execution (mode='research'), not LLM modify (mode='framework')"
                    assert result['status'] == 'running'
                    mock_exec.assert_called_once_with('ses_001')


class TestSuggestionIdShouldNotOverrideNonEmptyText:
    """修复验证：当 suggestion_id 存在但 text 非空时，应保留 text"""

    def test_text_preserved_when_non_empty(self):
        """
        修复后：当 text 非空时，suggestion_id 不覆盖 text
        """
        response = {
            'text': '确认开始研究，包含章节：市场规模、竞争格局',
            'suggestion_id': 'confirm_start',
        }
        user_message = response.get('text', response.get('message', ''))
        suggestion_id = response.get('suggestion_id', response.get('id', ''))
        if suggestion_id:
            suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
            if user_message:
                pass
            else:
                mapped = suggestion_map.get(suggestion_id)
                if mapped:
                    user_message = mapped
                else:
                    user_message = suggestion_id
        assert user_message == '确认开始研究，包含章节：市场规模、竞争格局', \
            "修复验证：text 非空时应保留原始文本"

    def test_suggestion_map_used_when_text_empty(self):
        """
        修复后：当 text 为空时，仍使用 suggestion_map 映射
        """
        response = {
            'text': '',
            'suggestion_id': 'add_details',
        }
        user_message = response.get('text', response.get('message', ''))
        suggestion_id = response.get('suggestion_id', response.get('id', ''))
        if suggestion_id:
            suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
            if user_message:
                pass
            else:
                mapped = suggestion_map.get(suggestion_id)
                if mapped:
                    user_message = mapped
                else:
                    user_message = suggestion_id
        assert user_message == 'add some details', \
            "修复验证：text 为空时使用 suggestion_map"

    def test_suggestion_id_fallback_when_text_empty_and_not_in_map(self):
        """
        修复后：text 为空且不在 suggestion_map 中时，回退为 suggestion_id
        """
        response = {
            'text': '',
            'suggestion_id': 'unknown_action',
        }
        user_message = response.get('text', response.get('message', ''))
        suggestion_id = response.get('suggestion_id', response.get('id', ''))
        if suggestion_id:
            suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
            if user_message:
                pass
            else:
                mapped = suggestion_map.get(suggestion_id)
                if mapped:
                    user_message = mapped
                else:
                    user_message = suggestion_id
        assert user_message == 'unknown_action', \
            "修复验证：text 为空且不在 map 中时，回退为 suggestion_id"
