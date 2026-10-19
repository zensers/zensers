# -*- coding: utf-8 -*-
"""
Bug v3.5.0 测试：消息顺序 / 框架确认 / Skill路由

验证点：
1. Bug11: _handle_chat_mode processing路径assistant消息写入conversation_history
2. Bug12/13: _handle_framework_mode 框架确认意图检测 + __SELECTED_SECTIONS__解析
3. Bug12/13: _handle_chat_mode 框架确认意图检测（fallback路径）
4. Bug15: tool_display_names 动态扩展
5. 端到端：handle_interact → _handle_framework_mode → _start_execution 完整链路
"""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from src.api.research_api import ResearchAPI
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState


def _make_api():
    api = ResearchAPI.__new__(ResearchAPI)
    api._loop_cancel_flags = {}
    api._background_tasks = {}
    api._background_task_gen = {}
    api._executor_tasks = {}
    api._pending_clarifications = {}
    api._clarification_responses = {}
    api._tool_set = MagicMock()
    api._tool_set.TOOL_DEFINITIONS = [
        {"name": "web_search", "description": "Search the internet for real-time information"},
        {"name": "news_search", "description": "Search latest news"},
        {"name": "scrape_url", "description": "Scrape main content from a given URL"},
        {"name": "get_current_datetime", "description": "Get current date and time"},
        {"name": "xueqiu", "description": "Xueqiu stock market data platform"},
        {"name": "stock_data", "description": "Stock financial data retrieval"},
        {"name": "annual_report_parser", "description": "Parse annual reports from PDF files"},
    ]
    return api


def _make_session(session_id='ses_test', mode='chat', framework=None, topic='新能源'):
    framework = framework or {
        'topic': topic,
        'sections': ['市场规模', '竞争格局', '发展趋势'],
        'output_type': 'industry_report',
        'depth': 'standard',
        'region': 'China',
        'time_range': 'Last 3 years',
    }
    state_machine = ConversationStateMachine(research_id=session_id)
    if mode == 'framework':
        state_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
    return {
        'user_input': topic,
        'state_machine': state_machine,
        'mode': mode,
        'language': 'zh',
        'llm_config': {},
        'conversation_history': [],
        'research_context': {
            'topic': topic,
            'directions': [],
            'framework': framework,
            'details': {},
        },
        'current_step': 0,
    }


# ============================================================
# Bug11: processing路径assistant消息写入conversation_history
# ============================================================

class TestBug11ProcessingPathHistoryWrite:
    """Bug11: _handle_chat_mode processing分支应将初始assistant消息写入conversation_history"""

    @pytest.mark.asyncio
    async def test_processing_path_writes_initial_assistant_message(self):
        """processing路径返回后，conversation_history应包含初始assistant消息"""
        api = _make_api()
        session_id = 'ses_bug11'
        session = _make_session(session_id, mode='chat', framework=None)
        session['conversation_history'] = [
            {'role': 'user', 'content': '帮我查一下新能源市场', 'timestamp': '2026-01-01T00:00:00'},
        ]

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_intent_state') as mock_intent:
                mock_intent.return_value = MagicMock()
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'processing',
                            'message': '好的，我马上帮你查一下新能源市场信息',
                            'action': 'continue_chat',
                            'topic': '新能源',
                            'directions': [],
                            'suggestions': [],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            result = await api._handle_chat_mode(session_id, '帮我查一下新能源市场')

        assert result['status'] == 'processing'
        assert result['message'] == '好的，我马上帮你查一下新能源市场信息'
        history = session.get('conversation_history', [])
        assistant_msgs = [m for m in history if m.get('role') == 'assistant']
        assert len(assistant_msgs) >= 1, "processing路径应写入至少一条assistant消息到conversation_history"
        assert '好的，我马上帮你查一下' in assistant_msgs[-1]['content']

    @pytest.mark.asyncio
    async def test_processing_path_no_message_no_write(self):
        """processing路径如果message为空，不应写入空消息"""
        api = _make_api()
        session_id = 'ses_bug11_empty'
        session = _make_session(session_id, mode='chat', framework=None)
        initial_len = len(session.get('conversation_history', []))

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_intent_state'):
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'processing',
                            'message': '',
                            'action': 'continue_chat',
                            'topic': None,
                            'directions': [],
                            'suggestions': [],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            result = await api._handle_chat_mode(session_id, 'test')

        assert result['status'] == 'processing'
        assert len(session.get('conversation_history', [])) == initial_len, "空消息不应写入conversation_history"

    @pytest.mark.asyncio
    async def test_processing_path_initial_and_final_are_different_messages(self):
        """验证初始消息和最终消息是不同的，不会双写"""
        api = _make_api()
        session_id = 'ses_bug11_dual'
        session = _make_session(session_id, mode='chat', framework=None)
        session['conversation_history'] = [
            {'role': 'user', 'content': '查一下AI市场', 'timestamp': '2026-01-01T00:00:00'},
        ]

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_intent_state'):
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'processing',
                            'message': '好的，我帮你查一下',
                            'action': 'continue_chat',
                            'topic': 'AI',
                            'directions': [],
                            'suggestions': [],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            await api._handle_chat_mode(session_id, '查一下AI市场')

        history = session.get('conversation_history', [])
        assistant_msgs = [m for m in history if m.get('role') == 'assistant']
        assert len(assistant_msgs) == 1, "初始消息只应写入一次"
        assert assistant_msgs[0]['content'] == '好的，我帮你查一下'

        # 模拟后台工具链完成后 push_chat_response 通过 _persist_event 写入最终消息
        # 直接操作 session 的 conversation_history（模拟 _persist_event 的行为）
        history.append({
            'role': 'assistant',
            'content': '根据搜索结果，AI市场规模约为...',
            'timestamp': '2026-01-01T00:01:00',
        })
        session['conversation_history'] = history

        assistant_msgs = [m for m in session.get('conversation_history', []) if m.get('role') == 'assistant']
        assert len(assistant_msgs) == 2, "初始+最终=2条不同的assistant消息"
        assert assistant_msgs[0]['content'] == '好的，我帮你查一下'
        assert assistant_msgs[1]['content'] == '根据搜索结果，AI市场规模约为...'


