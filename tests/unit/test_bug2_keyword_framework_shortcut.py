# -*- coding: utf-8 -*-
"""
Bug 2 测试：关键词快捷路径触发 framework 模式

验证点：
1. _handle_user_message 在 chat 模式下识别"深度研究"关键词，跳过 LLM 直接进入 framework
2. _handle_user_message 在 research 模式下识别"深度研究"关键词，跳过 LLM 直接进入 framework
3. 有 topic 但无 directions 时仍可进入 framework（_enter_framework_mode 会生成默认框架）
4. 无 topic 时关键词不触发 framework（避免空框架）
5. 非命令式表达（疑问句）不误触发
6. 英文关键词也能触发
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.api.research_api import ResearchAPI
from src.core.session_manager import SessionManager


def _make_session(mode='chat', topic=None, directions=None):
    session = {
        'mode': mode,
        'conversation_history': [],
        'research_context': {
            'topic': topic,
            'directions': directions or [],
        },
        'language': 'zh',
        'state_machine': MagicMock(),
        'llm_config': {},
    }
    return session


class TestKeywordFrameworkShortcut:

    def _make_api(self):
        api = ResearchAPI.__new__(ResearchAPI)
        api._loop_cancel_flags = {}
        api._pending_clarifications = {}
        api._executor_tasks = {}
        api._background_tasks = {}
        api._background_task_gen = {}
        api._pending_v2_revisions = {}
        return api

    @pytest.mark.asyncio
    async def test_chat_mode_depth_research_keyword_triggers_framework(self):
        """Bug 2 核心验证：chat 模式下'深度研究'关键词直接进入 framework"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='比亚迪财务分析', directions=['营收分析', '利润趋势'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            sm.create = MagicMock()
            sm._sessions = {}

            with patch.object(api, '_enter_framework_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                'message': '研究框架已生成', 'framework': {'topic': '比亚迪财务分析', 'sections': ['营收分析', '利润趋势']}
            })) as mock_enter_fw:
                result = await api._handle_user_message('ses_001', '根据框架进行深度研究')

                mock_enter_fw.assert_called_once_with('ses_001', '根据框架进行深度研究')
                assert result['mode'] == 'framework'

    @pytest.mark.asyncio
    async def test_research_mode_depth_research_keyword_triggers_framework(self):
        """Bug 2 验证：research 模式下'深度研究'关键词触发 framework，暂停研究任务"""
        api = self._make_api()
        session = _make_session(mode='research', topic='比亚迪财务分析', directions=['营收分析'])
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        cm = get_cancel_manager()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        api._executor_tasks['ses_001'] = mock_task

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            sm.create = MagicMock()

            with patch.object(api, '_enter_framework_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                'message': '研究框架已生成'
            })) as mock_enter_fw:
                with patch.object(cm, 'pause') as mock_pause:
                    result = await api._handle_user_message('ses_001', '深度研究')

                    mock_pause.assert_called_once_with('ses_001')
                    mock_task.cancel.assert_called_once()
                    assert 'ses_001' not in api._executor_tasks
                    mock_enter_fw.assert_called_once()
                    assert result['mode'] == 'framework'

    @pytest.mark.asyncio
    async def test_no_topic_does_not_trigger_framework(self):
        """验证：无 topic 时关键词不触发 framework（避免空框架）"""
        api = self._make_api()
        session = _make_session(mode='chat', topic=None, directions=[])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_handle_chat_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 0, 'mode': 'chat', 'message': '你想研究什么？'
            })) as mock_chat:
                result = await api._handle_user_message('ses_001', '深度研究')

                mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_question_form_does_not_trigger_framework(self):
        """验证：疑问句'深度研究是什么？'不误触发 framework"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='比亚迪', directions=['营收'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_handle_chat_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 0, 'mode': 'chat', 'message': '深度研究是...'
            })) as mock_chat:
                result = await api._handle_user_message('ses_001', '深度研究是什么？')

                mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_english_keyword_deep_research(self):
        """验证：英文关键词 'deep research' 触发 framework"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='BYD financial analysis', directions=['revenue'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_enter_framework_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                'message': 'Research framework generated'
            })) as mock_enter_fw:
                result = await api._handle_user_message('ses_001', 'start deep research')

                mock_enter_fw.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyword_with_no_directions_still_enters_framework(self):
        """验证：有 topic 但无 directions 时仍可进入 framework"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='比亚迪财务分析', directions=[])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_enter_framework_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                'message': '研究框架已生成', 'framework': {'topic': '比亚迪财务分析', 'sections': ['核心指标', '盈利能力']}
            })) as mock_enter_fw:
                result = await api._handle_user_message('ses_001', '按框架研究')

                mock_enter_fw.assert_called_once()

    @pytest.mark.asyncio
    async def test_framework_mode_keyword_not_intercepted(self):
        """验证：framework 模式下关键词不拦截，走正常 framework 确认流程"""
        api = self._make_api()
        session = _make_session(mode='framework', topic='比亚迪财务分析', directions=['营收分析'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_enter_framework_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                'message': 'should not be called'
            })) as mock_enter_fw:
                with patch.object(api, '_handle_framework_mode', new=AsyncMock(return_value={
                    'session_id': 'ses_001', 'step': 5, 'mode': 'framework',
                    'message': '框架确认中'
                })) as mock_fw_msg:
                    result = await api._handle_user_message('ses_001', '开始研究')

                    mock_enter_fw.assert_not_called()
                    mock_fw_msg.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_message_does_not_trigger_framework(self):
        """验证：普通消息（无关键词）走正常 LLM 路径"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='比亚迪', directions=['营收'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_handle_chat_mode', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'step': 0, 'mode': 'chat', 'message': '好的'
            })) as mock_chat:
                result = await api._handle_user_message('ses_001', '比亚迪的最新财报数据')

                mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyword_with_pending_revision_not_override(self):
        """验证：有 pending revision 时关键词不覆盖 revision 流程"""
        api = self._make_api()
        session = _make_session(mode='chat', topic='比亚迪', directions=['营收'])
        from src.core.adjustment.revision_types import ExecutionStatus
        mock_flow = MagicMock()
        mock_flow.status = ExecutionStatus.PREVIEW_READY
        session['_pending_v2_revision'] = {'flow': mock_flow}

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session

            with patch.object(api, '_confirm_v2_revision', new=AsyncMock(return_value={
                'session_id': 'ses_001', 'message': 'revision confirmed'
            })) as mock_confirm:
                result = await api._handle_user_message('ses_001', '深度研究')

                mock_confirm.assert_not_called()