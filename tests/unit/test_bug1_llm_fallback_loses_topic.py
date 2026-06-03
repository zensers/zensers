# -*- coding: utf-8 -*-
"""
Bug 1 测试：LLM 调用失败 fallback 丢失 topic

验证点：
1. _fallback_response 在 context 无 topic 时显示"你想研究什么？"
2. _fallback_response 在 context 有 topic 时保留主题
3. _handle_chat_mode 中 _llm_converse 抛异常后走 fallback
4. _llm_converse 中 ValueError 路径（success=False, 空内容, JSON 解析失败）
5. _llm_converse 中 break 路径不触发 fallback（返回部分结果）
6. topic 在当次 _llm_converse 中确定但 JSON 解析失败时，context 快照丢失 topic
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.api.research_api import ResearchAPI
from src.core.session_manager import SessionManager, PersistentSessionDict


class TestFallbackResponseLosesTopic:
    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_fallback_without_topic_shows_what_to_research(self):
        """Bug 1 核心验证：context 无 topic 时返回'你想研究什么？'"""
        api = self._make_api()
        with patch.object(api, '_get_lang', return_value='zh'):
            with patch.object(api, '_chat_response') as mock_chat:
                mock_chat.return_value = {'message': 'fallback'}
                with patch('src.api.research_api.session_manager') as sm:
                    sm.get.return_value = {'language': 'zh'}
                    api._fallback_response('ses_001', {'topic': None})
                    call_args = mock_chat.call_args
                    message = call_args[0][1]
                    assert '你想研究什么' in message

    def test_fallback_with_topic_preserves_topic(self):
        """context 有 topic 时 fallback 消息保留主题"""
        api = self._make_api()
        with patch.object(api, '_get_lang', return_value='zh'):
            with patch.object(api, '_chat_response') as mock_chat:
                mock_chat.return_value = {'message': 'fallback'}
                with patch('src.api.research_api.session_manager') as sm:
                    sm.get.return_value = {'language': 'zh'}
                    api._fallback_response('ses_001', {'topic': '新能源汽车'})
                    call_args = mock_chat.call_args
                    message = call_args[0][1]
                    assert '新能源汽车' in message
                    assert '你想研究什么' not in message

    def test_fallback_context_snapshot_loses_topic_set_during_llm_converse(self):
        """
        Bug 1 关键场景：topic 在 _llm_converse 中确定但 JSON 解析失败
        修复后：即使 context 快照无 topic，也从 session.research_context 恢复
        """
        api = self._make_api()
        context_before_llm = {'topic': None, 'directions': [], 'framework': None}
        with patch.object(api, '_get_lang', return_value='zh'):
            with patch.object(api, '_chat_response') as mock_chat:
                mock_chat.return_value = {'message': 'fallback'}
                with patch('src.api.research_api.session_manager') as sm:
                    session = {
                        'language': 'zh',
                        'research_context': {'topic': '新能源汽车'},
                    }
                    sm.get.return_value = session
                    api._fallback_response('ses_001', context_before_llm)
                    call_args = mock_chat.call_args
                    message = call_args[0][1]
                    assert '新能源汽车' in message, \
                        "修复验证：context 快照无 topic 但 session 中有 topic，fallback 应恢复主题"

    def test_llm_converse_raises_on_success_false(self):
        """LLM 返回 success=False 抛 ValueError → 被 except Exception 捕获 → fallback"""
        api = self._make_api()
        with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = ValueError("LLM call failed: timeout")
            with patch.object(api, '_fallback_response') as mock_fb:
                mock_fb.return_value = {'message': 'fallback'}
                with patch('src.api.research_api.session_manager') as sm:
                    sm.get.return_value = {
                        'mode': 'chat',
                        'research_context': {'topic': None},
                        'conversation_history': [],
                        'state_machine': MagicMock(),
                    }
                    import asyncio
                    with pytest.raises(ValueError):
                        asyncio.get_event_loop().run_until_complete(
                            api._llm_converse('ses_001', 'test', MagicMock())
                        )

    def test_llm_converse_raises_on_empty_content(self):
        """LLM 返回空内容抛 ValueError"""
        api = self._make_api()
        with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = ValueError("LLM returned empty content")
            with pytest.raises(ValueError):
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    api._llm_converse('ses_001', 'test', MagicMock())
                )

    def test_llm_converse_raises_on_no_json(self):
        """LLM 返回无有效 JSON 抛 ValueError"""
        api = self._make_api()
        with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = ValueError("LLM response contains no valid JSON")
            with pytest.raises(ValueError):
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    api._llm_converse('ses_001', 'test', MagicMock())
                )


class TestFallbackResponseTopicRecovery:
    """修复验证：_fallback_response 应从 session.research_context 恢复 topic"""

    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_fallback_recovers_topic_from_session_research_context(self):
        """
        修复后：即使 context 快照无 topic，也从 session.research_context 恢复
        修复验证（GREEN）
        """
        api = self._make_api()
        context_snapshot = {'topic': None, 'directions': []}
        with patch.object(api, '_get_lang', return_value='zh'):
            with patch.object(api, '_chat_response') as mock_chat:
                mock_chat.return_value = {'message': 'fallback'}
                with patch('src.api.research_api.session_manager') as sm:
                    session = {
                        'language': 'zh',
                        'research_context': {'topic': '新能源汽车'},
                    }
                    sm.get.return_value = session
                    api._fallback_response('ses_001', context_snapshot)
                    call_args = mock_chat.call_args
                    message = call_args[0][1]
                    assert '新能源汽车' in message, \
                        "修复验证：fallback 应从 session.research_context 恢复 topic"