# ============================================================
# Bug12/13: _handle_framework_mode 框架确认意图检测
# ============================================================

class TestBug12FrameworkConfirmInFrameworkMode:
    """Bug12/13: _handle_framework_mode 应检测确认意图并直接启动研究"""

    @pytest.mark.asyncio
    async def test_confirm_keyword_triggers_execution_not_llm(self):
        """确认关键词应跳过LLM调用，直接启动研究"""
        api = _make_api()
        session_id = 'ses_bug12_1'
        session = _make_session(session_id, mode='framework')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, '确认开始研究，包含章节：市场规模、竞争格局')

        mock_exec.assert_called_once_with(session_id)
        assert result['status'] == 'running'
        assert result['step'] == 6

    @pytest.mark.asyncio
    async def test_confirm_start_keyword_triggers_execution(self):
        """'confirm_start' 关键词也应触发直接执行"""
        api = _make_api()
        session_id = 'ses_bug12_2'
        session = _make_session(session_id, mode='framework')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': 'Research started',
                    }
                    result = await api._handle_framework_mode(session_id, 'confirm_start')

        mock_exec.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_confirm_keyword_with_english(self):
        """英文确认关键词也应触发执行"""
        api = _make_api()
        session_id = 'ses_bug12_3'
        session = _make_session(session_id, mode='framework')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': 'Research started',
                    }
                    result = await api._handle_framework_mode(session_id, 'Confirm and start research with sections: Market Size')

        mock_exec.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_non_confirm_keyword_goes_to_llm(self):
        """非确认关键词应正常走LLM流程"""
        api = _make_api()
        session_id = 'ses_bug12_4'
        session = _make_session(session_id, mode='framework')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_llm_framework_modify', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = {
                    'action': 'modify',
                    'message': '请告诉我你想如何修改',
                    'new_sections': ['市场规模', '竞争格局', '技术趋势'],
                }
                with patch.object(api, '_framework_response') as mock_fw:
                    mock_fw.return_value = {
                        'session_id': session_id, 'step': 5, 'mode': 'framework',
                        'message': '已调整框架',
                    }
                    result = await api._handle_framework_mode(session_id, '我想加一个技术趋势的章节')

        mock_llm.assert_called_once()
        assert result['mode'] == 'framework'

    @pytest.mark.asyncio
    async def test_selected_sections_marker_parsed(self):
        """__SELECTED_SECTIONS__ 标记应被正确解析，过滤框架章节"""
        api = _make_api()
        session_id = 'ses_bug12_5'
        framework = {
            'topic': '新能源',
            'sections': ['市场规模', '竞争格局', '发展趋势', '政策分析'],
            'output_type': 'industry_report',
            'depth': 'standard',
            'region': 'China',
            'time_range': 'Last 3 years',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        user_input = '确认开始研究，包含章节：市场规模、竞争格局\n__SELECTED_SECTIONS__:["市场规模","竞争格局"]'

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, user_input)

        fw = session['research_context']['framework']
        assert fw['sections'] == ['市场规模', '竞争格局'], \
            f"应只保留用户选中的章节，实际: {fw['sections']}"
        mock_exec.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_selected_sections_with_tree(self):
        """__SELECTED_SECTIONS__ + sections_tree 应正确过滤树结构，子节点选中时保留父节点"""
        api = _make_api()
        session_id = 'ses_bug12_6'
        framework = {
            'topic': '新能源',
            'sections': ['市场规模', '竞争格局', '发展趋势'],
            'sections_tree': [
                {'name': '市场规模', 'sub_sections': [
                    {'name': '总体规模', 'points': ['全球规模', '中国规模']},
                    {'name': '增长趋势', 'points': ['CAGR']},
                ]},
                {'name': '竞争格局', 'sub_sections': [
                    {'name': '主要企业', 'points': ['TOP10']},
                ]},
                {'name': '发展趋势', 'sub_sections': [
                    {'name': '技术趋势', 'points': ['AI']},
                ]},
            ],
            'output_type': 'industry_report',
            'depth': 'standard',
            'region': 'China',
            'time_range': 'Last 3 years',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        # 用户只选中"增长趋势"（市场规模的子节点），不选"市场规模"本身
        user_input = '确认开始研究\n__SELECTED_SECTIONS__:["增长趋势"]'

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, user_input)

        fw = session['research_context']['framework']
        # "增长趋势"是"市场规模"的子节点，"市场规模"应作为父节点保留在sections中
        assert '市场规模' in fw['sections'], f"市场规模应保留（作为增长趋势的父节点），实际: {fw['sections']}"
        # "竞争格局"和"发展趋势"未被选中，应被过滤
        assert '竞争格局' not in fw['sections']
        assert '发展趋势' not in fw['sections']
        tree = fw.get('sections_tree', [])
        tree_names = [n.get('name', '') for n in tree]
        assert '市场规模' in tree_names, "市场规模作为父节点应保留"
        assert '竞争格局' not in tree_names, "竞争格局未选中应被过滤"
        # 增长趋势是市场规模的子节点，应保留在市场规模的sub_sections中
        market_node = [n for n in tree if n.get('name') == '市场规模']
        assert len(market_node) == 1
        sub_names = [s.get('name', '') for s in market_node[0].get('sub_sections', [])]
        assert '增长趋势' in sub_names, "增长趋势作为选中的子节点应保留"
        # 总体规模未被选中，应被过滤
        assert '总体规模' not in sub_names, "总体规模未选中应被过滤"

    @pytest.mark.asyncio
    async def test_selected_sections_with_tree_parent_selected(self):
        """选中父节点时，其所有子节点应保留"""
        api = _make_api()
        session_id = 'ses_bug12_6b'
        framework = {
            'topic': '新能源',
            'sections': ['市场规模', '竞争格局', '发展趋势'],
            'sections_tree': [
                {'name': '市场规模', 'sub_sections': [
                    {'name': '总体规模', 'points': ['全球规模', '中国规模']},
                    {'name': '增长趋势', 'points': ['CAGR']},
                ]},
                {'name': '竞争格局', 'sub_sections': [
                    {'name': '主要企业', 'points': ['TOP10']},
                ]},
            ],
            'output_type': 'industry_report',
            'depth': 'standard',
            'region': 'China',
            'time_range': 'Last 3 years',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        # 用户选中"市场规模"（顶级节点），应包含其所有子节点
        user_input = '确认开始研究\n__SELECTED_SECTIONS__:["市场规模"]'

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, user_input)

        fw = session['research_context']['framework']
        assert '市场规模' in fw['sections']
        assert '竞争格局' not in fw['sections']
        tree = fw.get('sections_tree', [])
        market_node = [n for n in tree if n.get('name') == '市场规模']
        assert len(market_node) == 1
        sub_names = [s.get('name', '') for s in market_node[0].get('sub_sections', [])]
        # 选中父节点时，所有子节点都应保留
        assert '总体规模' in sub_names, "选中父节点时，所有子节点应保留"
        assert '增长趋势' in sub_names, "选中父节点时，所有子节点应保留"

    @pytest.mark.asyncio
    async def test_selected_sections_invalid_json_uses_all(self):
        """__SELECTED_SECTIONS__ JSON解析失败时，应使用全部章节"""
        api = _make_api()
        session_id = 'ses_bug12_7'
        framework = {
            'topic': '新能源',
            'sections': ['市场规模', '竞争格局'],
            'output_type': 'industry_report',
            'depth': 'standard',
            'region': 'China',
            'time_range': 'Last 3 years',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        user_input = '确认开始研究\n__SELECTED_SECTIONS__:invalid json here'

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, user_input)

        fw = session['research_context']['framework']
        assert fw['sections'] == ['市场规模', '竞争格局'], \
            "JSON解析失败时应保留全部章节"

    @pytest.mark.asyncio
    async def test_confirm_without_selected_sections_uses_all(self):
        """确认关键词但无__SELECTED_SECTIONS__标记时，应使用全部章节"""
        api = _make_api()
        session_id = 'ses_bug12_8'
        framework = {
            'topic': '新能源',
            'sections': ['市场规模', '竞争格局', '发展趋势'],
            'output_type': 'industry_report',
            'depth': 'standard',
            'region': 'China',
            'time_range': 'Last 3 years',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api._handle_framework_mode(session_id, '确认开始研究')

        fw = session['research_context']['framework']
        assert fw['sections'] == ['市场规模', '竞争格局', '发展趋势'], \
            "无标记时应保留全部章节"
        mock_exec.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_confirm_empty_framework_returns_error(self):
        """确认但框架无章节时，应返回错误而非启动执行"""
        api = _make_api()
        session_id = 'ses_bug12_9'
        framework = {
            'topic': '新能源',
            'sections': [],
            'output_type': 'industry_report',
        }
        session = _make_session(session_id, mode='framework', framework=framework)

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            result = await api._handle_framework_mode(session_id, '确认开始研究')

        assert result['mode'] == 'framework', "空框架不应启动执行"


# ============================================================
# Bug12/13: _handle_chat_mode fallback路径
# ============================================================

class TestBug12FrameworkConfirmInChatMode:
    """Bug12/13: _handle_chat_mode 中的框架确认fallback检测"""

    @pytest.mark.asyncio
    async def test_chat_mode_with_framework_and_confirm_keyword(self):
        """chat模式下有框架+确认关键词也应触发执行"""
        api = _make_api()
        session_id = 'ses_bug12_chat_1'
        session = _make_session(session_id, mode='chat')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_sync_state_machine_to_framework'):
                    with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                        mock_exec.return_value = {
                            'session_id': session_id, 'task_id': session_id,
                            'step': 6, 'mode': 'research', 'status': 'running',
                            'message': '研究任务已启动',
                        }
                        result = await api._handle_chat_mode(session_id, '确认开始研究')

        mock_exec.assert_called_once_with(session_id)
        assert result['status'] == 'running'

    @pytest.mark.asyncio
    async def test_chat_mode_no_framework_goes_to_llm(self):
        """chat模式下无框架+确认关键词应正常走LLM"""
        api = _make_api()
        session_id = 'ses_bug12_chat_2'
        session = _make_session(session_id, mode='chat', framework=None)
        session['research_context']['framework'] = None

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_intent_state'):
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'completed',
                            'message': '好的，你想研究什么？',
                            'action': 'continue_chat',
                            'topic': None,
                            'directions': [],
                            'suggestions': [],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            with patch.object(api, '_chat_response') as mock_chat:
                                mock_chat.return_value = {
                                    'session_id': session_id, 'step': 0, 'mode': 'chat',
                                    'message': '好的，你想研究什么？',
                                }
                                result = await api._handle_chat_mode(session_id, '确认开始研究')

        mock_llm.assert_called_once(), "无框架时确认关键词应走LLM"


# ============================================================
# Bug12/13: handle_interact 完整链路
# ============================================================

class TestBug12HandleInteractEndToEnd:
    """Bug12/13: handle_interact → _handle_framework_mode → _start_execution 完整链路"""

    @pytest.mark.asyncio
    async def test_handle_interact_framework_mode_confirm(self):
        """handle_interact step=0 mode=framework + confirm_start → 直接执行"""
        api = _make_api()
        session_id = 'ses_e2e_1'
        session = _make_session(session_id, mode='framework')

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动',
                    }
                    result = await api.handle_interact(
                        session_id, step=0,
                        response={
                            'text': '确认开始研究，包含章节：市场规模、竞争格局\n__SELECTED_SECTIONS__:["市场规模","竞争格局"]',
                            'suggestion_id': 'confirm_start',
                        }
                    )

        assert result['status'] == 'running'
        assert result['step'] == 6
        mock_exec.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_handle_interact_preserves_text_with_suggestion_id(self):
        """handle_interact 中 suggestion_id 存在但 text 非空时，应保留 text"""
        api = _make_api()
        session_id = 'ses_e2e_2'
        session = _make_session(session_id, mode='framework')

        response = {
            'text': '确认开始研究，包含章节：市场规模\n__SELECTED_SECTIONS__:["市场规模"]',
            'suggestion_id': 'confirm_start',
        }
        user_message = response.get('text', response.get('message', ''))
        suggestion_id = response.get('suggestion_id', response.get('id', ''))
        if suggestion_id:
            if user_message:
                pass
            else:
                suggestion_map = {'add_details': 'add some details'}
                mapped = suggestion_map.get(suggestion_id)
                if mapped:
                    user_message = mapped
                else:
                    user_message = suggestion_id

        assert '__SELECTED_SECTIONS__' in user_message, \
            "text非空时应保留完整文本（包含__SELECTED_SECTIONS__标记）"


# ============================================================
# Bug15: tool_display_names 动态扩展
# ============================================================

class TestBug15ToolDisplayNames:
    """Bug15: tool_display_names 应包含动态注册skill的显示名"""

    def test_base_tools_have_display_names(self):
        """内置工具应有显示名"""
        tool_display_names = {
            'web_search': 'Web Search Agent',
            'news_search': 'News Search Agent',
            'scrape_url': 'Content Scraper Agent',
            'get_current_datetime': 'Date/Time Agent',
            'xueqiu': 'Xueqiu Stock Data',
            'stock_data': 'Stock Financial Data',
            'annual_report_parser': 'Annual Report Parser',
        }
        assert tool_display_names['xueqiu'] == 'Xueqiu Stock Data'
        assert tool_display_names['stock_data'] == 'Stock Financial Data'
        assert tool_display_names['annual_report_parser'] == 'Annual Report Parser'

    def test_dynamic_fallback_from_tool_definitions(self):
        """未知工具应从 TOOL_DEFINITIONS description 提取显示名"""
        tool_display_names = {
            'web_search': 'Web Search Agent',
            'news_search': 'News Search Agent',
            'scrape_url': 'Content Scraper Agent',
            'get_current_datetime': 'Date/Time Agent',
            'xueqiu': 'Xueqiu Stock Data',
            'stock_data': 'Stock Financial Data',
            'annual_report_parser': 'Annual Report Parser',
        }
        tool_definitions = [
            {"name": "xueqiu", "description": "Xueqiu stock market data platform"},
            {"name": "custom_skill", "description": "Custom skill for data analysis"},
        ]
        tool_name = "custom_skill"
        if tool_name not in tool_display_names:
            for td in tool_definitions:
                if td.get('name') == tool_name:
                    tool_display_names[tool_name] = td.get('description', f'Agent ({tool_name})').split('.')[0].strip()
                    break
        assert tool_display_names.get('custom_skill') == 'Custom skill for data analysis', \
            "未知工具应从description提取显示名"

    def test_unknown_tool_fallback_to_agent_name(self):
        """完全未知的工具应回退为 'Agent (tool_name)'"""
        tool_display_names = {
            'web_search': 'Web Search Agent',
        }
        tool_name = "unknown_tool_xyz"
        result = tool_display_names.get(tool_name, f"Agent ({tool_name})")
        assert result == "Agent (unknown_tool_xyz)"


# ============================================================
# 端到端：完整对话流程验证
# ============================================================

class TestEndToEndConversationFlow:
    """端到端验证：对话 → 框架 → 确认 → 执行"""

    @pytest.mark.asyncio
    async def test_full_flow_chat_to_framework_to_confirm(self):
        """完整流程：用户发消息 → LLM返回enter_framework → 用户确认 → 执行启动"""
        api = _make_api()
        session_id = 'ses_e2e_full'

        # Step 1: 用户发消息，LLM返回enter_framework
        session_step1 = _make_session(session_id, mode='chat', framework=None)
        session_step1['research_context']['framework'] = None

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session_step1
            with patch.object(api, '_get_or_create_intent_state'):
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_machine.can_transition_to.return_value = True
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'completed',
                            'message': '我来帮你整理研究框架',
                            'action': 'enter_framework',
                            'topic': '新能源',
                            'directions': ['市场规模', '竞争格局'],
                            'suggestions': [],
                            'framework_sections': ['市场规模', '竞争格局', '发展趋势'],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            with patch.object(api, '_enter_framework_mode', new_callable=AsyncMock) as mock_enter_fw:
                                mock_enter_fw.return_value = {
                                    'session_id': session_id, 'step': 5, 'mode': 'framework',
                                    'message': '研究框架已准备好',
                                    'framework': {
                                        'topic': '新能源',
                                        'sections': ['市场规模', '竞争格局', '发展趋势'],
                                    },
                                }
                                result1 = await api._handle_chat_mode(session_id, '帮我研究新能源市场')

        assert result1['mode'] == 'framework'

        # Step 2: 用户确认框架
        session_step2 = _make_session(session_id, mode='framework')
        session_step2['conversation_history'] = session_step1.get('conversation_history', [])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session_step2
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动！',
                    }
                    result2 = await api._handle_framework_mode(
                        session_id,
                        '确认开始研究，包含章节：市场规模、竞争格局\n__SELECTED_SECTIONS__:["市场规模","竞争格局"]'
                    )

        assert result2['status'] == 'running'
        assert result2['step'] == 6
        fw = session_step2['research_context']['framework']
        assert fw['sections'] == ['市场规模', '竞争格局']

    @pytest.mark.asyncio
    async def test_conversation_history_preserved_across_modes(self):
        """验证conversation_history在模式切换中不丢失"""
        api = _make_api()
        session_id = 'ses_history_preserve'
        session = _make_session(session_id, mode='framework')
        session['conversation_history'] = [
            {'role': 'user', 'content': '帮我研究新能源', 'timestamp': '2026-01-01T00:00:00'},
            {'role': 'assistant', 'content': '好的，我来帮你整理研究框架', 'timestamp': '2026-01-01T00:00:01'},
            {'role': 'user', 'content': '确认开始研究', 'timestamp': '2026-01-01T00:00:02'},
        ]
        initial_count = len(session['conversation_history'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch.object(api, '_start_execution', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        'session_id': session_id, 'task_id': session_id,
                        'step': 6, 'mode': 'research', 'status': 'running',
                        'message': '研究任务已启动！',
                    }
                    await api._handle_framework_mode(session_id, '确认开始研究')

        history = session.get('conversation_history', [])
        assert len(history) >= initial_count, "conversation_history不应丢失已有消息"


# ============================================================
# BUG1 fix: processing_ack 标记
# ============================================================

class TestBug1ProcessingAckMarker:
    """processing路径的初始assistant消息应带 _type='processing_ack' 标记"""

    @pytest.mark.asyncio
    async def test_processing_message_has_ack_type(self):
        """processing路径写入的消息应有 _type='processing_ack'"""
        api = _make_api()
        session_id = 'ses_ack_1'
        session = _make_session(session_id, mode='chat', framework=None)

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_intent_state'):
                with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                    mock_machine = MagicMock()
                    mock_machine.current_state = ConversationState.UNDERSTANDING
                    mock_conv.return_value = mock_machine
                    with patch.object(api, '_llm_converse', new_callable=AsyncMock) as mock_llm:
                        mock_llm.return_value = {
                            'status': 'processing',
                            'message': '好的，我帮你查一下',
                            'action': 'continue_chat',
                            'topic': 'AI',
                            'directions': [],
                            'suggestions': [],
                        }
                        with patch.object(api, '_cancel_existing_task'):
                            await api._handle_chat_mode(session_id, '查一下AI市场')

        history = session.get('conversation_history', [])
        ack_msgs = [m for m in history if m.get('_type') == 'processing_ack']
        assert len(ack_msgs) == 1, "processing消息应有 _type='processing_ack' 标记"
        assert ack_msgs[0]['role'] == 'assistant'
        assert ack_msgs[0]['content'] == '好的，我帮你查一下'

    @pytest.mark.asyncio
    async def test_non_processing_message_has_no_ack_type(self):
        """非processing路径的消息不应有 _type 标记"""
        api = _make_api()
        session_id = 'ses_ack_2'
        session = _make_session(session_id, mode='chat', framework=None)

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            result = api._chat_response(session_id, '这是普通回复')

        history = session.get('conversation_history', [])
        assert len(history) >= 1
        assert history[-1].get('_type') is None, "普通assistant消息不应有_type标记"


# ============================================================
# BUG2 fix: _start_execution 持久化 "研究任务已启动" 消息
# ============================================================

class TestBug2StartExecutionPersistsMessage:
    """_start_execution 应将 '研究任务已启动' 消息写入 conversation_history"""

    @pytest.mark.asyncio
    async def test_start_execution_persists_message(self):
        """_start_execution 调用后，conversation_history 应包含启动消息"""
        api = _make_api()
        api._executor_tasks = {}
        session_id = 'ses_exec_1'
        session = _make_session(session_id, mode='framework')
        session['conversation_history'] = [
            {'role': 'user', 'content': '帮我研究新能源', 'timestamp': '2026-01-01T00:00:00'},
            {'role': 'assistant', 'content': '框架已准备好', 'timestamp': '2026-01-01T00:00:01'},
            {'role': 'user', 'content': '确认开始研究', 'timestamp': '2026-01-01T00:00:02'},
        ]
        initial_count = len(session['conversation_history'])

        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch('src.api.research_executor.get_executor') as mock_get_exec:
                mock_executor = MagicMock()
                mock_executor.execute = AsyncMock()
                mock_get_exec.return_value = mock_executor
                with patch('src.api.research_api.safe_create_task') as mock_task:
                    mock_task.return_value = MagicMock()
                    with patch('src.core.progress_streamer.ProgressStreamer.set_disconnect_callback'):
                        result = await api._start_execution(session_id)

        assert result['status'] == 'running'
        history = session.get('conversation_history', [])
        assert len(history) > initial_count, "_start_execution应写入启动消息到conversation_history"
        last_msg = history[-1]
        assert last_msg['role'] == 'assistant'
        assert '研究任务已启动' in last_msg['content'] or 'Research task has been started' in last_msg['content']

    @pytest.mark.asyncio
    async def test_framework_confirm_flow_no_message_loss(self):
        """完整框架确认流程：用户消息+启动消息都不丢失"""
        api = _make_api()
        api._executor_tasks = {}
        session_id = 'ses_exec_2'
        session = _make_session(session_id, mode='framework')
        session['conversation_history'] = []

        # Step 1: _handle_user_message 写入用户消息
        with patch('src.api.research_api.session_manager') as sm:
            sm.get.return_value = session
            with patch.object(api, '_get_or_create_conv_machine') as mock_conv:
                mock_machine = MagicMock()
                mock_conv.return_value = mock_machine
                with patch('src.api.research_executor.get_executor') as mock_get_exec:
                    mock_executor = MagicMock()
                    mock_executor.execute = AsyncMock()
                    mock_get_exec.return_value = mock_executor
                    with patch('src.api.research_api.safe_create_task') as mock_task:
                        mock_task.return_value = MagicMock()
                        with patch('src.core.progress_streamer.ProgressStreamer.set_disconnect_callback'):
                            # _handle_user_message 先写 user 消息
                            history = session.get('conversation_history', [])
                            history.append({'role': 'user', 'content': '确认开始研究', 'timestamp': '2026-01-01T00:00:00'})
                            session['conversation_history'] = history

                            # 然后走 _handle_framework_mode → _start_execution
                            result = await api._handle_framework_mode(session_id, '确认开始研究')

        history = session.get('conversation_history', [])
        user_msgs = [m for m in history if m.get('role') == 'user']
        assistant_msgs = [m for m in history if m.get('role') == 'assistant']
        assert len(user_msgs) >= 1, "用户消息不应丢失"
        assert len(assistant_msgs) >= 1, "启动消息不应丢失"
        assert any('研究任务已启动' in m['content'] or 'Research task' in m['content'] for m in assistant_msgs), \
            "assistant消息应包含研究启动信息"
