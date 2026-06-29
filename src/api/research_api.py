# -*- coding: utf-8 -*-

"""

Research Interaction API
========================

Provides interactive API endpoints for research tasks, supporting frontend integration.

Core process design:
1. Dialogue phase (step=0, mode=chat) - Free communication, explore research direction
2. Framework confirmation phase (step=0, mode=framework) - Confirm research framework and details
3. Execution phase (step=1-6) - Smart routing, Agent collaboration execution
4. Preview phase - HTML preview, user review
5. Revision phase - User feedback modification or confirmation
6. Output phase - Generate final document

Special entry: /template command -> Use built-in framework directly

Design doc: docs/USER_INTERACTION_INTEGRATION_PLAN.md

"""

import json
import datetime
import asyncio
import uuid
import logging
import os
import re
from src.core.llm_client import call_llm, call_llm_stream
import time
import traceback
import shutil
from datetime import datetime
from src.core.orchestrator.execution.task_utils import safe_create_task
from pathlib import Path
from typing import Any
from src.core.adjustment.cascade_update_analyzer import CascadeUpdateAnalyzer
from src.core.adjustment.enhanced_section_locator import EnhancedSectionLocator
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
from src.core.adjustment.revision_type_inferrer import RevisionTypeInferrer
from src.core.dialogue.dialogue_intent_state import DialogueIntentState
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
from src.core.dialogue.sub_intent import SubIntent
from src.core.i18n import detect_language, set_language as set_global_language, Language, get_language_instruction
from src.core.intent_types import IntentType
from src.core.orchestrator.orchestrator import ResearchOrchestrator
from src.core.orchestrator.smart_clarifier import SmartClarifier
from src.core.preview.preview_generator import PreviewGenerator
from src.core.preview_storage import PreviewStorage
from src.core.prompt_manager import PromptManager
from src.core.research_framework_manager import get_framework_config
from src.core.session_manager import SessionManager


logger = logging.getLogger(__name__)
session_manager = SessionManager()

class ConversationToolSet:
    """ConversationToolSet"""

    TOOL_DEFINITIONS = [
        {"name": "get_current_datetime", "description": "Get current date and time", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "web_search", "description": "Search the internet for real-time information", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query keywords"}, "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 5}, "recency_days": {"type": "integer", "description": "How recent the results should be in days (e.g. 7 for past week, 30 for past month)", "default": 30}}, "required": ["query"]}},
        {"name": "news_search", "description": "Search latest news", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "News search query keywords"}, "max_results": {"type": "integer", "description": "Maximum number of news results to return", "default": 5}, "recency_days": {"type": "integer", "description": "How recent the news should be in days (e.g. 7 for past week, 30 for past month)", "default": 30}}, "required": ["query"]}},
        {"name": "scrape_url", "description": "Scrape main content from a given URL", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "The URL to scrape"}, "max_chars": {"type": "integer", "description": "Maximum characters to extract", "default": 5000}}, "required": ["url"]}},
    ]

    TOOL_TIMEOUTS = {"get_current_datetime": 5, "web_search": 30, "news_search": 30, "scrape_url": 20}

    def __init__(self):
        self._search_skill = None
        self._news_skill = None
        self._scraper_skill = None
        return

    def get_current_datetime(self):
        """Get current date and time"""
        now = datetime.now()
        weekdays = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
        return {'success': True, 'data': {'iso_format': now.isoformat(), 'date': now.strftime('%Y-%m-%d'), 'weekday': weekdays[now.weekday()], 'time': now.strftime('%H:%M'), 'year': now.year, 'month': now.month, 'day': now.day, 'hour': now.hour, 'minute': now.minute}}

    async def web_search(self, query, max_results=5, recency_days=30):
        """Search the internet for real-time information"""
        try:
            if not self._search_skill:
                from src.skills.search_skill import MultiSearchSkill
                self._search_skill = MultiSearchSkill()
            kwargs = {'query': query, 'max_results': max_results}
            if recency_days:
                if recency_days > 0:
                    if recency_days <= 7:
                        kwargs['time_range'] = 'd'
                    elif recency_days <= 30:
                        kwargs['time_range'] = 'w'
                    elif recency_days <= 90:
                        kwargs['time_range'] = 'm'
                    else:
                        kwargs['time_range'] = 'y'
            result = await self._search_skill.execute(**kwargs)
            if result.get('success'):
                return {'success': True, 'data': result.get('results', [])}
            return {'success': False, 'error': result.get('error', 'Search failed')}
        except Exception as e:
            logger.warning(f"web_search failed: {e}")
            return {'success': False, 'error': str(e)}

    async def news_search(self, query, max_results=5, recency_days=30):
        """Search latest news"""
        try:
            if not self._news_skill:
                from src.skills.search_skill import NewsSearchSkill
                self._news_skill = NewsSearchSkill()
            kwargs = {'query': query, 'max_results': max_results}
            if recency_days:
                if recency_days > 0:
                    if recency_days <= 7:
                        kwargs['time_range'] = 'd'
                    elif recency_days <= 30:
                        kwargs['time_range'] = 'w'
                    elif recency_days <= 90:
                        kwargs['time_range'] = 'm'
                    else:
                        kwargs['time_range'] = 'y'
            result = await self._news_skill.execute(**kwargs)
            if result.get('success'):
                return {'success': True, 'data': result.get('results', [])}
            return {'success': False, 'error': result.get('error', 'News search failed')}
        except Exception as e:
            logger.warning(f"news_search failed: {e}")
            return {'success': False, 'error': str(e)}

    def scrape_url(self, url, max_chars):
        """Scrape main content from a given URL"""
        try:
            if not self._scraper_skill:
                from src.skills.web_scraper_skill import WebScraperSkill
                self._scraper_skill = WebScraperSkill()
            result = self._scraper_skill.execute(url=url, action='extract_text', max_chars=max_chars)
            if result.get('success'):
                return {'success': True, 'data': result.get('content', '')}
            return {'success': False, 'error': result.get('error', 'Scrape failed')}
        except Exception as e:
            logger.warning(f"scrape_url failed: {e}")
            return {'success': False, 'error': str(e)}

    def _get_handler(self, tool_name):
        tool_map = {'get_current_datetime': self.get_current_datetime, 'web_search': self.web_search, 'news_search': self.news_search, 'scrape_url': self.scrape_url}
        return tool_map.get(tool_name)

    async def execute_tool(self, tool_name, arguments):
        """Execute the specified tool and return result (with single timeout protection)"""
        handler = self._get_handler(tool_name)
        if not handler:
            return {'success': False, 'error': f"Unknown tool: {tool_name}"}
        try:
            timeout = self.TOOL_TIMEOUTS.get(tool_name, 30)
            result = handler(**arguments)
            if hasattr(result, '__await__'):
                result = await asyncio.wait_for(result, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Tool {tool_name} timed out after {timeout}s")
            return {'success': False, 'error': f"{tool_name} execution timeout ({timeout}s)"}
        except Exception as e:
            logger.warning(f"{tool_name} failed: {e}")
            return {'success': False, 'error': str(e)}

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


class _ThinkTagFilter:
    """Splits streaming tokens into thinking and normal content.

    feed() returns a list of (type, text) tuples where type is 'think' or 'text'.
    """

    def __init__(self):
        self._in_think = False
        self._buffer = ""

    @staticmethod
    def _partial_tag_prefix(tag: str, buf: str) -> int:
        for i in range(1, min(len(tag), len(buf) + 1)):
            if buf.endswith(tag[:i]):
                return i
        return 0

    def feed(self, token: str) -> list[tuple[str, str]]:
        emitted: list[tuple[str, str]] = []
        self._buffer += token
        while self._buffer:
            if self._in_think:
                close_idx = self._buffer.find(_THINK_CLOSE)
                if close_idx != -1:
                    if close_idx > 0:
                        emitted.append(('think', self._buffer[:close_idx]))
                    self._buffer = self._buffer[close_idx + len(_THINK_CLOSE):]
                    self._in_think = False
                else:
                    partial_len = self._partial_tag_prefix(_THINK_CLOSE, self._buffer)
                    safe_len = len(self._buffer) - partial_len if partial_len else len(self._buffer)
                    if safe_len > 0:
                        emitted.append(('think', self._buffer[:safe_len]))
                        self._buffer = self._buffer[safe_len:]
                    else:
                        break
            else:
                open_idx = self._buffer.find(_THINK_OPEN)
                if open_idx != -1:
                    if open_idx > 0:
                        emitted.append(('text', self._buffer[:open_idx]))
                    self._buffer = self._buffer[open_idx + len(_THINK_OPEN):]
                    self._in_think = True
                else:
                    partial_len = self._partial_tag_prefix(_THINK_OPEN, self._buffer)
                    safe_len = len(self._buffer) - partial_len if partial_len else len(self._buffer)
                    if safe_len > 0:
                        emitted.append(('text', self._buffer[:safe_len]))
                        self._buffer = self._buffer[safe_len:]
                    else:
                        break
        return emitted

    def flush(self) -> list[tuple[str, str]]:
        if not self._buffer:
            return []
        result = self._buffer
        self._buffer = ""
        if self._in_think:
            return [('think', result)]
        return [('text', result)]


class ResearchAPI:
    """ResearchAPI"""

    _background_tasks: dict = {}
    _background_task_gen: dict = {}

    _JSON_OUTPUT_SCHEMA = """Output MUST be a JSON object with these fields:
{
  "message": "your response to the user (REQUIRED)",
  "action": "continue_chat" | "enter_framework" | "modify_research" | "resume_research" | "revise_report" | "regenerate_report" | "inject_requirement",
  "topic": "identified research topic or null",
  "directions": ["direction1", "direction2"],
  "framework_sections": ["section1", "section2"],
  "framework_tree": [{"name": "section1", "sub_sections": [{"name": "sub1", "points": ["point1"]}]}],
  "clarification_questions": ["q1"],
  "suggestions": ["suggestion text"],
  "inject_ops": [{"op": "add_section", "section_name": "..."}],
  "modifications": {"add_aspects": [], "remove_aspects": [], "modify_aspects": {}},
  "adjustment": "user's original request text",
  "aspects": ["section names for revision"],
  "revision_type": "section" | "full",
  "tool_call": {"name": "tool_name", "arguments": {}} or null
}
RULE: When action="enter_framework", if the topic has natural multi-level structure (e.g., industry segments, regional breakdowns, product categories), prefer using "framework_tree" instead of only "framework_sections". Simple topics can use "framework_sections" alone."""

    def __init__(self, orchestrator=None, preview_generator=None, use_intelligent_routing=True, knowledge_manager=None):
        """_knowledge_manager"""
        if orchestrator:
            self._orchestrator = orchestrator
        else:
            self._orchestrator = ResearchOrchestrator(use_intelligent_routing=use_intelligent_routing)
        if knowledge_manager:
            self._knowledge_manager = knowledge_manager
        else:
            self._knowledge_manager = getattr(self._orchestrator, '_knowledge_manager', None)
        if preview_generator:
            self._preview_generator = preview_generator
        else:
            self._preview_generator = PreviewGenerator(cache_dir=str(PreviewStorage.NEW_DIR))
        self._tool_set = ConversationToolSet()
        self._revision_locks = {}
        self._revision_task = None
        self._executor_tasks = {}
        self._session_locks = {}
        self._pending_clarifications = {}
        self._clarification_responses = {}
        self._loop_cancel_flags = {}
        self._dream_mode_running = False

    def _get_session_lock(self, session_id):
        """P0 fix: Get or create session-level lock for thread-safe context updates"""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    async def _update_research_context_atomic(self, session_id, updates):
        """P0 fix: Thread-safe research context update with lock protection"""
        lock = self._get_session_lock(session_id)
        async with lock:
            session = session_manager.get(session_id)
            if not session:
                return
            context = session.setdefault('research_context', {})
            context.update(updates)
            session['research_context'] = context
            context = session.get('research_context', {})
            new_topic = updates.get('topic')
            current_topic = context.get('topic')
            if new_topic and new_topic != current_topic:
                logger.info(f"""Research topic updated: '{current_topic}' -> '{new_topic}'. Cleared directions and framework for fresh start.""")
                context['topic'] = new_topic
                context['directions'] = []
                context['framework'] = {}
            for key, value in updates.items():
                if key != 'topic':
                    context[key] = value
            session['research_context'] = context

    async def start_research(self, user_input, user_id, llm_config):
        """
        
        Start research dialogue
        
        POST /api/research/start
        
        Flow:
        1. Identify user intent
        2. Greeting/small talk -> guide to express research needs
        3. Research need -> enter dialogue phase, start communication
        
        """
        session_id = f"""ses_{uuid.uuid4().hex[:8]}"""
        state_machine = ConversationStateMachine(research_id=session_id)
        detected_lang = detect_language(user_input).value
        session_manager.create(session_id, {'user_input': user_input, 'user_id': user_id, 'state_machine': state_machine, 'clarifier': SmartClarifier(), 'created_at': datetime.now(), 'current_step': 0, 'mode': 'chat', 'llm_config': llm_config, 'language': detected_lang, '_session_id': session_id, 'conversation_history': [], 'research_context': {'topic': None, 'directions': [], 'framework': None, 'details': {}}})
        set_global_language(Language(detected_lang))
        return await self._handle_user_message(session_id, user_input)

    async def _handle_user_message(self, session_id, user_input, skip_lang_detect=False):
        """
        Process user message (core dialogue logic)
        All routing decisions are made by the LLM (complexity analysis, intent).
        """
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}

        pending = session.get('_pending_v2_revision')
        if pending:
            from src.core.adjustment.revision_types import ExecutionStatus, TaskStatus
            flow = pending['flow']
            if flow.status == ExecutionStatus.PREVIEW_READY:
                if user_input.strip().lower() in ('y', 'yes', '确认', '同意', '好', '提交', '完成'):
                    return await self._confirm_v2_revision(session_id, accept=True)
                if user_input.strip().lower() in ('n', 'no', '取消', '拒绝'):
                    return await self._confirm_v2_revision(session_id, accept=False)
                return self._chat_response(session_id, '请确认修改(y)或拒绝(n)')
            if flow.current_index < len(flow.tasks):
                task = flow.tasks[flow.current_index]
                if task.status == TaskStatus.CONFIRMING:
                    return await self._handle_task_confirmation(session_id, flow, pending, user_input)

        pending_clar_id = session.get('_pending_clarification_id')
        if pending_clar_id:
            old_event = self._pending_clarifications.pop(pending_clar_id, None)
            if old_event and not old_event.is_set():
                self._clarification_responses[pending_clar_id] = user_input
                old_event.set()
                logger.info(f"Resolved clarification {pending_clar_id}")
                session.pop('_pending_clarification_id', None)

        mode = session.get('mode', 'chat')
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        cm = get_cancel_manager()
        history = session.get('conversation_history', [])
        history.append({'role': 'user', 'content': user_input, 'timestamp': datetime.now().isoformat()})
        session['conversation_history'] = history

        latest_context = session.get('research_context', {})
        if self._should_start_execution(user_input, mode, latest_context, session_id):
            return await self._start_execution(session_id)

        depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
        question_suffixes = ('？', '?', '吗', '呢', '是什么', '是什么意思', '怎么', '如何')
        input_lower = user_input.strip().lower()
        is_depth_command = any(kw in input_lower for kw in depth_keywords) and not any(input_lower.endswith(s) for s in question_suffixes)
        if is_depth_command and latest_context.get('topic') and mode != 'framework':
            if mode == 'research':
                # R-FIX-6: 研究正在运行，不走直接中断，走正常意图分析+约束层
                # 消息会进入 _handle_research_msg() → _llm_converse() → _validate_action_for_state()
                logger.info(f"Depth research keyword detected but already in research mode for {session_id}, "
                             f"deferring to intent analysis + action constraint")
            else:
                logger.info(f"Depth research keyword detected for {session_id}, entering framework mode directly")
                return await self._enter_framework_mode(session_id, user_input)

        if mode == 'framework':
            if user_input.strip().lower() == 'cancel research':
                logger.info(f"User cancelled framework for {session_id}")
                conv_machine = session.get('state_machine')
                if conv_machine and conv_machine.can_transition_to(ConversationState.CLARIFYING):
                    conv_machine.transition(ConversationState.CLARIFYING)
                context = session.get('research_context', {})
                context['framework'] = None
                intent_state = self._get_or_create_intent_state(session)
                intent_state.clear_framework_aspects()
                self._save_dialogue_state(session_id, session, intent_state, conv_machine)
                self._sync_mode_with_state(session, conv_machine)
                return await self._handle_chat_mode(session_id, user_input, skip_lang_detect)
            return await self._handle_framework_mode(session_id, user_input)

        if mode == 'chat':
            return await self._handle_chat_mode(session_id, user_input, skip_lang_detect)

        if mode == 'research':
            input_lower = user_input.strip().lower()
            cancel_keywords = ('取消研究', 'cancel research', '停止研究', 'stop research', '终止研究', 'abort research')
            pause_keywords = ('暂停', 'pause', '暂停研究', 'pause research')
            resume_keywords = ('继续', '继续研究', 'resume', 'resume research', '继续执行', '继续运行')
            if any(kw in input_lower for kw in cancel_keywords):
                logger.info(f"Keyword cancel detected in research mode for {session_id}")
                return await self.cancel_research(session_id)
            if any(kw in input_lower for kw in pause_keywords):
                logger.info(f"Keyword pause detected in research mode for {session_id}")
                return await self.pause_research(session_id)
            if any(kw in input_lower for kw in resume_keywords) and cm.is_paused(session_id):
                logger.info(f"Keyword resume detected for paused {session_id}")
                return await self.resume_research(session_id)
            return await self._handle_research_msg(session_id, user_input, session)

        return {'error': f"Unknown mode: {mode}", 'error_code': 'UNKNOWN_MODE'}

    async def _handle_research_msg(self, session_id, user_input, session):
        """Handle user message during research execution"""
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        research_result = session.get('research_result')
        has_executor_task = session_id in self._executor_tasks and not self._executor_tasks[session_id].done()
        is_actually_running = bool(research_result.get('status') not in ('completed', 'cancelled', 'error')) if research_result else has_executor_task
        cm = get_cancel_manager()

        if research_result and research_result.get('status') in ('completed', 'completed_with_warnings'):
            session['mode'] = 'chat'
            logger.info(f"Research completed, entering chat mode for {session_id}")
            return await self._handle_chat_mode(session_id, user_input)
        if not has_executor_task and not research_result:
            logger.warning(f"Stale research mode for {session_id}, falling back to chat")
            session['mode'] = 'chat'
            session['current_step'] = 0
            session.pop('research_result', None)
            return await self._handle_chat_mode(session_id, user_input)

        if cm.is_paused(session_id):
            try:
                conv_result = await asyncio.wait_for(self._llm_converse(session_id, user_input), timeout=60)
            except asyncio.TimeoutError:
                logger.warning(f"LLM converse timed out for paused {session_id}, falling back to chat")
                return await self._handle_chat_mode(session_id, user_input)
            action = conv_result.get('action', 'continue_chat')
            if action == 'resume_research':
                return await self.resume_research(session_id)
            if action == 'modify_research':
                return await self._handle_modify_research(session_id=session_id, modifications=conv_result.get('modifications', {}), adjustment=conv_result.get('adjustment', user_input))
            if action == 'enter_framework':
                old = self._executor_tasks.pop(session_id, None)
                if old and not old.done():
                    old.cancel()
                session['mode'] = 'chat'
                context = session.get('research_context', {})
                if conv_result.get('topic'):
                    context['topic'] = conv_result['topic']
                if conv_result.get('directions'):
                    context['directions'] = conv_result.get('directions', [])
                fw_sections = conv_result.get('framework_sections')
                if fw_sections and isinstance(fw_sections, list) and len(fw_sections) > 0:
                    context['_suggested_sections'] = fw_sections
                fw_tree = conv_result.get('framework_tree')
                if fw_tree and isinstance(fw_tree, list) and len(fw_tree) > 0:
                    context['_framework_tree'] = fw_tree
                session['research_context'] = context
                return await self._enter_framework_mode(session_id, user_input)
            if action == 'regenerate_report':
                return await self._regenerate_report(session_id)
            return await self._handle_chat_mode(session_id, user_input)

        logger.info(f"User message during research: {user_input}")
        try:
            conv_result = await asyncio.wait_for(self._llm_converse(session_id, user_input), timeout=60)
        except asyncio.TimeoutError:
            logger.warning(f"LLM converse timed out during research for {session_id}, queuing message")
            return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': '消息分析超时，您的消息已记录。您可以说"暂停"后重新发送，或等待研究完成后回复。', 'suggestions': ['暂停研究', '继续等待'], 'next_step': 'continue_research'}
        except Exception as e:
            logger.error(f"LLM converse failed: {e}", exc_info=True)
            return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': '消息处理临时异常，您可以尝试"暂停"后重新发送。', 'suggestions': ['暂停研究'], 'next_step': 'continue_research'}

        if conv_result.get('status') == 'processing':
            return {'session_id': session_id, 'step': 0, 'mode': 'research', 'status': 'processing', 'message': conv_result.get('message', '正在处理您的请求...'), 'suggestions': [], 'next_step': 'tool_executing'}

        conv_machine = session.get('state_machine')
        raw_action = conv_result.get('action', 'continue_chat')
        action = self._validate_action_for_state(raw_action, conv_machine, user_input)
        if action != raw_action:
            logger.info(f"[R-FIX-1] Action constrained: {raw_action} → {action}")

        if action == 'inject_requirement':
            return await self._handle_inject_requirement(session_id=session_id, inject_ops=conv_result.get('inject_ops', []), user_message=user_input)
        if action == 'modify_research':
            cm.pause(session_id)
            old = self._executor_tasks.pop(session_id, None)
            if old and not old.done():
                old.cancel()
            if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
                if conv_machine.can_transition_to(ConversationState.PAUSED):
                    conv_machine.transition(ConversationState.PAUSED)
            return await self._handle_modify_research(session_id=session_id, modifications=conv_result.get('modifications', {}), adjustment=conv_result.get('adjustment', user_input))
        if action == 'enter_framework':
            cm.pause(session_id)
            old = self._executor_tasks.pop(session_id, None)
            if old and not old.done():
                old.cancel()
            if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
                if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                    conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
            session['mode'] = 'chat'
            context = session.get('research_context', {})
            if conv_result.get('topic'):
                context['topic'] = conv_result['topic']
            if conv_result.get('directions'):
                context['directions'] = conv_result.get('directions', [])
            fw_sections = conv_result.get('framework_sections')
            if fw_sections and isinstance(fw_sections, list) and len(fw_sections) > 0:
                context['_suggested_sections'] = fw_sections
                logger.info(f"[{session_id}] LLM suggested {len(fw_sections)} sections: {fw_sections}")
            fw_tree = conv_result.get('framework_tree')
            if fw_tree and isinstance(fw_tree, list) and len(fw_tree) > 0:
                context['_framework_tree'] = fw_tree
                logger.info(f"[{session_id}] LLM provided framework_tree with {len(fw_tree)} sections")
            session['research_context'] = context
            return await self._enter_framework_mode(session_id, user_input)

        return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': conv_result.get('message', ''), 'suggestions': conv_result.get('suggestions', []), 'next_step': 'continue_research'}

    def _validate_action_for_state(self, action: str, conv_machine, user_input: str) -> str:
        """R-FIX-1: 根据当前状态机状态约束LLM返回的action。
        EXECUTING状态下：重操作需用户明确关键词，否则降级；轻操作直接放行。
        PAUSED状态下：所有action合法。
        """
        if not conv_machine:
            return action
        current_state = conv_machine.current_state
        if current_state == ConversationState.PAUSED:
            return action
        if current_state == ConversationState.EXECUTING:
            HEAVY_ACTIONS = {
                'enter_framework': (
                    '重新规划', '重新研究', '重新开始', '换个方向', '重新设计',
                    'restart', 'redesign', 'start over', '重新来', '重做',
                    '换个框架', '重新框架', '重新制定', '重新启动',
                ),
                'modify_research': (
                    '修改', '调整', '改一下', '修订', '变更',
                    'modify', 'adjust', 'revise', 'change',
                ),
            }
            if action in HEAVY_ACTIONS:
                confirm_keywords = HEAVY_ACTIONS[action]
                text = user_input.strip().lower()
                if any(kw in text for kw in confirm_keywords):
                    return action
                fallback = 'inject_requirement' if action == 'modify_research' else 'continue_chat'
                logger.info(f"[R-FIX-1] {action} without explicit user intent, downgrading to {fallback}")
                return fallback
            return action
        return action

    def _get_cached_intent_result(self, session):
        """R-FIX-3: 从session中获取已缓存的意图分析结果"""
        context = session.get('research_context', {})
        cached = context.get('_cached_intent_result')
        if cached:
            try:
                from src.core.semantic_intent import DeepIntentResult
                return DeepIntentResult.from_dict(cached)
            except Exception as e:
                logger.warning(f"Failed to restore cached intent result: {e}")
        return None

    def _cache_intent_result(self, session, intent_result):
        """R-FIX-3: 缓存意图分析结果到session"""
        context = session.setdefault('research_context', {})
        try:
            context['_cached_intent_result'] = intent_result.to_dict()
        except Exception as e:
            logger.warning(f"Failed to cache intent result: {e}")

    def _should_start_execution(self, user_input, mode, context, session_id):
        """confirm start"""
        if mode != 'framework':
            return False
        if not context.get('framework'):
            return False
        if user_input.strip().lower() != 'confirm start':
            return False
        if session_id:
            session = session_manager.get(session_id)
            from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
            if get_cancel_manager().is_cancelled(session_id):
                if session and session.get('status') == 'cancelled':
                    logger.warning(f"confirm start but task was cancelled: {session_id}")
                    return False
            if session:
                conv_machine = session.get('state_machine')
                if conv_machine and not conv_machine.is_in_state(ConversationState.FRAMEWORK_CONFIRM):
                    logger.warning(f"confirm start but state is {conv_machine.current_state.value}, correcting")
                    conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        return True

    async def _handle_chat_mode(self, session_id, user_input, skip_lang_detect=False):
        """Handle chat mode interaction"""
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})

        if not skip_lang_detect:
            current_lang = detect_language(user_input).value
            session['language'] = current_lang
            set_global_language(Language(current_lang))

        intent_state = self._get_or_create_intent_state(session)
        conv_machine = self._get_or_create_conv_machine(session)
        cancel_flag = self._loop_cancel_flags.get(session_id, 0) + 1
        self._loop_cancel_flags[session_id] = cancel_flag

        try:
            conv_result = await self._llm_converse(session_id, user_input, conv_machine.current_state)
        except ValueError as e:
            logger.warning(f"LLM conversation ValueError, retrying once with lower temp: {e}")
            try:
                conv_result = await self._llm_converse(session_id, user_input, conv_machine.current_state, temperature=0.3, _json_retry=True)
            except Exception as e2:
                logger.error(f"LLM conversation retry also failed: {e2}")
                return self._fallback_response(session_id, context)
        except Exception as e:
            logger.error(f"LLM conversation failed: {e}")
            return self._fallback_response(session_id, context)

        if conv_result.get('status') == 'processing':
            if conv_result.get('topic'):
                context['topic'] = conv_result['topic']
            if conv_result.get('directions'):
                existing = context.get('directions', [])
                for d in conv_result['directions']:
                    if d not in existing:
                        existing.append(d)
                context['directions'] = existing
            session['research_context'] = context
            msg = conv_result.get('message', '')
            if msg:
                history = session.get('conversation_history', [])
                history.append({'role': 'assistant', 'content': msg, 'timestamp': datetime.now().isoformat()})
                session['conversation_history'] = history
            return {'session_id': session_id, 'step': 0, 'mode': 'chat', 'status': 'processing', 'message': conv_result.get('message', 'Querying information, please wait...'), 'suggestions': [], 'next_step': 'tool_executing'}

        if conv_result.get('topic'):
            new_topic = conv_result['topic']
            old_topic = context.get('topic')
            if old_topic and old_topic != new_topic:
                logger.info(f"Research topic updated: '{old_topic}' -> '{new_topic}'. Cleared directions and framework for fresh start.")
                context['topic'] = new_topic
                context['directions'] = []
                context['framework'] = None
                intent_state.reset_for_new_topic(new_topic)
            elif not old_topic and new_topic:
                logger.info(f"Research topic set: '{new_topic}'")
                context['topic'] = new_topic

        if conv_result.get('directions'):
            existing = context.get('directions', [])
            for d in conv_result['directions']:
                if d not in existing:
                    existing.append(d)
            context['directions'] = existing

        session['research_context'] = context
        intent_state.update_from_response(conv_result, user_input)

        llm_action = conv_result.get('action', '')
        if llm_action:
            target = self._resolve_transition(llm_action)
            if target:
                if conv_machine.can_transition_to(target):
                    conv_machine.transition(target)
                else:
                    logger.warning(f"[{session_id}] Cannot transition from {conv_machine.current_state.value} to {target.value}, skipping")

        self._save_dialogue_state(session_id, session, intent_state, conv_machine)
        self._sync_mode_with_state(session, conv_machine)

        action = llm_action if llm_action else 'continue_chat'

        if action == 'revise_report':
            logger.info(f"LLM returned revise_report for {session_id}")
            return await self._handle_v2_revision(session_id, conv_result)
        if action == 'enter_framework':
            fw_sections = conv_result.get('framework_sections')
            if fw_sections and isinstance(fw_sections, list) and len(fw_sections) > 0:
                context['_suggested_sections'] = fw_sections
                logger.info(f"[{session_id}] LLM suggested {len(fw_sections)} sections from conversation: {fw_sections}")
            fw_tree = conv_result.get('framework_tree')
            if fw_tree and isinstance(fw_tree, list) and len(fw_tree) > 0:
                context['_framework_tree'] = fw_tree
                logger.info(f"[{session_id}] LLM provided framework_tree with {len(fw_tree)} sections from conversation")
            session['research_context'] = context
            return await self._enter_framework_mode(session_id, user_input)
        if action == 'start_execution':
            logger.info(f"LLM returned legacy start_execution, redirecting to framework: {session_id}")
            return await self._enter_framework_mode(session_id, user_input)
        if action == 'regenerate_report':
            logger.info(f"LLM returned regenerate_report for {session_id}")
            return await self._regenerate_report(session_id)

        return self._chat_response(session_id, conv_result.get('message', ''), conv_result.get('suggestions', []))

    def _get_or_create_intent_state(self, session):
        """research_context"""
        context = session.get('research_context', {})
        state_dict = context.get('_dialogue_intent_state')
        if state_dict:
            try:
                return DialogueIntentState.from_dict(state_dict)
            except Exception as e:
                logger.warning(f"DialogueIntentState.from_dict failed: {e}, creating fresh instance")
        return DialogueIntentState()

    def _get_or_create_conv_machine(self, session):
        """state_machine"""
        machine = session.get('state_machine')
        if machine and isinstance(machine, ConversationStateMachine):
            return machine
        logger.warning('state_machine missing or invalid in session, creating new instance (previous state history lost)')
        return ConversationStateMachine()

    def _save_dialogue_state(self, session_id, session, intent_state, conv_machine):
        """research_context"""
        context = session.get('research_context', {})
        context['_dialogue_intent_state'] = intent_state.to_dict()
        context['_conversation_state'] = conv_machine.current_state.value
        session.update({'research_context': context, 'state_machine': conv_machine})

    def _update_intent_state_after_async(self, session):
        """research_context"""
        context = session.get('research_context', {})
        state_dict = context.get('_dialogue_intent_state')
        if not state_dict:
            return
        state_dict['research_turns'] = state_dict.get('research_turns', 0) + 1
        context['_dialogue_intent_state'] = state_dict
        session['research_context'] = context

    def _sync_mode_with_state(self, session, conv_machine):
        state = conv_machine.current_state
        if state in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
            if session.get('mode') != 'chat':
                session['mode'] = 'chat'
        elif state == ConversationState.FRAMEWORK_CONFIRM:
            if session.get('mode') != 'framework':
                session['mode'] = 'framework'
        elif state in (ConversationState.EXECUTING, ConversationState.PAUSED, ConversationState.PREVIEWING):
            if session.get('mode') != 'research':
                session['mode'] = 'research'
        elif state == ConversationState.COMPLETED:
            if session.get('mode') != 'chat':
                session['mode'] = 'chat'

    def _action_aligns_with_state(self, llm_action, target_state):
        """continue_chat"""
        alignment = {ConversationState.UNDERSTANDING: ['continue_chat', 'enter_framework'], ConversationState.CLARIFYING: ['continue_chat', 'enter_framework'], ConversationState.FRAMEWORK_CONFIRM: ['enter_framework']}
        return (llm_action in alignment.get(target_state, []))

    def _resolve_transition(self, llm_action):
        """enter_framework"""
        if llm_action == 'enter_framework':
            return ConversationState.FRAMEWORK_CONFIRM
        if llm_action == 'modify_research':
            return ConversationState.PAUSED
        return None

    def _build_dialogue_context(self, conversation_state):
        """Build dialogue phase guidance (without intent state injection)"""
        state_guidance = {ConversationState.UNDERSTANDING: '## Current Dialogue Phase: Understanding\nFocus on understanding the user\'s research need.\n- If the request is vague, ask 1-2 targeted questions.\n- Do NOT propose a research framework yet.\n', ConversationState.CLARIFYING: '## Current Dialogue Phase: Clarifying\nThe topic is identified but details may be missing.\n- Ask focused questions about specific gaps. Max 2 per turn.\n- If enough information, you may propose a framework.\n', ConversationState.FRAMEWORK_CONFIRM: '## Current Dialogue Phase: Framework Confirmation\nRequirements are clear. Propose a research framework.\n- Use action="enter_framework" with framework_sections.\n- If the topic has natural sub-structure (e.g., industry segments, regional breakdowns), also output "framework_tree" with hierarchical section→sub_section→points structure.\n', ConversationState.EXECUTING: '## Current Dialogue Phase: Research Executing\nResearch is actively running with professional agents working.\nCRITICAL RULES for action selection:\n- Default action: "continue_chat" — for confirmations, greetings, simple questions, status queries.\n- "inject_requirement" — ONLY when user clearly asks to add/remove/supplement sections.\n- "modify_research" — ONLY when user EXPLICITLY uses words like 修改/调整/修订/adjust/modify. Do NOT use this for vague suggestions.\n- "enter_framework" — ONLY when user EXPLICITLY uses words like 重新规划/重新开始/换个方向/restart/redesign. NEVER use this for simple messages like "继续" or "好的".\n- When in doubt, use "continue_chat" with a brief reassuring message.\n', ConversationState.PAUSED: '## Current Dialogue Phase: Research Paused\nResearch was interrupted. Cached data available.\n- Resume → resume_research; Modify → modify_research; Chat → continue_chat.\n', ConversationState.PREVIEWING: '## Current Dialogue Phase: Report Preview\nReport is being previewed.\n- Handle user feedback on the report.\n'}
        guidance = state_guidance.get(conversation_state, '')
        return f"""\n{guidance}\n"""

    def _sync_state_machine_to_framework(self, session, session_id):
        """state_machine"""
        conv_machine = session.get('state_machine')
        if not conv_machine:
            return
        if conv_machine.current_state in (ConversationState.CANCELLED, ConversationState.COMPLETED):
            logger.warning(f"[{session_id}] Cannot enter framework from terminal state {conv_machine.current_state.value}, skipping")
            return
        if conv_machine.current_state in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        elif conv_machine.current_state == ConversationState.PAUSED:
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        elif conv_machine.current_state == ConversationState.EXECUTING:
            if conv_machine.can_transition_to(ConversationState.PAUSED):
                conv_machine.transition(ConversationState.PAUSED)
                if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                    conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
            else:
                logger.warning(f"[{session_id}] Cannot transition EXECUTING→PAUSED→FRAMEWORK_CONFIRM, force setting")
                conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        if not conv_machine.is_in_state(ConversationState.FRAMEWORK_CONFIRM):
            logger.warning(f"[{session_id}] _enter_framework_mode but state is {conv_machine.current_state.value}, force setting to FRAMEWORK_CONFIRM")
            conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        session['state_machine'] = conv_machine

    def _build_research_running_context(self, session, session_id=None):
        """R-FIX-7b: 构建研究运行上下文，供LLM判断用户意图。"""
        mode = session.get('mode', 'chat')
        if mode != 'research':
            return ''
        research_context = session.get('research_context')
        if not research_context:
            return ''
        topic = research_context.get('topic', '')
        framework = research_context.get('framework', {})
        sections = framework.get('sections', [])
        research_result = session.get('research_result')
        if research_result and research_result.get('status') in ('completed', 'completed_with_warnings'):
            if not sections:
                return ''
            sections_str = ', '.join(sections[:8]) + ('...' if len(sections) > 8 else '')
            pending = session.get('_pending_section_injects', [])
            inject_hint = f" (Pending injects: {len(pending)})" if pending else ''
            return (
                f"\n## Research Status: COMPLETED\n"
                f"Topic: {topic}\n"
                f"Sections: {sections_str}{inject_hint}\n"
                f"The research has been completed. A report is available.\n"
                f"Rules for changes during research:\n"
                f"- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n"
                f"- User EXPLICITLY says 修改/调整/修订 → `modify_research` (pause + re-plan)\n"
                f"- User EXPLICITLY says 重新规划/重新开始/换个方向 → `enter_framework`\n"
                f"- Simple messages (继续/好的/ok/等) → `continue_chat`\n"
            )
        if not sections:
            sections_str = '(sections being determined)'
        else:
            sections_str = ', '.join(sections[:8]) + ('...' if len(sections) > 8 else '')
        task_progress = session.get('task_progress', {})
        progress_pct = task_progress.get('progress', 0)
        completed_agents = []
        data_point_count = 0
        if session_id:
            try:
                from src.core.storage.research_result_store import ResearchResultStore
                store = ResearchResultStore(storage_path="data")
                stored = store.load_result(session_id)
                if stored:
                    completed_agents = stored.get('completed_agents', [])
                    data_point_count = len(stored.get('data_points', []))
            except Exception:
                pass
        phase_1_done = sum(1 for ca in completed_agents if ca.get('agent_id', '').startswith('phase_1_') and ca.get('success'))
        phase_2_done = sum(1 for ca in completed_agents if ca.get('agent_id', '').startswith('phase_2_') and ca.get('success'))
        section_count = len(sections) if sections else 0
        if phase_2_done > 0:
            current_phase_desc = f"深度分析(Phase 2): {phase_2_done}/{section_count} sections done"
        elif phase_1_done > 0:
            current_phase_desc = f"数据采集(Phase 1): {phase_1_done}/{section_count} sections done"
        else:
            current_phase_desc = "编排/启动中"
        completed_hint = ''
        if phase_1_done > 0:
            completed_hint = f"\nData collection completed for: {phase_1_done} sections"
        if data_point_count > 0:
            completed_hint += f"\nData points collected: {data_point_count}"
        pending = session.get('_pending_section_injects', [])
        inject_hint = f" (Pending injects: {len(pending)})" if pending else ''
        return (
            f"\n## Research Status: RUNNING ({progress_pct:.0%})\n"
            f"Topic: {topic}\n"
            f"Framework sections: {sections_str}{inject_hint}\n"
            f"Current phase: {current_phase_desc}\n"
            f"{completed_hint}\n"
            f"Research is actively running. Agents are working on the above sections.\n"
            f"Rules for changes during research:\n"
            f"- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n"
            f"- User EXPLICITLY says 修改/调整/修订 → `modify_research` (pause + re-plan)\n"
            f"- User EXPLICITLY says 重新规划/重新开始/换个方向 → `enter_framework`\n"
            f"- Simple messages (继续/好的/ok/等) → `continue_chat`\n"
        )

    async def _llm_converse(self, session_id, user_input, conversation_state=None, temperature=None, _json_retry=False):
        """LLM driven dialogue with multi-turn tool loop (Phase 2)"""
        session = session_manager.get(session_id)
        if not session:
            return self._build_response({'message': 'Session not found.', 'action': 'continue_chat', 'topic': None, 'directions': [], 'suggestions': []}, None)
        context = session.get('research_context', {})
        history = session.get('conversation_history', [])
        llm_config = session.get('llm_config', {})
        recent_history = history[-10:] if history else []
        try:
            profile = PromptManager.get_instance().load_profile('conversation')
            system_prompt = profile.get_full_prompt()
        except (FileNotFoundError, ImportError):
            system_prompt = "You are a professional and friendly market research consultant named Zensers. Please analyze the user's research needs and provide appropriate responses."
        history_text = ''
        for msg in recent_history:
            role = 'User' if msg.get('role') == 'user' else 'Assistant'
            content = msg.get('content', '')
            if content:
                history_text += f"{role}: {content}\n"
        context_summary = ''
        if context.get('topic'):
            context_summary += f"Confirmed research topic: {context['topic']}\n"
        if context.get('directions'):
            context_summary += f"User interested directions: {', '.join(context['directions'])}\n"
        if context.get('topic') and context.get('framework'):
            context_summary += 'NOTE: If you decide to use action="enter_framework", you MUST also output "framework_sections" — an array of 4-8 section names derived from the topic and conversation.\nIf the topic has clear sub-structure (e.g., industry segments, regional breakdowns, product categories), ALSO output "framework_tree" — a hierarchical array where each section contains "name" and optional "sub_sections" (each with "name" and "points"). Prefer framework_tree over flat framework_sections when multi-level structure is natural.\n'
        tool_defs = self._tool_set.TOOL_DEFINITIONS
        tools_section = ''
        if tool_defs:
            tools_section = '\n## Tool Calling Capability\nWhen you need real-time information (date/time, web search, news, web content), you can add a `tool_call` field in the JSON to request tool invocation.\nAvailable tools:\n'
            for t in tool_defs:
                params_str = str(t['parameters']) if t['parameters'] else 'No parameters'
                tools_section += f"- **{t['name']}**: {t['description']} | Parameters: {params_str}\n"
            tools_section += '\nUsage: add `"tool_call": {"name": "tool_name", "arguments": {...}}` to the output JSON\nAfter tool call you will receive the result, please generate the final response based on it.\nIf no tool is needed, set tool_call to null.\n'
        _now = datetime.now()
        current_date = _now.strftime('%Y-%m-%d')
        current_time = _now.strftime('%H:%M:%S')
        current_year = _now.year
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        _cm5 = get_cancel_manager()
        paused_context = ''
        if _cm5.is_paused(session_id) and session.get('research_result'):
            report = session['research_result'].get('report', {})
            section_count = len(report.get('sections', []))
            paused_context = f"\n## Paused Research Context\nThe previous research on '{context.get('topic', '')}' was interrupted.\nCollected data is cached ({section_count} sections available).\nThe user may want to:\n- Resume → resume_research\n- Modify framework → modify_research\n- Regenerate from cache → regenerate_report\n- New question → continue_chat\n"
        if session.get('_paused_research_context'):
            rr = session.get('research_result', {})
            sc = len(rr.get('report', {}).get('sections', [])) if rr else 0
            paused_context = f"\n## Paused Research Context\nResearch on '{context.get('topic', '')}' is paused.\nCached: {sc} sections.\n- Resume → resume_research\n- Modify → modify_research\n- Regenerate → regenerate_report\n- Chat → continue_chat\n"
        sections_context = ''
        post_research_hint = ''
        if session.get('research_result'):
            report = session['research_result'].get('report', {})
            sections = report.get('sections', [])
            if sections:
                sl = '\n'.join(f"- {s.get('title', s.get('id', str(s)))}" if isinstance(s, dict) else f"- {s}" for s in sections)
                sections_context = f"\n## Existing Report Sections\n{sl}\nUse these exact section names in aspects when the user requests revision.\n"
            rs = session['research_result'].get('status', 'unknown')
            rst = session['research_result'].get('stages_completed', 0)
            post_research_hint = f"\n## Previous Research Context\nStatus: {rs} | Stages: {rst}\nThe research has completed and a session record exists.\nIf the user asks to retry or start a NEW research, use `enter_framework`.\nIf the user asks to regenerate or refresh the REPORT/DOCUMENT (e.g. 重新生成HTML, 重新生成报告, regenerate report), use `regenerate_report`.\nIf the user asks to revise specific sections, use `revise_report`.\nDO NOT trigger revise_report if:\n- The user is asking ABOUT the revision/modification feature itself\n- The user is reporting a bug, issue, or problem with the report generation\n- The user mentions functionality is 'broken', 'not working', '有问题', '不工作'\n- The user is analyzing or evaluating the report output, not requesting changes\nThese should use `continue_chat` instead.\n"
        dialogue_context = ''
        if conversation_state:
            dialogue_context = self._build_dialogue_context(conversation_state)
        domain_guard = '\n## SCOPE REMINDER\nYou are a professional market research assistant. But you can handle ANY question\nthe user asks — answer directly or search the web. You are not limited to research.\nOnly start a formal research framework when the user EXPLICITLY asks for it.\n\n'
        cancel_flag = self._loop_cancel_flags.get(session_id, 0)
        accumulated_context = ''
        tool_history = []
        parsed = {}
        MAX_ITERATIONS = self._get_max_tool_iterations()
        try:
            from src.core.session_streamer import SessionStreamer
        except ImportError:
            SessionStreamer = None
        for iteration in range(MAX_ITERATIONS):
            if self._loop_cancel_flags.get(session_id, 0) != cancel_flag:
                logger.info(f"Cancelling loop iteration {iteration} — new message detected")
                break
            if iteration == 0:
                rrc = self._build_research_running_context(session, session_id)
                user_prompt = self._build_initial_prompt(current_date, current_time, current_year, history_text, context_summary, dialogue_context, paused_context, sections_context, post_research_hint, tools_section, domain_guard, user_input, rrc)
                if _json_retry:
                    user_prompt = f"## CRITICAL: Your previous response contained errors.\nYou MUST respond with ONLY a valid JSON object. No markdown, no code fences, no explanation outside the JSON.\n\n{self._JSON_OUTPUT_SCHEMA}\n\n{user_prompt}"
            else:
                user_prompt = self._build_followup_prompt(accumulated_context, tool_history, user_input, history_text, dialogue_context)
            try:
                from src.config.settings import settings as app_settings
                _model = llm_config.get('model', app_settings.llm.model)
                _max_tokens = llm_config.get('max_tokens', app_settings.llm.max_tokens)
                _temperature = temperature if temperature is not None else app_settings.llm.temperature

                if SessionStreamer and iteration == 0:
                    full_content = ""
                    think_filter = _ThinkTagFilter()
                    try:
                        async for token in call_llm_stream(
                            prompt=user_prompt, system_prompt=system_prompt,
                            model=_model, max_tokens=_max_tokens, temperature=_temperature,
                        ):
                            full_content += token
                            for typ, text in think_filter.feed(token):
                                if typ == 'think':
                                    SessionStreamer.push_chat_thinking(session_id, text)
                                else:
                                    SessionStreamer.push_chat_token(session_id, text)
                        for typ, text in think_filter.flush():
                            if typ == 'think':
                                SessionStreamer.push_chat_thinking(session_id, text)
                            else:
                                SessionStreamer.push_chat_token(session_id, text)
                    except Exception as stream_err:
                        logger.warning(f"Stream failed (iteration {iteration}), degrading: {stream_err}")
                        result = await asyncio.wait_for(
                            call_llm(prompt=user_prompt, system_prompt=system_prompt,
                                     model=_model, max_tokens=_max_tokens, temperature=_temperature),
                            timeout=60)
                        if not result.get('success'):
                            raise ValueError(f"LLM call failed: {result.get('error', 'Unknown error')}")
                        full_content = result.get('content', '')
                else:
                    result = await asyncio.wait_for(
                        call_llm(prompt=user_prompt, system_prompt=system_prompt,
                                 model=_model, max_tokens=_max_tokens, temperature=_temperature),
                        timeout=60)
                    if not result.get('success'):
                        raise ValueError(f"LLM call failed: {result.get('error', 'Unknown error')}")
                    full_content = result.get('content', '')
            except asyncio.TimeoutError:
                logger.warning(f"LLM call timed out (iteration {iteration}), using accumulated results")
                break
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                break
            content = full_content
            if not content or not content.strip():
                raise ValueError('LLM returned empty content')
            json_str = self._extract_json_from_llm_content(content)
            if not json_str:
                logger.error(f"Could not extract JSON from LLM response (iteration {iteration}), content preview: {content[:200]}")
                if iteration == 0:
                    retry_content = await self._retry_json_only(system_prompt, llm_config, session_id)
                    if retry_content:
                        content = retry_content
                        json_str = self._extract_json_from_llm_content(content)
                if not json_str:
                    raise ValueError(f"LLM response contains no valid JSON: {content[:200]}")
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"LLM JSON parse failed (iteration {iteration}): {e}")
                if iteration == 0:
                    retry_content = await self._retry_json_only(system_prompt, llm_config, session_id)
                    if retry_content:
                        json_str = self._extract_json_from_llm_content(retry_content)
                        if json_str:
                            parsed = json.loads(json_str)
                if not parsed:
                    break
            tool_call = parsed.get('tool_call')
            if not tool_call or not isinstance(tool_call, dict):
                break
            tool_name = tool_call.get('name', '')
            tool_args = tool_call.get('arguments', {})
            logger.info(f"Tool execution (iteration {iteration + 1}): {tool_name}({tool_args})")
            try:
                from src.core.session_streamer import SessionStreamer
            except ImportError:
                SessionStreamer = None
            tool_display_names = {'web_search': 'Web Search Agent', 'news_search': 'News Search Agent', 'scrape_url': 'Content Scraper Agent', 'get_current_datetime': 'Date/Time Agent'}
            agent_name = tool_display_names.get(tool_name, f"Agent ({tool_name})")
            query_display = tool_args.get('query', tool_args.get('url', ''))
            if SessionStreamer:
                SessionStreamer.push_agent_message(session_id, {'agent_id': tool_name, 'agent_name': agent_name, 'action': 'searching', 'content': f"Searching for: {query_display[:100]}"})
            tool_result = await self._tool_set.execute_tool(tool_name, tool_args)
            if SessionStreamer:
                SessionStreamer.push_agent_message(session_id, {'agent_id': tool_name, 'agent_name': agent_name, 'action': 'completed', 'content': f"Completed: {tool_name}"})
            result_summary = json.dumps({k: v for k, v in tool_result.items() if k not in ('success', 'message', 'error')}, ensure_ascii=False)
            accumulated_context += f"\n### Tool: {tool_name} (iteration {iteration + 1})\nArguments: {json.dumps(tool_args, ensure_ascii=False)}\nResult:\n```json\n{result_summary}\n```\n"
            tool_history.append({'iteration': iteration + 1, 'name': tool_name, 'args': tool_args})
        if not parsed or not parsed.get('action'):
            logger.error(f"LLM conversation failed: parsed content is empty after {MAX_ITERATIONS} iterations")
            return self._build_response({'message': '抱歉，系统暂时无法处理您的请求，请重新描述。', 'action': 'continue_chat', 'topic': None, 'directions': [], 'suggestions': []}, None, accumulated_context or None)
        if accumulated_context:
            tool_names = [t['name'] for t in tool_history]
            tool_desc = '、'.join(tool_names)
            final_message = f"I've performed {len(tool_history)} search operations ({tool_desc}) on your request."
        else:
            final_message = "I wasn't able to complete the search. Please try again or rephrase."
        return self._build_response(parsed, None, accumulated_context or None)

    def _get_max_tool_iterations(self):
        """Get max tool iterations from config, fallback to 10"""
        try:
            from src.config.settings import settings
            return settings.conversation.max_tool_iterations
        except Exception:
            return 10

    def _build_initial_prompt(self, current_date, current_time, current_year, history_text, context_summary, dialogue_context, paused_context, sections_context, post_research_hint, tools_section, domain_guard, user_input, research_running_ctx):
        """Build the first-turn prompt for the multi-tool loop"""
        ctx = context_summary or '(Research topic not yet confirmed, need to guide user to express needs)'
        return f"""{current_date} {current_time} (This is the REAL current date — use it to determine what "latest" means. Do NOT call get_current_datetime.)\n\nCurrent conversation context:\n{history_text}\n\nExisting research information:\n{ctx}\n{dialogue_context}\n{paused_context}\n{sections_context}\n{post_research_hint}\n{research_running_ctx}\nLatest user message: {user_input}\n{tools_section}\n{domain_guard}\n## LANGUAGE RULE — CRITICAL (MUST FOLLOW BEFORE ANYTHING ELSE)\n\n**You MUST respond in the SAME language as the user's latest message.**\n- User writes in Chinese → your `message` field MUST be entirely in Chinese\n- User writes in English → your `message` field MUST be entirely in English\n- All data, quotes, and search results MUST be translated into the user's language\n- Never output mixed languages. Check your entire response before writing it.\n- This rule is ABSOLUTE. It cannot be overridden by any other instruction.\n\n## DATA FRESHNESS RULES (CRITICAL)\n\n**Today is {current_date}. The current year is {current_year}.**\n\nYou MUST follow these rules when generating search queries:\n\n1. **DO NOT hardcode years in search queries** — Unless the user explicitly says "2022 data" or "last year's numbers", do NOT add year constraints like "2023" or "2024" to your search query. Just search for the topic without year qualifiers. The search engine will return the most recent results.\n\n2. **Always get the latest data** — When the user asks about financial data, market size, sales figures, or any time-sensitive information, search for "latest" or "recent" data. Do NOT assume any specific year.\n\n3. **Example correct queries:**\n   - User: "比亚迪营收多少" → Query: `比亚迪 营收 净利润 最新财务数据` (NOT "比亚迪 2023 年营收")\n   - User: "新能源汽车市场多大" → Query: `新能源汽车 市场规模 最新` (NOT "2024 年新能源汽车市场规模")\n   - User: "特斯拉2022年销量" → Query: `特斯拉 2022 年 销量` (user specified year, include it)\n\n4. **When in doubt, prefer recency** — If search results contain both old and new information, prioritize the most recent. Add "最新" (latest) or sort parameters to your query.\n\n## Action Selection Rules — Task Complexity Analysis\n\nYou are the decision maker for task routing. Analyze the user's request and the full conversation context:\n\n**`"action": "continue_chat"` — DEFAULT choice for:**\n- Simple queries: "what's the best selling car", "find recent news about X", "what's the price of Y"\n- Data lookups that can be answered with a search\n- Casual conversation, clarifying needs, providing information\n- User just wants information, not a formal research report\n\n**`"action": "enter_framework"` — Trigger ONLY when user EXPLICITLY requests a formal research framework:\n\nA. Explicit research framework request:\n- User explicitly asks for a structured research report or formal analysis framework\n- "帮我做一份市场研究报告", "我需要一份行业分析报告"\n- "你形成一个详细的分析框架", "你形成一个框架", "形成框架" (user asks you to build a framework)\n- User wants to design, confirm, or redesign the research framework\n\nB. Framework review/confirmation request:\n- User explicitly asks to see or confirm the research framework/plan\n- "让我看看研究框架"、"框架确认"、"我必须明确研究框架"\n- "列出研究章节"、"研究计划确认"、"先明确框架"\n\nC. Research scope adjustment (non-execution phase only):\n- User proposes changes to the research scope/directions\n- "把XX加到研究里"、"去掉XX部分"、"不只XX，还要看YY"\n\n**⚠️ MANDATORY output when enter_framework**: You MUST ALSO output `framework_sections` (array of 4-8 section name strings). Derive them from the topic and conversation history. Example: ["市场规模分析", "竞争格局", "政策环境", "产业链分析"]\n**⚠️ framework_sections quality check**: Before outputting, review your sections: (1) NO duplicate or semantically overlapping sections — each must cover a distinct dimension; (2) sections must collectively form a coherent, logical research framework for the topic\n**⚠️ Priority rule**: If research is currently running (session.mode == "research"), scope adjustment inputs MUST trigger `modify_research` instead. `enter_framework` applies only in chat/framework modes.\n**⚠️ Do NOT trigger `enter_framework` for**: simple multi-dimensional queries, supplementary information during research, casual questions about multiple topics. These should use `continue_chat` or `modify_research`.\n\n**`"action": "regenerate_report"` — When paused research context is present and user wants to:\n- Regenerate the report from cached data\n- Continue the interrupted research\n- Retry after fixing an error\nThis skips data collection and re-uses cached results.\n\n**`"action": "revise_report"` — When a completed report exists and user wants to modify it:\nALL conditions must be met:\n1. A completed research report exists (research_result is present in session)\n2. User mentions modifying, updating, adding, or changing report content\n3. User is discussing the existing report, not requesting new research\nOutput fields:\n- `aspects`: list of section names (use exact names from the report sections list if available)\n- `adjustment`: the user's original request text (passed to the revision engine)\n- `revision_type`: "section" (partial) or "full" (full redo)\n\n**`"action": "modify_research"` — Only when user EXPLICITLY requests to pause or redesign:\n- "先停一下" / "暂停" / "我要重新设计" → modify_research\n- For supplementary inputs during research, prefer `inject_requirement` instead.\nOutput fields:\n- `modifications.add_aspects`: sections to add\n- `modifications.remove_aspects`: sections to remove\n- `modifications.modify_aspects`: {{old_name: new_name}} mapping\n- `adjustment`: the user's original request text\n\n**`"action": "resume_research"` — When research is paused and user wants to continue:\n- User says "继续研究", "恢复", "resume", "继续执行" or similar\n- Only valid when session has paused research context\n- This will resume the research from cached progress\n\n**`"action": "inject_requirement"` — During active research, inject requirements WITHOUT pausing:\n- Use this when user adds dimensions, supplements sections, or cancels sections — without asking to pause\n- DEFAULT action for requirement changes during research. Only use `modify_research` if user EXPLICITLY says "暂停" or "停一下"\n- Output `inject_ops`: array of operations:\n  - {{"op": "add_section", "section_name": "竞品分析"}} — add new section\n  - {{"op": "cancel_section", "section_name": "政策分析"}} — cancel section\n  - {{"op": "merge_to_section", "section_name": "市场规模", "requirement": "补充细分赛道数据"}} — merge requirement into section\n\n**Examples:**\n- "重新生成报告" → regenerate_report\n- "继续完成研究" → regenerate_report\n- "把报告生成出来" → regenerate_report\n- "修改第三节，增加市场规模数据" → revise_report\n- "第三部分写得再详细一些" → revise_report\n- "增加一个风险分析章节" → inject_requirement (运行时补充，不暂停研究)\n- "先停一下，我想改需求" → modify_research (明确要求暂停)\n- "我不需要某个章节了" → inject_requirement (op=cancel_section)\n\n**Examples:**\n- "比亚迪哪个车型销量最大" → continue_chat (simple data query, can answer with search)\n- "帮我分析一下新能源汽车行业的竞争格局和未来趋势" → enter_framework (A. multi-dimensional research)\n- "我必须明确研究框架" → **enter_framework (B. framework confirmation)** ← key fix\n- "让我看看你打算研究哪些方面" → enter_framework (B. framework review)\n- "把轩逸朗逸卡罗拉的销量对比加进去" → enter_framework (C. scope adjustment, chat mode) / modify_research (if research running)\n- "我不需要看框架了，直接开始" → continue_chat (declining framework, not a confirmation request)\n- "之前的框架没问题" → continue_chat (in chat mode) or confirm (in framework mode)\n- User says "非常好" or "ok" → continue_chat (just acknowledgment, not research request)\n\n**IMPORTANT**: DO NOT escalate simple data queries to research. Use continue_chat for single-point questions.\n\nPlease output JSON response based on the role."""

    def _build_followup_prompt(self, accumulated_context, tool_history, original_input, history_text, dialogue_context):
        """Build follow-turn prompt with tool execution results"""
        tool_list = '\n'.join(f"- {t['name']} (iteration {t['iteration']})" for t in tool_history)
        context_section = ''
        if history_text:
            context_section = f"""\n## Conversation Context (for reference)\n{history_text}\n"""
        if dialogue_context:
            context_section += f"""\n{dialogue_context}\n"""
        return f"""## Tool Execution Results\n\nThe following tools have been executed:\n\n{tool_list}\n\n--- Tool Results ---\n{accumulated_context}\n{context_section}\n## Continue or Finish\n\nBased on the above results, determine if you have enough information to answer the user's original request.\n\nOriginal request: "{original_input}"\n\n- If you have enough information → set `tool_call: null` and provide the final answer\n- If you need MORE information → set `tool_call` to request another tool\n- You CAN call the same tool again with a different query if needed\n- If results are empty/failed → use your existing knowledge to answer\n\n{self._JSON_OUTPUT_SCHEMA}\n"""

    def _extract_json_from_llm_content(self, content):
        """Extract JSON from LLM response content"""
        content = content.strip()
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            return json_match.group(1).strip()
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        if cleaned.startswith('{') or cleaned.startswith('['):
            brace_count = 0
            for i, ch in enumerate(cleaned):
                if ch in ('{', '['):
                    brace_count += 1
                elif ch in ('}', ']'):
                    brace_count -= 1
                if brace_count == 0:
                    return cleaned[:i + 1]
        json_in_text = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned)
        if json_in_text:
            return json_in_text.group(1).strip()
        return None

    async def _retry_json_only(self, system_prompt, llm_config, session_id):
        """Retry LLM call with stricter JSON-only instruction and lower temperature."""
        retry_prompt = f"""## CRITICAL: Your previous response was not valid JSON.\nYou MUST respond with ONLY a valid JSON object starting with `{{` and ending with `}}`.\nNo markdown, no code fences, no explanation before or after the JSON.\nNo natural language text outside the JSON structure.\n\n{self._JSON_OUTPUT_SCHEMA}\n\nOutput ONLY the JSON object now."""
        try:
            from src.config.settings import settings as app_settings
            result = await asyncio.wait_for(
                call_llm(prompt=retry_prompt, system_prompt=system_prompt,
                         model=llm_config.get('model', app_settings.llm.model),
                         max_tokens=llm_config.get('max_tokens', app_settings.llm.max_tokens), temperature=0.1),
                timeout=60)
            if not result.get('success'):
                return None
            content = result.get('content', '')
            if not content or not content.strip():
                return None
            logger.info(f"JSON retry succeeded for session {session_id}")
            return content
        except Exception as e:
            logger.warning(f"JSON retry LLM call failed for session {session_id}: {e}")
            return None

    def _build_response(self, parsed, tool_results, note):
        """Build standardized response dict from parsed LLM output"""
        response = {'status': 'done', 'message': parsed.get('message', ''), 'action': parsed.get('action', 'continue_chat'), 'topic': parsed.get('topic'), 'directions': parsed.get('directions', []), 'framework_sections': parsed.get('framework_sections'), 'framework_tree': parsed.get('framework_tree'), 'clarification_questions': parsed.get('clarification_questions', []), 'identified_aspects': parsed.get('identified_aspects', []), 'is_composite': parsed.get('is_composite', False), 'suggestions': parsed.get('suggestions', []), 'inject_ops': parsed.get('inject_ops', []), 'complexity': parsed.get('complexity', 'single'), 'research_types': parsed.get('research_types', []), 'hidden_requirements': parsed.get('hidden_requirements', [])}
        if note:
            response['_note'] = note
        return response

    def _check_cancelled(self, session_id):
        """Check if task has been cancelled"""
        session = session_manager.get(session_id)
        if not session:
            return False
        return session.get('status') == 'cancelled'

    def _cancel_existing_task(self, session_id):
        """Cancel old background task for the same session"""
        old_task = self._background_tasks.pop(session_id, None)
        if not old_task or old_task.done():
            return
        old_task.cancel()
        logger.info(f"Cancelled existing background task for {session_id}")

    async def _do_execute_tool_background(self, session_id, generation, tool_name, tool_args, system_prompt, llm_config):
        """Execute tool call chain in background: tool -> LLM synthesis -> SSE push"""
        try:
            from src.core.progress_streamer import ProgressStreamer
            from src.core.session_streamer import SessionStreamer
        except ImportError:
            SessionStreamer, ProgressStreamer = None, None
        if self._check_cancelled(session_id) or self._background_task_gen.get(session_id) != generation:
            self._background_tasks.pop(session_id, None)
            self._background_task_gen.pop(session_id, None)
            return
        tool_display_names = {'web_search': 'Web Search Agent', 'news_search': 'News Search Agent', 'scrape_url': 'Content Scraper Agent', 'get_current_datetime': 'Date/Time Agent'}
        agent_name = tool_display_names.get(tool_name, f"Agent ({tool_name})")
        query_display = tool_args.get('query', tool_args.get('url', ''))
        if SessionStreamer:
            SessionStreamer.push_agent_message(session_id, {'agent_id': tool_name, 'agent_name': agent_name, 'action': 'searching', 'content': f"Searching for: {query_display[:100]}"})
        tool_result = await self._tool_set.execute_tool(tool_name, tool_args)
        if self._check_cancelled(session_id) or self._background_task_gen.get(session_id) != generation:
            self._background_tasks.pop(session_id, None)
            self._background_task_gen.pop(session_id, None)
            return
        _session = session_manager.get(session_id)
        _sess_lang = _session.get('language', '') if _session else ''
        try:
            _lang_code = Language(_sess_lang) if _sess_lang else Language.ZH
        except ValueError:
            _lang_code = Language.ZH
        _lang_instruction = get_language_instruction(_lang_code)
        if tool_result.get('success'):
            result_data = {k: v for k, v in tool_result.items() if k not in ('success', 'message', 'error')}
            result_summary = json.dumps(result_data, ensure_ascii=False)
            synthesis_prompt = f"{_lang_instruction}\n\nYou called the tool **{tool_name}** with query: `{query_display[:200]}`\n\nHere is the returned data:\n\n```json\n{result_summary}\n```\n\nPlease generate the final response based on the above data. Do not output tool_call anymore (set to null).\n IMPORTANT: Set action to \"continue_chat\". Output the final JSON response."
        else:
            error_msg = tool_result.get('error', 'Unknown error')
            synthesis_prompt = f"{_lang_instruction}\n\nYou called the tool **{tool_name}** but execution failed: {error_msg}\n\nPlease respond to the user directly based on existing knowledge. Do not output tool_call anymore (set to null).\n IMPORTANT: Set action to \"continue_chat\". Output the final JSON response."
        try:
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        except ImportError:
            import sys, pathlib
            project_root = pathlib.Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        try:
            from src.config.settings import settings as app_settings
            model = llm_config.get('model', app_settings.llm.model)
            result = await asyncio.wait_for(
                llm_skill.execute(prompt=synthesis_prompt, system_prompt=system_prompt, model=model, max_tokens=llm_config.get('max_tokens', app_settings.llm.max_tokens)),
                timeout=60)
        except asyncio.CancelledError:
            logger.info(f"Background task cancelled for {session_id}")
            if ProgressStreamer:
                ProgressStreamer.push_chat_response(session_id, {'message': 'Previous information query has been cancelled.', 'action': 'continue_chat', 'topic': None, 'directions': [], 'suggestions': []})
            return None
        except Exception as e:
            logger.error(f"Background tool execution failed: {e}", exc_info=True)
            if ProgressStreamer:
                ProgressStreamer.fail_task(session_id, str(e))
                ProgressStreamer.push_chat_response(session_id, {'message': 'Sorry, encountered an issue while querying information. Please try again later.', 'action': 'continue_chat', 'topic': None, 'directions': [], 'suggestions': []})
            return None
        if not result or not result.get('success'):
            content = result.get('content', '') if result else ''
        else:
            content = result.get('content', '')
        json_str = self._extract_json_from_llm_content(content)
        if json_str:
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                parsed = {'message': content[:500]}
        else:
            parsed = {'message': content[:500] if content else 'Sorry, could not generate a valid response.'}
        response_data = {'message': parsed.get('message', ''), 'action': parsed.get('action', 'continue_chat'), 'topic': parsed.get('topic'), 'directions': parsed.get('directions', []), 'framework_sections': parsed.get('framework_sections'), 'clarification_questions': parsed.get('clarification_questions', []), 'identified_aspects': parsed.get('identified_aspects', []), 'is_composite': parsed.get('is_composite', False), 'suggestions': parsed.get('suggestions', []), 'inject_ops': parsed.get('inject_ops', [])}
        session = session_manager.get(session_id)
        if session:
            ctx = session.get('research_context', {})
            current_mode = session.get('mode', 'chat')
            if response_data.get('topic'):
                new_topic = response_data['topic']
                if ctx.get('topic') != new_topic:
                    ctx['topic'] = new_topic
                    if current_mode in ('chat', None, ''):
                        ctx['directions'] = []
                        ctx['framework'] = None
            if response_data.get('directions'):
                existing = ctx.get('directions', [])
                for d in response_data['directions']:
                    if d not in existing:
                        existing.append(d)
                ctx['directions'] = existing
            session['research_context'] = ctx
            self._update_intent_state_after_async(session)
            history = session.get('conversation_history', [])
            history.append({'role': 'assistant', 'content': response_data['message'], 'timestamp': datetime.now().isoformat(), 'tool_used': tool_name})
            session['conversation_history'] = history
        if ProgressStreamer:
            ProgressStreamer.push_chat_response(session_id, response_data)
        logger.info(f"Background tool execution completed: {session_id}")
        if self._background_task_gen.get(session_id) != generation:
            self._background_tasks.pop(session_id, None)
            self._background_task_gen.pop(session_id, None)
            return
        return 'completed'

    def _fallback_response(self, session_id, context):
        """Safe fallback when LLM fails — acknowledges issue without alarming user"""
        session = session_manager.get(session_id) if session_id else None
        lang = self._get_lang(session)
        existing_topic = context.get('topic')
        if not existing_topic and session:
            existing_topic = session.get('research_context', {}).get('topic')
        if existing_topic:
            return self._chat_response(session_id, self._l(f"抱歉，我临时遇到了问题。我们刚才在讨论 **{existing_topic}**，请再试一次。", f"Sorry, I encountered a temporary issue. We were discussing **{existing_topic}**, please try again.", lang))
        return self._chat_response(session_id, self._l('抱歉，我临时遇到了问题，请再试一次。你想研究什么？', 'Sorry, I encountered a temporary issue, please try again. What would you like to research?', lang))

    async def _llm_framework_modify(self, session_id, user_input):
        """Lightweight LLM call for framework modification — no tool routing, just framework reasoning."""
        session = session_manager.get(session_id)
        if not session:
            return {'action': 'modify', 'message': 'Session not found.', 'new_sections': None}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        sections = framework.get('sections', [])
        topic = context.get('topic', '')
        lang = self._get_lang(session)
        sections_str = '\n'.join(f"- {s}" for s in sections) if sections else '(no sections)'
        sections_tree = framework.get('sections_tree')
        tree_str = ''
        if sections_tree and isinstance(sections_tree, list) and len(sections_tree) > 0:
            tree_lines = []
            for i, sec in enumerate(sections_tree, 1):
                tree_lines.append(f"{i}. {sec.get('name', '')}")
                for j, sub in enumerate(sec.get('sub_sections', []), 1):
                    tree_lines.append(f"   {i}.{j} {sub.get('name', '')}")
                    for k, pt in enumerate(sub.get('points', []), 1):
                        tree_lines.append(f"      {i}.{j}.{k} {pt}")
            tree_str = '\nCurrent multi-level structure:\n' + '\n'.join(tree_lines)
        user_lang = 'Chinese' if lang == 'zh' else 'English'
        prompt = f"""You are helping the user refine their research framework.\n\nCurrent research topic: {topic}\nCurrent framework sections:\n{sections_str}{tree_str}\n\nUser's request: {user_input}\n\n## Rules\n\n1. If the user confirms (e.g., '确认', '没问题', 'ok', '好的', '开始吧', 'looks good', 'proceed'), set action="confirm".\n2. If the user wants ANY change, set action="modify" with COMPLETE new section list in `new_sections`.\n3. If the user wants to cancel, set action="cancel".\n4. When action="modify", `new_sections` MUST be a non-empty array.\n5. Remove duplicate or semantically overlapping sections.\n6. When modifying a multi-level framework, also provide `new_framework_tree` reflecting the updated structure.\n7. Your `message` MUST be in {user_lang}.\n\nOutput JSON only:\n{{"action": "confirm" | "modify" | "cancel", "message": "...", "new_sections": [...], "new_framework_tree": [{{"name": "...", "sub_sections": [{{"name": "...", "points": [...]}}]}}]}}\n"""
        try:
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        except ImportError:
            import sys, pathlib
            project_root = pathlib.Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        try:
            from src.config.settings import settings as app_settings
            llm_config = session.get('llm_config', {})
            result = await asyncio.wait_for(
                llm_skill.execute(prompt=prompt, model=llm_config.get('model', app_settings.llm.model), max_tokens=llm_config.get('max_tokens', app_settings.llm.max_tokens)),
                timeout=30)
        except Exception:
            return {'action': 'modify', 'message': "I understand you'd like to adjust the framework. Please tell me what changes you'd like to make.", 'new_sections': None}
        if not result.get('success'):
            return {'action': 'modify', 'message': "I understand you'd like to adjust the framework. Please tell me what changes you'd like to make.", 'new_sections': None}
        content = result.get('content', '')
        json_str = self._extract_json_from_llm_content(content)
        if not json_str:
            if content:
                return {'action': 'modify', 'message': content[:500], 'new_sections': None}
            return {'action': 'modify', 'message': 'I see. How would you like to change the framework?', 'new_sections': None}
        try:
            parsed = json.loads(json_str)
            return {'action': parsed.get('action', 'modify'), 'message': parsed.get('message', ''), 'new_sections': parsed.get('new_sections'), 'new_framework_tree': parsed.get('new_framework_tree')}
        except json.JSONDecodeError:
            return {'action': 'modify', 'message': content[:500], 'new_sections': None}

    async def _handle_framework_mode(self, session_id, user_input):
        """
        Handle framework confirmation mode — fully LLM-driven.
        Uses lightweight LLM call (_llm_framework_modify), not the chat-mode _llm_converse.
        """
        session = session_manager.get(session_id)
        if not session:
            return self._chat_response(session_id, self._l('Session not found.', 'Session not found.', 'zh'))
        context = session.get('research_context', {})
        lang = self._get_lang(session)
        framework = context.get('framework')
        topic = context.get('topic', '')
        if not framework:
            logger.warning(f"[{session_id}] framework is None in _handle_framework_mode, regenerating")
            return await self._enter_framework_mode(session_id, user_input)
        conv_result = await self._llm_framework_modify(session_id, user_input)
        action = conv_result.get('action', 'modify')
        if action == 'cancel':
            conv_machine = session.get('state_machine')
            if conv_machine and conv_machine.can_transition_to(ConversationState.CLARIFYING):
                conv_machine.transition(ConversationState.CLARIFYING)
            context['framework'] = None
            session['research_context'] = context
            intent_state = self._get_or_create_intent_state(session)
            intent_state.clear_framework_aspects()
            self._save_dialogue_state(session_id, session, intent_state, conv_machine)
            self._sync_mode_with_state(session, conv_machine)
            return self._chat_response(session_id, conv_result.get('message', 'Cancelled.'))
        if action == 'confirm':
            if not topic or not framework.get('sections'):
                return self._framework_response(session_id, self._l('研究框架尚未完整定义，请先完成框架设置。', 'The research framework is not yet complete. Please finish setting it up first.', lang))
            return await self._start_execution(session_id)
        new_sections = conv_result.get('new_sections')
        new_framework_tree = conv_result.get('new_framework_tree')
        if new_sections and isinstance(new_sections, list) and len(new_sections) > 0:
            new_framework = {'topic': topic, 'sections': new_sections, 'output_type': framework.get('output_type', 'industry_report'), 'depth': framework.get('depth', 'standard'), 'region': framework.get('region', 'China'), 'time_range': framework.get('time_range', 'Last 3 years')}
            if new_framework_tree and isinstance(new_framework_tree, list) and len(new_framework_tree) > 0:
                new_framework['sections_tree'] = new_framework_tree
            elif framework.get('sections_tree'):
                existing_tree = framework['sections_tree']
                existing_flat = [s.get('name', '') for s in existing_tree if s.get('name')]
                if set(new_sections) == set(existing_flat):
                    new_framework['sections_tree'] = existing_tree
                else:
                    preserved_tree = []
                    for new_sec in new_sections:
                        matched = [s for s in existing_tree if s.get('name') == new_sec]
                        if matched:
                            preserved_tree.append(matched[0])
                        else:
                            preserved_tree.append({'name': new_sec, 'sub_sections': []})
                    new_framework['sections_tree'] = preserved_tree
        else:
            new_framework = self._generate_research_framework(context)
        context['framework'] = new_framework
        session['research_context'] = context
        return self._framework_response(session_id, conv_result.get('message', self._l(f"已根据你的意见调整研究框架：\n\n**研究主题**: {topic}\n\n**研究框架**:\n{self._format_framework(new_framework)}", f"Updated the research framework based on your feedback:\n\n**Research Topic**: {topic}\n\n**Research Framework**:\n{self._format_framework(new_framework)}", lang)))

    async def _enter_framework_mode(self, session_id, user_input):
        """
        Enter framework confirmation mode.
        Generate research framework based on collected information, wait for user confirmation.
        Idempotent: if a framework with sections already exists, return it unchanged.
        """
        session = session_manager.get(session_id)
        if not session:
            return {'session_id': session_id, 'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})
        lang = self._get_lang(session)
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        if get_cancel_manager().is_cancelled(session_id) or session.get('status') == 'cancelled':
            logger.warning(f"[{session_id}] Cannot enter framework — session was cancelled")
            return {'session_id': session_id, 'error': 'Session was cancelled', 'message': self._l('该研究任务已被取消，请新建一个任务。', 'This research task was cancelled. Please start a new one.', lang)}
        existing_fw = context.get('framework')
        if existing_fw and existing_fw.get('sections'):
            logger.info(f"Framework already exists for {session_id}, returning existing")
            session['mode'] = 'framework'
            self._sync_state_machine_to_framework(session, session_id)
            return self._framework_response(session_id, self._l(f"研究框架已经准备好了：\n\n**研究主题**: {context.get('topic')}\n\n**研究框架**:\n{self._format_framework(existing_fw)}\n\n请确认是否满足需求。", f"The research framework is ready:\n\n**Research Topic**: {context.get('topic')}\n\n**Research Framework**:\n{self._format_framework(existing_fw)}\n\nPlease confirm if this meets your needs.", lang))
        suggested = context.get('_suggested_sections', [])
        directions = context.get('directions', [])
        fw_tree = context.get('_framework_tree')
        if fw_tree and isinstance(fw_tree, list) and len(fw_tree) > 0:
            all_sections = [s.get('name', '') for s in fw_tree if s.get('name')]
            all_sections = [s for s in all_sections if s]
            logger.info(f"[{session_id}] Using framework_tree: {len(all_sections)} sections derived from tree")
        elif suggested and directions:
            all_sections = self._merge_sections_dedup(suggested, directions)
            logger.info(f"[{session_id}] Merged {len(suggested)} suggested + {len(directions)} directions = {len(all_sections)} sections (after dedup)")
        elif suggested:
            all_sections = suggested
        else:
            all_sections = directions
        if all_sections:
            framework = {'topic': context.get('topic', 'Research Report'), 'sections': all_sections, 'output_type': 'industry_report', 'depth': context.get('details', {}).get('depth', 'standard'), 'region': context.get('details', {}).get('region', 'China'), 'time_range': context.get('details', {}).get('time_range', 'Last 3 years')}
            if fw_tree and isinstance(fw_tree, list) and len(fw_tree) > 0:
                framework['sections_tree'] = fw_tree
            logger.info(f"[{session_id}] Framework derived from conversation: {len(all_sections)} sections")
        elif not directions:
            framework = self._generate_research_framework(context)
        else:
            framework = await self._build_framework_with_fallback(session_id, context)
        context.pop('_suggested_sections', None)
        context.pop('_framework_tree', None)
        context['framework'] = framework
        session['research_context'] = context
        session['mode'] = 'framework'
        self._sync_state_machine_to_framework(session, session_id)
        return self._framework_response(session_id, self._l(f"根据我们的讨论，我整理了以下研究框架：\n\n**研究主题**: {context.get('topic')}\n\n**研究框架**:\n{self._format_framework(framework)}\n\n请确认这个框架是否满足你的需求，或提出修改建议。", f"Based on our discussion, I have organized the following research framework:\n\n**Research Topic**: {context.get('topic')}\n\n**Research Framework**:\n{self._format_framework(framework)}\n\nPlease confirm if this framework meets your needs, or suggest modifications.", lang))

    async def _start_execution(self, session_id):
        """
        Start executing research
        User has confirmed. Priority use of intelligent routing to generate execution plan,
        fall back to handcrafted plan on failure.
        """
        session = session_manager.get(session_id)
        if not session:
            return {'session_id': session_id, 'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})
        topic = context.get('topic', '')
        framework = context.get('framework', {})
        sections = framework.get('sections', [])
        sections_tree = framework.get('sections_tree')
        if not topic:
            return {'session_id': session_id, 'error': 'No research topic specified', 'error_code': 'EMPTY_TOPIC', 'status': 'error'}
        if not sections:
            suggested = context.get('_suggested_sections', [])
            if suggested:
                framework['sections'] = suggested
                sections = suggested
                context['framework'] = framework
                session['research_context'] = context
                context.pop('_suggested_sections', None)
                logger.info(f"[{session_id}] Recovered {len(sections)} sections from _suggested_sections in _start_execution")
            else:
                return {'session_id': session_id, 'error': 'No research sections defined', 'error_code': 'EMPTY_SECTIONS', 'status': 'error'}
        state_machine = session.get('state_machine')
        if state_machine:
            state_machine.transition(ConversationState.EXECUTING)
        session['mode'] = 'research'
        session['current_step'] = 6
        final_plan = {'topic': topic, 'output_type': framework.get('output_type', 'industry_report'), 'aspects': sections, 'sections_tree': sections_tree, 'section_details': self._build_section_details_from_tree(sections_tree) if sections_tree else [], 'region': context.get('details', {}).get('region', 'China'), 'time_range': context.get('details', {}).get('time_range', 'Last 3 years'), 'framework': framework.get('depth', 'standard'), 'language': session.get('language', 'zh')}
        logger.info(f"Display plan generated: {len(sections)} sections")
        session['final_plan'] = final_plan
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        _cm_exec = get_cancel_manager()
        if _cm_exec.is_paused(session_id):
            _cm_exec.resume(session_id)
            logger.info(f"Cleared stale pause flag for {session_id} before starting execution")
        from src.api.research_executor import get_executor
        from src.core.progress_streamer import ProgressStreamer
        executor = get_executor()
        task = safe_create_task(executor.execute(session_id, final_plan, session_manager), name=f"exec_{session_id}")
        self._executor_tasks[session_id] = task
        task.add_done_callback(lambda _: self._executor_tasks.pop(session_id, None))
        ProgressStreamer.set_disconnect_callback(session_id, self._on_sse_disconnect)
        return {'session_id': session_id, 'task_id': session_id, 'step': 6, 'mode': 'research', 'status': 'running', 'message': self._l(f"研究任务已启动！\n\n**研究主题**: {topic}\n\n正在执行研究，请耐心等待...", f"Research task has been started!\n\n**Research Topic**: {topic}\n\nExecuting research, please wait...", session.get('language', 'zh')), 'final_plan': final_plan, 'next_step': 'execute'}

    async def _start_execution_with_routing(self, session_id, routing_result):
        """Start execution using pre-computed IntelligentRoutingResult (BP1 fix)"""
        session = session_manager.get(session_id)
        if not session:
            return {'session_id': session_id, 'error': 'Session not found'}
        session['mode'] = 'research'
        session['current_step'] = 6
        user_request = routing_result.user_request
        topic = routing_result.requirement.get('topic', user_request)
        final_plan = {'topic': topic, 'output_type': routing_result.requirement.get('output_type', 'industry_report'), 'aspects': routing_result.requirement.get('aspects', []), 'region': routing_result.requirement.get('region', 'China'), 'time_range': routing_result.requirement.get('time_range', 'Last 3 years'), 'framework': 'standard', 'language': session.get('language', 'zh'), '_routing_result': routing_result.to_dict()}
        session['final_plan'] = final_plan
        from src.api.research_executor import get_executor
        from src.core.progress_streamer import ProgressStreamer
        executor = get_executor()
        task = safe_create_task(executor.execute(session_id, final_plan, session_manager), name=f"exec_route_{session_id}")
        self._executor_tasks[session_id] = task
        task.add_done_callback(lambda _: self._executor_tasks.pop(session_id, None))
        ProgressStreamer.set_disconnect_callback(session_id, self._on_sse_disconnect)
        return {'session_id': session_id, 'task_id': session_id, 'step': 6, 'mode': 'research', 'status': 'running', 'message': self._l(f"研究任务已启动！\n\n**研究主题**: {topic}\n\n正在执行研究，请耐心等待...", f"Research task has been started!\n\n**Research Topic**: {topic}\n\nExecuting research, please wait...", session.get('language', 'zh')), 'final_plan': final_plan, 'next_step': 'execute'}

    def _is_greeting_simple(self, user_input):
        """Determine if it's a pure greeting or irrelevant question"""
        user_input_stripped = user_input.strip()
        user_input_lower = user_input_stripped.lower()
        pure_greetings = ('hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'who are you', 'what are you')
        if user_input_lower in pure_greetings:
            return True
        if user_input_stripped in pure_greetings:
            return True
        for g in ('hello', 'hi', 'hey'):
            if user_input_stripped.startswith(g):
                remaining = user_input_stripped[len(g):].strip()
                if not remaining:
                    return True
                if all(not c.isalpha() for c in remaining):
                    return True
        return False

    def _get_greeting_response(self, session_id, user_input):
        """Generate greeting/chit-chat response — localized by session language"""
        session = session_manager.get(session_id) if session_id else None
        lang = self._get_lang(session)
        user_input_s = user_input.strip()
        if any(q in user_input_s.lower() for q in ('who are you', 'what are you')):
            return self._chat_response(session_id, self._l('我是 **Zensers**，一个智能市场研究助手。\n\n我可以帮你：\n- **行业分析**：深入研究行业现状和发展趋势\n- **企业研究**：分析目标公司的业务、竞争力和财务\n- **市场评估**：估算市场容量、增长率并发现机会\n- **竞争分析**：对比主要竞争对手的战略和市场地位\n- **政策研究**：评估政策环境对行业的影响\n\n请告诉我你想研究什么？', 'I am **Zensers**, an intelligent market research assistant.\n\nI can help you with:\n- **Industry Analysis**: Deep research into industry status and trends\n- **Company Research**: Analyze target company\'s business, competitiveness and financials\n- **Market Sizing**: Estimate market capacity, growth rate and opportunities\n- **Competitive Analysis**: Compare major competitors\' strategies and market position\n- **Policy Research**: Evaluate policy environment impact on industry\n\nPlease tell me what you would like to research?', lang))
        return self._chat_response(session_id, self._l('你好！我是 **Zensers** 市场研究助手。\n\n我可以帮助你做专业的市场研究，包括行业分析、企业研究、市场评估、竞争分析等。\n\n你想研究什么？', 'Hello! I am **Zensers** market research assistant.\n\nI can help you with professional market research, including industry analysis, company research, market sizing, competitive analysis, and more.\n\nWhat would you like to research?', lang))

    def _generate_dynamic_suggestions(self, context):
        """Dynamically generate suggestion options based on context"""
        topic = context.get('topic', '')
        directions = context.get('directions', [])
        suggestions = [{'id': 'start_research', 'label': 'Start Research', 'example': 'Ready to start research'}]
        common_directions = (('market_size', 'Market Size', 'Understand market size and growth'), ('competition', 'Competition', 'Analyze major competitors'), ('trend', 'Trends', 'Research future trends'), ('policy', 'Policy', 'Analyze policy impact'), ('chain', 'Industry Chain', 'Research industry chain structure'))
        for dir_id, label, example in common_directions:
            if label not in directions:
                suggestions.append({'id': dir_id, 'label': label, 'example': example})
        return suggestions[:6]

    @staticmethod
    def _tokenize(s):
        return re.findall(r'\w+', s)

    @staticmethod
    def _bigrams(s):
        return {s[i:i+2] for i in range(len(s) - 1)}

    @staticmethod
    def _has_cjk(s):
        return any('\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf' for c in s)

    def _merge_sections_dedup(self, primary, secondary):
        merged = list(primary)
        for sec in secondary:
            is_dup = False
            for i, existing in enumerate(merged):
                if sec == existing:
                    is_dup = True
                    break
                if existing in sec or sec in existing:
                    if len(sec) > len(existing):
                        merged[i] = sec
                    is_dup = True
                    break
                sec_tokens = set(self._tokenize(sec))
                existing_tokens = set(self._tokenize(existing))
                if not sec_tokens or not existing_tokens:
                    continue
                if self._has_cjk(sec) and self._has_cjk(existing):
                    sec_bg = self._bigrams(sec)
                    existing_bg = self._bigrams(existing)
                    overlap = sec_bg & existing_bg
                    ratio = len(overlap) / max(len(sec_bg), len(existing_bg), 1)
                    if ratio >= 0.6:
                        if len(sec) > len(existing):
                            merged[i] = sec
                        is_dup = True
                        break
                else:
                    overlap = sec_tokens & existing_tokens
                    ratio = len(overlap) / max(len(sec_tokens), len(existing_tokens), 1)
                    if ratio >= 0.65:
                        if len(sec) > len(existing):
                            merged[i] = sec
                        is_dup = True
                        break
            if not is_dup:
                merged.append(sec)
        return merged

    def _generate_research_framework(self, context):
        """
        
        Generate research framework from collected context.
        
        The user's directions ARE the sections — Executive Summary and
        Conclusions are optional, added only if the user asked for them.
        No template dependency — this is a pure direction-to-sections mapping.
        
        """
        topic = context.get('topic', '')
        directions = context.get('directions', [])
        details = context.get('details', {})
        seen = set()
        sections = []
        for d in directions:
            d_lower = d.lower().strip()
            if d_lower not in seen and len(d_lower) > 1:
                seen.add(d_lower)
                sections.append(d)
        return {'topic': topic, 'sections': sections, 'output_type': 'industry_report', 'depth': details.get('depth', 'standard'), 'region': details.get('region', 'China'), 'time_range': details.get('time_range', 'Last 3 years')}

    async def _build_framework_with_fallback(self, session_id, context):
        """
        Build research framework with multi-level fallback chain.
        Called when both _suggested_sections and directions are empty.
        Priority: LLM inference -> template sections -> default aspects.
        """
        topic = context.get('topic', '')
        details = context.get('details', {})
        inferred = await self._infer_framework_sections_from_conversation(session_id)
        if inferred and len(inferred) >= 3:
            logger.info(f"[{session_id}] Fallback L1: LLM inferred {len(inferred)} sections: {inferred}")
            return {'topic': topic, 'sections': inferred, 'output_type': 'industry_report', 'depth': details.get('depth', 'standard'), 'region': details.get('region', 'China'), 'time_range': details.get('time_range', 'Last 3 years')}
        template_sections = self._get_template_sections_for_topic(topic)
        if template_sections and len(template_sections) >= 3:
            logger.info(f"[{session_id}] Fallback L2: template generated {len(template_sections)} sections: {template_sections}")
            return {'topic': topic, 'sections': template_sections, 'output_type': 'industry_report', 'depth': details.get('depth', 'standard'), 'region': details.get('region', 'China'), 'time_range': details.get('time_range', 'Last 3 years')}
        default_sections = self._generate_default_sections_for_topic(topic)
        logger.info(f"[{session_id}] Fallback L3: using keyword-based defaults ({len(default_sections)} sections)")
        return {'topic': topic, 'sections': default_sections, 'output_type': 'industry_report', 'depth': details.get('depth', 'standard'), 'region': details.get('region', 'China'), 'time_range': details.get('time_range', 'Last 3 years')}

    async def _infer_framework_sections_from_conversation(self, session_id):
        """
        Use LLM to infer research framework sections from conversation history.
        Called when _enter_framework_mode has no directions or _suggested_sections.
        Returns empty list on failure (triggers next fallback level).
        """
        session = session_manager.get(session_id)
        if not session:
            return []
        context_data = session.get('research_context', {})
        topic = context_data.get('topic', '')
        history = session.get('conversation_history', [])
        lang = self._get_lang(session)
        if not history or not topic:
            return []
        history_text = ''
        for msg in history[-8:]:
            role = 'User' if msg.get('role') == 'user' else 'Assistant'
            content = msg.get('content', '')
            if content:
                history_text += f"{role}: {content}\n"
        user_lang = 'Chinese' if lang == 'zh' else 'English'
        prompt = f"""Based on the following conversation about a research topic, derive appropriate report sections for a professional research framework.\n\nResearch topic: {topic}\n\nConversation history:\n{history_text}\n\nRequirements:\n- Output 4-8 sections that comprehensively cover the research topic\n- Section names must be in {user_lang}\n- Reflect what was actually discussed or requested in the conversation\n- NO duplicate or semantically overlapping sections\n- Output ONLY a JSON array of section name strings, no other text\n- Example format: ["Market Size Analysis", "Competitive Landscape", "Policy Environment"]\n"""
        try:
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        except ImportError:
            import sys, pathlib
            project_root = pathlib.Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
        try:
            from src.config.settings import settings as app_settings
            result = await asyncio.wait_for(
                llm_skill.execute(prompt=prompt, model=app_settings.llm.model, max_tokens=app_settings.llm.max_tokens, temperature=0.3),
                timeout=30)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Failed to infer framework sections: {e}")
            return []
        if not result or not result.get('success'):
            logger.warning(f"LLM section inference failed: {result.get('error') if result else 'no result'}")
            return []
        content = result.get('content', '').strip()
        json_match = re.search(r'\[[\s\S]*?\]', content)
        if not json_match:
            logger.warning(f"LLM returned unparseable section list: {content[:200]}")
            return []
        try:
            sections = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []
        if not isinstance(sections, list):
            return []
        cleaned = [s.strip() for s in sections if s.strip()]
        if not cleaned:
            return []
        return cleaned

    def _get_template_sections_for_topic(self, topic):
        """
        Get template sections from SmartClarifier/TemplateLoader for a given topic.
        Falls back to keyword-matched templates.
        """
        if not topic:
            return []
        topic_lower = topic.lower()
        output_type_hint = 'industry_report'
        company_kw = ('公司', 'company', '企业', 'firm', 'corp')
        tech_kw = ('技术', 'technology', '芯片', 'chip', 'ai', '人工智能', '半导体', 'semiconductor')
        policy_kw = ('政策', 'policy', '监管', 'regulation')
        if any(kw in topic_lower for kw in company_kw):
            output_type_hint = 'company_research'
        try:
            sections = self._get_section_details_for_type(output_type_hint)
            if sections and len(sections) >= 3:
                result = []
                for s in sections:
                    if isinstance(s, dict):
                        result.append(s.get('id', s.get('name', '')))
                    else:
                        result.append(str(s))
                if result:
                    return result
        except Exception:
            pass
        if any(kw in topic_lower for kw in company_kw):
            return ('公司概况', '业务分析', '财务分析', '竞争优势', '风险因素', '增长前景')
        if any(kw in topic_lower for kw in tech_kw):
            return ('行业概况与技术背景', '市场规模与增长', '竞争格局分析', '产业链分析', '技术发展趋势', '政策与监管环境')
        if any(kw in topic_lower for kw in policy_kw):
            return ('政策概述', '政策背景与动机', '对行业的影响分析', '对重点企业的影响', '国际比较', '应对策略建议')
        return ('市场规模', '竞争格局', '产业链分析', '发展趋势', '政策环境', '投资机会')

    def _generate_default_sections_for_topic(self, topic):
        """
        
        Generate default research sections as final fallback.
        Uses keywords from config/research_frameworks.yaml focus_areas as reference.
        
        """
        if not topic:
            return ('研究概述', '现状分析', '竞争格局', '关键驱动因素', '发展趋势', '风险与挑战')
        topic_lower = topic.lower()
        company_kw = ('公司', 'company', '企业', 'firm', '集团', 'corp')
        tech_kw = ('技术', 'technology', '芯片', 'chip', 'ai', '人工智能', '半导体', 'semiconductor')
        policy_kw = ('政策', 'policy', '监管', 'regulation', '合规', 'compliance')
        industry_kw = ('行业', 'industry', '市场', 'market', '产业', 'sector')
        if any(kw in topic_lower for kw in company_kw):
            return ('公司概况', '业务分析', '竞争格局', '财务分析', '发展战略', '风险评估', '投资建议')
        if any(kw in topic_lower for kw in tech_kw):
            return ('行业概况与技术背景', '市场规模与增长', '竞争格局分析', '产业链分析', '技术发展趋势', '政策与监管环境', '投资机会与风险')
        if any(kw in topic_lower for kw in policy_kw):
            return ('政策概述', '政策背景与动机', '对行业的影响分析', '对重点企业的影响', '国际比较', '应对策略建议')
        if any(kw in topic_lower for kw in industry_kw):
            return ('行业概述', '市场规模与增长', '竞争格局', '产业链分析', '发展趋势', '政策环境', '投资机会与风险')
        return ('研究概述', '现状分析', '竞争格局', '关键驱动因素', '发展趋势', '风险与挑战')

    def _build_section_details_from_tree(self, sections_tree):
        """Build section_details with sub_sections from sections_tree for execution chain"""
        if not sections_tree:
            return []
        details = []
        for st in sections_tree:
            name = st.get('name', '')
            sub_sections = st.get('sub_sections', [])
            detail = {
                'id': name.lower().replace(' ', '_'),
                'name': name,
                'content': name,
                'sub_sections': [
                    {'name': sub.get('name', ''), 'points': sub.get('points', [])}
                    for sub in sub_sections if sub.get('name')
                ]
            }
            details.append(detail)
        return details

    def _format_framework(self, framework):
        """Format framework for display with optional section descriptions and multi-level tree"""
        sections_tree = framework.get('sections_tree')
        if sections_tree and isinstance(sections_tree, list) and len(sections_tree) > 0:
            lines = []
            for i, section in enumerate(sections_tree, 1):
                name = section.get('name', '')
                lines.append(f"{i}. {name}")
                sub_sections = section.get('sub_sections', [])
                for j, sub in enumerate(sub_sections, 1):
                    sub_name = sub.get('name', '')
                    lines.append(f"   {i}.{j} {sub_name}")
                    points = sub.get('points', [])
                    for k, point in enumerate(points, 1):
                        lines.append(f"      {i}.{j}.{k} {point}")
            return '\n'.join(lines)

        sections = framework.get('sections', [])
        raw_details = framework.get('section_details', {})
        section_details = {}
        if isinstance(raw_details, list):
            for s in raw_details:
                if isinstance(s, dict):
                    sid = s.get('id', s.get('name', ''))
                    section_details[sid] = s
        elif isinstance(raw_details, dict):
            section_details = raw_details
        lines = []
        for i, section in enumerate(sections, 1):
            detail = section_details.get(section, {}) if isinstance(section_details, dict) else {}
            desc = detail.get('description', '') if isinstance(detail, dict) else ''
            if desc:
                lines.append(f"{i}. {section} — {desc}")
            else:
                lines.append(f"{i}. {section}")
        return '\n'.join(lines)

    def _get_lang(self, session):
        """Get user language from session, defaulting to 'zh'"""
        if session:
            return session.get('language', 'zh')
        return 'zh'

    def _l(self, msg_zh, msg_en, lang):
        """Localize a message based on language code"""
        if lang == 'zh':
            return msg_zh
        return msg_en

    def _chat_response(self, session_id, message='', suggestions=None, **kwargs):
        """Generate chat response and save assistant message to history"""
        session = session_manager.get(session_id)
        if session:
            history = session.get('conversation_history', [])
            history.append({'role': 'assistant', 'content': message, 'timestamp': datetime.now().isoformat()})
            session['conversation_history'] = history
        if suggestions is None:
            suggestions = []
        return {'session_id': session_id, 'step': 0, 'mode': 'chat', 'message': message, 'instruction': '', 'suggestions': suggestions, 'next_step': 'continue_chat'}

    def _framework_response(self, session_id, message, suggestions=None):
        """Generate framework confirmation response and save assistant message to history"""
        session = session_manager.get(session_id)
        framework_data = None
        if session:
            history = session.get('conversation_history', [])
            history.append({'role': 'assistant', 'content': message, 'timestamp': datetime.now().isoformat()})
            session['conversation_history'] = history
            framework_data = session.get('research_context', {}).get('framework')
        if suggestions is None:
            suggestions = []
        return {'session_id': session_id, 'step': 5, 'mode': 'framework', 'message': message, 'instruction': '', 'suggestions': suggestions, 'framework': framework_data, 'next_step': 'confirm_framework'}

    async def handle_interact(self, session_id, step, response):
        """
        Handle interaction step response
        POST /api/research/interact
        """
        session = session_manager.get(session_id)
        clarification_id = response.get('clarification_id')
        if clarification_id:
            event = self._pending_clarifications.get(clarification_id)
            if event and not event.is_set():
                user_text = response.get('text', response.get('message', 'y'))
                self._clarification_responses[clarification_id] = user_text
                event.set()
                return {'status': 'ok', 'message': 'clarification received'}
        if not session:
            if step == 0:
                user_message = response.get('text', response.get('message', ''))
                new_session_id = f"ses_{uuid.uuid4().hex[:8]}"
                logger.info(f"Auto-creating session {new_session_id} (original {session_id} not found)")
                state_machine = ConversationStateMachine(research_id=new_session_id)
                detected_lang = detect_language(user_message).value
                session_manager.create(new_session_id, {
                    'user_input': user_message, 'state_machine': state_machine,
                    'clarifier': SmartClarifier(), 'created_at': datetime.now(),
                    'current_step': 0, 'mode': 'chat', 'language': detected_lang,
                    'conversation_history': [],
                    'research_context': {'topic': None, 'directions': [], 'framework': None, 'details': {}}})
                set_global_language(Language(detected_lang))
                return await self._handle_user_message(new_session_id, user_message)
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        if step == 0:
            mode = session.get('mode', 'chat')
            user_message = response.get('text', response.get('message', ''))
            suggestion_id = response.get('suggestion_id', response.get('id', ''))
            skip_lang = False
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
                skip_lang = True
            if not user_message:
                return {'error': 'Invalid response', 'error_code': 'INVALID_RESPONSE'}
            return await self._handle_user_message(session_id, user_message, skip_lang_detect=skip_lang)
        return await self._handle_research_flow(session_id, step, response)

    async def _handle_research_flow(self, session_id, step, response):
        """Handle research flow steps"""
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found'}
        clarifier = session.get('clarifier')
        if not clarifier:
            return {'error': 'Clarifier not found'}
        if step == 1:
            output_type = response.get('output_type', 'research_report')
            step2 = clarifier.select_output_type(output_type)
            session['current_step'] = 2
            session['output_type'] = output_type
            return {'session_id': session_id, 'step': 2, 'mode': 'research', 'message': step2['message'], 'instruction': step2['instruction'], 'framework_options': step2.get('framework_options', []), 'next_step': 'select_framework'}
        if step == 2:
            template_id = response.get('framework_id', 'detailed')
            if template_id:
                clarifier.select_template(template_id)
            clarifier.select_framework(response.get('framework_id', 'detailed'))
            session['current_step'] = 3
            sections_detail = session.get('section_details', [])
            sections = [{'id': s['id'], 'title': s.get('name', s['id']), 'description': s.get('description', ''), 'required': s.get('required', False), 'selected': True} for s in sections_detail]
            return {'session_id': session_id, 'step': 3, 'mode': 'research', 'message': 'Please confirm section contents', 'sections': sections, 'next_step': 'confirm_sections'}
        if step == 3:
            selected = response.get('selected_sections', [])
            if not selected:
                selected = [s['id'] for s in session.get('section_details', [])]
            session['selected_sections'] = selected
            session['current_step'] = 4
            output_type = session.get('output_type', 'industry_report')
            fw_config = get_framework_config(output_type)
            raw_params = fw_config.get_interaction_parameters()
            interaction_params = None
            if raw_params:
                try:
                    from src.core.interaction_parameter import InteractionParameterSet
                    param_set = InteractionParameterSet.from_yaml_dict(raw_params)
                    if param_set:
                        interaction_params = param_set.to_list()
                except Exception:
                    pass
            if not interaction_params:
                interaction_params = [{'id': 'region', 'type': 'select', 'label': 'Research Region', 'default': 'China', 'options': [{'value': 'China', 'label': 'China'}, {'value': 'Global', 'label': 'Global'}]}, {'id': 'time_range', 'type': 'select', 'label': 'Time Range', 'default': 'Last 3 years', 'options': [{'value': 'Last 1 year', 'label': 'Last 1 year'}, {'value': 'Last 3 years', 'label': 'Last 3 years'}, {'value': 'Last 5 years', 'label': 'Last 5 years'}]}]
            return {'session_id': session_id, 'step': 4, 'mode': 'research', 'message': 'Please set research parameters', 'parameters': {'parameters': interaction_params}, 'next_step': 'set_parameters'}
        if step == 4:
            session['current_step'] = 5
            session['custom_params'] = response
            summary = {'topic': session.get('user_input', ''), 'output_type': session.get('output_type', ''), 'sections': session.get('selected_sections', []), 'parameters': response}
            return {'session_id': session_id, 'step': 5, 'mode': 'research', 'message': 'Parameters confirmed', 'summary': summary, 'next_step': 'confirm_research'}
        if step == 5:
            confirmed = response.get('confirmed', False)
            if not confirmed:
                return {'session_id': session_id, 'step': 5, 'status': 'cancelled', 'message': 'Cancelled', 'next_step': 'cancelled'}
            session['current_step'] = 6
            output_type = session.get('output_type', 'industry_report')
            aspects = ['Market Size', 'Competitive Landscape', 'Development Trends']
            selected_sections = session.get('selected_sections', aspects)
            final_plan = {'topic': session.get('user_input', ''), 'output_type': output_type, 'aspects': selected_sections}
            session['final_plan'] = final_plan
            from src.api.research_executor import get_executor
            executor = get_executor()
            safe_create_task(executor.execute(session_id, final_plan, session_manager), name=f"exec_step5_{session_id}")
            return {'session_id': session_id, 'task_id': session_id, 'step': 6, 'mode': 'research', 'status': 'running', 'message': 'Research task started', 'final_plan': final_plan, 'next_step': 'execute'}
        return {'error': 'Invalid step', 'error_code': 'INVALID_STEP'}

    async def quick_start(self, user_input, template_id, user_id=None, llm_config=None, custom_params=None, auto_confirm=False, template_context=None):
        """
        Template quick start (/template command entry)
        Default: enters interaction flow at Step 4 (parameter settings).
        With auto_confirm=True: LLM extracts params, creates session at step 6.
        """
        template_id = template_id.replace('-', '_')
        TEMPLATES = {
            'industry_research': {'output_type': 'industry_report', 'aspects': ('市场定义', '市场规模', '增长驱动', '市场细分', '竞争格局')},
            'company_analysis': {'output_type': 'company_research', 'aspects': ('公司概况', '业务分析', '财务分析', '竞争优势', '风险因素', '增长前景')},
            'market_sizing': {'output_type': 'industry_report', 'aspects': ('市场定义', '市场规模', '增长驱动', '市场细分', '竞争格局')},
            'competitive_analysis': {'output_type': 'company_research', 'aspects': ('竞争格局', '主要竞争对手', '市场份额', '竞争策略', '进入壁垒')},
            'investment_research': {'output_type': 'industry_report', 'aspects': ('投资机会', '市场展望', '团队分析', '财务分析', '风险评估', '估值分析')},
        }
        template = TEMPLATES.get(template_id)
        if not template:
            return {'error': f"Unknown template: {template_id}", 'error_code': 'UNKNOWN_TEMPLATE'}
        output_type = template['output_type']
        aspects = template['aspects']
        params = custom_params or {}
        if auto_confirm:
            section_details = self._get_section_details_for_type(output_type)
            selected_sections = list(aspects[:8])
            extraction_context = template_context or user_input
            extracted = await self._extract_params_from_context(extraction_context, output_type, params)
            params.update(extracted)
            task_id = f"research_{uuid.uuid4().hex[:8]}"
            final_plan = {'topic': user_input, 'output_type': output_type, 'aspects': selected_sections}
            session_data = {
                'user_input': user_input, 'template_id': template_id,
                'output_type': output_type, 'aspects': aspects,
                'selected_sections': selected_sections, 'section_details': section_details,
                'final_plan': final_plan, 'params': params,
                'current_step': 6, 'mode': 'research', 'status': 'running',
                'created_at': datetime.now()
            }
            session_manager.create(task_id, session_data)
            from src.api.research_executor import get_executor
            executor = get_executor()
            task = safe_create_task(executor.execute(task_id, final_plan, session_manager), name=f"exec_quick_{task_id}")
            task.add_done_callback(lambda _: self._executor_tasks.pop(task_id, None))
            self._executor_tasks[task_id] = task
            return {'session_id': task_id, 'task_id': task_id, 'step': 6, 'mode': 'research', 'status': 'running',
                    'message': f"Starting research with template **{template_id}**.",
                    'plan': {'topic': user_input, 'output_type': output_type, 'aspects': aspects}}
        task_id = f"research_{uuid.uuid4().hex[:8]}"
        clarifier = SmartClarifier()
        clarifier.start(user_input)
        clarifier.select_output_type(output_type)
        clarifier.select_framework('detailed')
        fw_config = get_framework_config(output_type)
        raw_params = fw_config.get_interaction_parameters()
        interaction_params = None
        if raw_params:
            try:
                from src.core.interaction_parameter import InteractionParameterSet
                param_set = InteractionParameterSet.from_yaml_dict(raw_params)
                if param_set:
                    interaction_params = param_set.to_list()
            except Exception:
                pass
        if not interaction_params:
            interaction_params = [
                {'id': 'region', 'type': 'select', 'label': 'Research Region', 'default': 'China',
                 'options': [{'value': 'China', 'label': 'China'}, {'value': 'Global', 'label': 'Global'}]},
                {'id': 'time_range', 'type': 'select', 'label': 'Time Range', 'default': 'Last 3 years',
                 'options': [{'value': 'Last 1 year', 'label': 'Last 1 year'},
                             {'value': 'Last 3 years', 'label': 'Last 3 years'},
                             {'value': 'Last 5 years', 'label': 'Last 5 years'}]}
            ]
        section_details = self._get_section_details_for_type(output_type) or []
        selected_sections = [s['id'] for s in section_details[:8]] if section_details else list(aspects[:8])
        session_data = {
            'user_input': user_input, 'user_id': user_id,
            'clarifier': clarifier, 'created_at': datetime.now(),
            'current_step': 4, 'mode': 'framework',
            'template_id': template_id, 'output_type': output_type,
            'aspects': aspects, 'llm_config': llm_config,
            'selected_sections': selected_sections, 'section_details': section_details,
            'final_plan': {'topic': user_input, 'output_type': output_type, 'aspects': aspects, 'sections': selected_sections}
        }
        for key in ('region', 'time_range', 'depth', 'company_name', 'market',
                     'primary_company', 'policy_name', 'quarter', 'year', 'call_date'):
            if key in params:
                session_data[key] = params[key]
        if params:
            session_data['custom_params'] = params
        session_manager.create(task_id, session_data)
        sections = [{'id': s['id'], 'title': s.get('name', s['id']),
                     'description': s.get('description', ''),
                     'required': s.get('required', False),
                     'selected': s['id'] in selected_sections} for s in section_details[:8]]
        return {'session_id': task_id, 'task_id': task_id, 'step': 4, 'mode': 'framework',
                'status': 'awaiting_params',
                'message': f"Selected **{template['output_type']}** template. Please configure the research parameters",
                'instruction': 'Please set research parameters to continue',
                'template': template_id, 'parameters': {'parameters': interaction_params},
                'sections': sections, 'next_step': 'set_parameters'}

    async def _extract_params_from_context(self, context, output_type, default_params):
        """
        Use LLM to extract research parameters from conversation context.
        Falls back to default_params on any error.
        """
        fw_config = get_framework_config(output_type)
        raw_params = fw_config.get_interaction_parameters()
        if not raw_params:
            return default_params
        param_descriptions = []
        for key, config in raw_params.items():
            label = config.get('label', {}).get('en', key)
            options = [o['value'] for o in config.get('options', [])]
            param_descriptions.append(f"  - {key} ({label}): options = {options}")
        prompt = f"Extract research parameters from user conversation.\n\nConversation:\n{context}\n\nParameters:\n{chr(10).join(param_descriptions)}\n\nDefault values: {json.dumps(default_params, ensure_ascii=False)}\n\nReturn ONLY a JSON object with extracted values.\nUse default value if a parameter is not mentioned.\nDo NOT include explanations.\n"
        try:
            from src.skills.llm_skill import LLMSkill
            llm = LLMSkill()
            result = await llm.execute(prompt=prompt)
            if isinstance(result, dict):
                raw = result.get('content', '')
                if not raw:
                    return default_params
            else:
                raw = str(result)
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if match:
                extracted = json.loads(match.group(1))
            else:
                extracted = json.loads(raw)
            if not extracted or not isinstance(extracted, dict):
                return default_params
            merged = dict(default_params)
            for k, v in extracted.items():
                if v and v != '':
                    merged[k] = v
            return merged
        except json.JSONDecodeError:
            try:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
                if match:
                    return json.loads(match.group(1))
            except Exception:
                pass
            return default_params
        except Exception as e:
            logger.warning(f"LLM param extraction failed, using defaults: {e}")
            return default_params

    def _get_section_details_for_type(self, output_type):
        """Get section details by output type"""
        try:
            from src.core.orchestrator.smart_clarifier import OutputType, TemplateLoader
            loader = TemplateLoader()
            templates = loader.get_templates_by_type(OutputType(output_type))
            if templates:
                return templates[0].sections
            return []
        except Exception:
            return []

    async def get_preview(self, task_id, format='html'):
        """
        Get preview document
        Fixes:
        - Direct session lookup
        - Ensures preview HTML file exists by copying from orchestrator output if needed
        """
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Task not found', 'error_code': 'TASK_NOT_FOUND'}
        research_result = session.get('research_result', {})
        if not research_result or research_result.get('status') not in ('completed', 'completed_with_warnings'):
            return {'task_id': task_id, 'preview_url': None, 'html_content': None, 'preview_format': format, 'download_url': None}
        preview_path = PreviewStorage.path(task_id)
        if not preview_path.exists():
            output_path = research_result.get('document_path', '') or research_result.get('output_path', '')
            if output_path:
                src = Path(output_path)
                if src.exists():
                    preview_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, preview_path)
        preview_url = None
        html_content = None
        if preview_path.exists():
            preview_url = PreviewStorage.url(task_id)
            html_content = preview_path.read_text(encoding='utf-8')
        download_url = None
        for candidate_dir in [Path('data/reports') / task_id, Path('data') / task_id]:
            if candidate_dir.exists():
                docs = sorted(candidate_dir.glob('*.docx')) + sorted(candidate_dir.glob('*.html'))
                if docs:
                    download_url = f"/api/v1/download/{task_id}"
                    break
        return {'task_id': task_id, 'preview_url': preview_url, 'html_content': html_content, 'preview_format': format, 'download_url': download_url}

    async def handle_feedback(self, session_id, action, section=None, adjustment=None):
        """Handle preview feedback"""
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        if action == 'confirm':
            if self._knowledge_manager and not self._dream_mode_running:
                self._dream_mode_running = True
                loop = asyncio.get_running_loop()
                _run_dream = lambda: None
                loop.run_in_executor(None, _run_dream)
            return {'session_id': session_id, 'status': 'completed', 'message': 'Report confirmed, generating final document...'}
        if action == 'revise':
            return {'session_id': session_id, 'status': 'revising', 'message': f"Revising section: {section}"}
        return {'error': 'Invalid action', 'error_code': 'INVALID_ACTION'}

    def get_sections(self, task_id):
        """Get report section list"""
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        research_result = session.get('research_result', {})
        sections = research_result.get('report', {}).get('sections', [])
        if not sections:
            sections = research_result.get('sections', [])
        return {'task_id': task_id, 'sections': sections}

    async def revise_sections(self, task_id, aspects=None, adjustment=None):
        """遗留 API 端点 (main.py L371) — 已迁移到 v2 修订管道"""
        logger.info(f"revise_sections (legacy) for {task_id}, routing to v2")
        conv_result = {'adjustment': adjustment or '', 'aspects': aspects or [], 'revision_type': 'section'}
        return await self._handle_v2_revision(task_id, conv_result)

    async def pause_research(self, task_id):
        """Pause research task — save snapshot + set flag + notify frontend. No Task.cancel()."""
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        from src.core.progress_streamer import ProgressStreamer
        cm = get_cancel_manager()
        state_machine = session.get('state_machine')
        if state_machine:
            try:
                state_machine.transition(ConversationState.PAUSED)
            except Exception as e:
                logger.warning(f"State transition to PAUSED failed: {e}")
        await self._save_cancel_snapshot(task_id, session)
        cm.pause(task_id)
        try:
            from src.core.task_persistence import TaskPersistenceManager
            tp = TaskPersistenceManager()
            task = tp.load_task(task_id)
            if task:
                task.pause('Paused by user')
                tp.save_task(task)
        except Exception as e:
            logger.warning(f"Failed to persist pause state: {e}")
        ProgressStreamer.pause_task(task_id, 'Task paused by user')
        return {'task_id': task_id, 'status': 'paused', 'message': 'Research task paused'}

    async def resume_research(self, task_id):
        """Resume research task — clear flag + wake Engine. With snapshot recovery Path B."""
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        from src.core.progress_streamer import ProgressStreamer
        cm = get_cancel_manager()
        rr = session.get('research_result')
        if rr and rr.get('status') in ('completed', 'completed_with_warnings'):
            return {'task_id': task_id, 'status': 'completed', 'message': 'Research already completed while paused'}
        if session.get('status') == 'cancelled' or cm.is_cancelled(task_id):
            return {'task_id': task_id, 'status': 'cancelled', 'message': 'Research was cancelled, cannot resume'}
        if task_id not in self._executor_tasks or self._executor_tasks[task_id].done():
            logger.warning(f"Resume called but engine already dead for {task_id}, attempting snapshot recovery")
            snapshot = await self._load_cancel_snapshot(task_id)
            if snapshot and snapshot.get('pending_sections'):
                return await self._resume_from_snapshot(task_id, session, snapshot)
            return {'task_id': task_id, 'status': 'failed', 'message': 'Research engine has stopped, please start a new task'}
        cm.resume(task_id)
        state_machine = session.get('state_machine')
        if state_machine and state_machine.can_transition_to(ConversationState.EXECUTING):
            try:
                state_machine.transition(ConversationState.EXECUTING)
            except Exception as e:
                logger.warning(f"State transition to EXECUTING failed: {e}")
        ProgressStreamer.resume_task(task_id, 'Task resumed by user')
        return {'task_id': task_id, 'status': 'resumed', 'message': 'Research task resumed'}

    async def _resume_from_snapshot(self, task_id, session, snapshot):
        """Resume research from a saved cancel snapshot when the engine is dead.

        Rebuilds the research plan with only pending sections and starts a new executor.
        """
        from src.api.research_executor import get_executor
        pending_sections = snapshot.get('pending_sections', [])
        completed_sections = snapshot.get('completed_sections', [])
        context = snapshot.get('research_context', {})
        framework = context.get('framework', {})
        framework['sections'] = completed_sections + pending_sections
        context['framework'] = framework
        session['research_context'] = context
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        topic = context.get('topic', '')
        try:
            adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
            routing_result = adapter.analyze_incremental(
                user_request=f"Resume research for pending sections",
                requirement={'topic': topic, 'aspects': pending_sections},
                completed_aspects=completed_sections,
                topic=topic)
            new_plan = {}
            if hasattr(routing_result, 'execution_plan'):
                plan = routing_result.execution_plan
                if hasattr(plan, 'to_dict'):
                    new_plan = plan.to_dict()
            new_plan['topic'] = topic
            new_plan['output_type'] = framework.get('output_type', 'industry_report')
            new_plan['skip_phases'] = getattr(routing_result, 'skip_phases', [])
        except Exception as e:
            logger.warning(f"Routing failed during snapshot resume for {task_id}: {e}")
            new_plan = session.get('final_plan', {})
        session['final_plan'] = new_plan
        session['mode'] = 'research'
        session['status'] = 'running'
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        get_cancel_manager().resume(task_id)
        state_machine = session.get('state_machine')
        if state_machine and state_machine.can_transition_to(ConversationState.EXECUTING):
            try:
                state_machine.transition(ConversationState.EXECUTING)
            except Exception as e:
                logger.warning(f"State transition to EXECUTING failed during snapshot resume: {e}")
        executor = get_executor()
        resume_task = safe_create_task(executor.execute(task_id, new_plan, session_manager), name=f"resume_{task_id}")
        self._executor_tasks[task_id] = resume_task
        resume_task.add_done_callback(lambda _: self._executor_tasks.pop(task_id, None))
        from src.core.progress_streamer import ProgressStreamer
        ProgressStreamer.resume_task(task_id, 'Resumed from snapshot')
        logger.info(f"Resumed research from snapshot for {task_id}: {len(pending_sections)} pending sections")
        return {'task_id': task_id, 'status': 'resumed', 'message': f"Research resumed from snapshot. {len(pending_sections)} sections remaining."}

    async def _generate_documents_from_cache(self, session_id, research_result_data, output_dir, session):
        """Generate preview + document from cached research result, skipping orchestrator."""
        from src.core.progress_streamer import update_progress, complete_task, fail_task
        update_progress(session_id, 0.0)
        try:
            preview_input = {'action': 'produce_document', 'research_result': research_result_data, 'output_format': 'html', 'output_dir': str(output_dir), 'task_id': session_id}
            preview_result = await self._orchestrator._document_agent.execute(preview_input)
            if isinstance(preview_result, dict) and preview_result.get('document_path'):
                preview_path = preview_result['document_path']
                PreviewStorage.copy_file(session_id, Path(preview_path))
                logger.info(f"Preview generated from cache: {preview_path}")
            else:
                raise ValueError(f"Preview generation failed: {preview_result}")
            doc_input = {'action': 'produce_document', 'research_result': research_result_data, 'output_format': 'docx', 'output_dir': str(output_dir), 'task_id': session_id}
            doc_result = await self._orchestrator._document_agent.execute(doc_input)
            doc_path = doc_result.get('document_path', '') if isinstance(doc_result, dict) else ''
            result = {'status': 'completed', 'report': research_result_data, 'document_path': preview_path}
            session['research_result'] = result
            session['mode'] = 'chat'
            session['current_step'] = 0
            complete_task(session_id)
            logger.info(f"Document generated from cache: {'no doc, using preview'}")
            return doc_path or ''
        except asyncio.CancelledError:
            logger.info(f"Cache doc generation cancelled: {session_id}")
            session['research_result'] = {'status': 'cancelled'}
            session['mode'] = 'chat'
        except Exception as e:
            logger.error(f"Cache-based doc generation failed: {e}", exc_info=True)
            session['research_result'] = {'status': 'completed', 'report': research_result_data, 'document_path': ''}
            session['mode'] = 'chat'
            fail_task(session_id, str(e))
            return

    def _convert_session_to_cache_format(self, session_rr):
        """Convert session['research_result'] to the format expected by _document_agent.

        session format: sections under 'report.sections'
        cache format:   sections at top-level 'sections'
        """
        converted = dict(session_rr)
        if "report" in converted and "sections" not in converted:
            report = converted.get("report", {})
            converted["sections"] = report.get("sections", [])
            converted["topic"] = converted.get("topic", report.get("topic", ""))
            converted["title"] = converted.get("topic", "")
            converted["aspects"] = converted.get("aspects", report.get("aspects", []))
            converted["sources"] = converted.get("sources", report.get("sources", []))
            converted["key_findings"] = converted.get("key_findings", report.get("key_findings", []))
        return converted

    async def _regenerate_report(self, session_id):
        """Regenerate HTML preview from cached research result, without re-running research.

        Loads research_result_cache.json (preferred) or converts session data,
        then calls _generate_documents_from_cache() to produce new HTML.
        """
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}

        research_result = session.get('research_result', {})
        if not research_result or research_result.get('status') not in ('completed', 'completed_with_warnings'):
            return {'error': 'No completed research to regenerate from',
                    'error_code': 'NO_COMPLETED_RESEARCH'}

        task_id = research_result.get('task_id', session_id)
        cache_path = Path('data') / task_id / 'research_result_cache.json'
        if not cache_path.exists():
            cache_path = Path('data') / session_id / 'research_result_cache.json'

        if cache_path.exists():
            try:
                research_result_data = json.loads(cache_path.read_text(encoding='utf-8'))
                logger.info(f"[{session_id}] Loaded research result from cache: {cache_path}")
            except Exception as e:
                logger.warning(f"[{session_id}] Failed to load cache: {e}, falling back to session data")
                research_result_data = self._convert_session_to_cache_format(research_result)
        else:
            logger.info(f"[{session_id}] No cache file found, converting session data")
            research_result_data = self._convert_session_to_cache_format(research_result)

        if not research_result_data.get('sections'):
            return {'error': 'No sections found in research result',
                    'error_code': 'NO_SECTIONS'}

        output_dir = Path('data') / session_id
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            await self._generate_documents_from_cache(
                session_id, research_result_data, output_dir, session
            )
        except Exception as e:
            logger.error(f"[{session_id}] Regenerate report failed: {e}", exc_info=True)
            return {'error': str(e), 'error_code': 'REGENERATE_FAILED'}

        try:
            from src.core.session_streamer import SessionStreamer
            from src.core.preview_storage import PreviewStorage
            preview_url = PreviewStorage.url(session_id)
            SessionStreamer.push_preview_refresh(session_id, preview_url, 'v1')
        except Exception:
            pass

        return {
            'session_id': session_id,
            'status': 'completed',
            'message': '文档已重新生成',
        }

    async def _save_cancel_snapshot(self, task_id, session):
        """Save a snapshot of current research state before cancel/pause for recovery.

        Persists completed sections and pending sections to a JSON file so that
        resume_from_snapshot can reconstruct the research state if the engine dies.
        """
        output_dir = Path('data') / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = output_dir / 'cancel_snapshot.json'
        research_result = session.get('research_result', {})
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        all_sections = list(framework.get('sections', []))
        completed_sections = []
        cache_path = output_dir / 'research_result_cache.json'
        if cache_path.exists():
            try:
                cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
                completed_sections = [s.get('title', s.get('id', '')) for s in cache_data.get('sections', [])]
            except Exception as e:
                logger.warning(f"Failed to read cache for snapshot: {e}")
        pending_sections = [s for s in all_sections if s not in completed_sections]
        snapshot = {
            'task_id': task_id,
            'timestamp': datetime.now().isoformat(),
            'status': session.get('status', 'unknown'),
            'mode': session.get('mode', 'unknown'),
            'current_step': session.get('current_step', 0),
            'all_sections': all_sections,
            'completed_sections': completed_sections,
            'pending_sections': pending_sections,
            'research_result_status': research_result.get('status') if isinstance(research_result, dict) else None,
            'final_plan': session.get('final_plan'),
            'research_context': context,
        }
        try:
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            logger.info(f"Cancel snapshot saved for {task_id}: {len(completed_sections)} completed, {len(pending_sections)} pending")
        except Exception as e:
            logger.error(f"Failed to save cancel snapshot for {task_id}: {e}")

    async def _load_cancel_snapshot(self, task_id):
        """Load a previously saved cancel snapshot. Returns None if not found."""
        snapshot_path = Path('data') / task_id / 'cancel_snapshot.json'
        if not snapshot_path.exists():
            return None
        try:
            data = json.loads(snapshot_path.read_text(encoding='utf-8'))
            logger.info(f"Cancel snapshot loaded for {task_id}: {len(data.get('completed_sections', []))} completed, {len(data.get('pending_sections', []))} pending")
            return data
        except Exception as e:
            logger.warning(f"Failed to load cancel snapshot for {task_id}: {e}")
            return None

    async def cancel_research(self, task_id):
        """Cancel research task — cascade cancel + save snapshot + update session + notify frontend."""
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        from src.core.progress_streamer import ProgressStreamer
        cm = get_cancel_manager()
        state_machine = session.get('state_machine')
        if state_machine and state_machine.can_transition_to(ConversationState.CANCELLED):
            state_machine.transition(ConversationState.CANCELLED)
        await self._save_cancel_snapshot(task_id, session)
        cm.cancel(task_id)
        exec_task = self._executor_tasks.get(task_id)
        if exec_task and not exec_task.done():
            exec_task.cancel()
            logger.info(f"Cancelled executor task for {task_id}")
        self._background_tasks.pop(task_id, None)
        session['status'] = 'cancelled'
        session['mode'] = 'chat'
        session['current_step'] = 0
        ProgressStreamer.cancel_task(task_id, 'Cancelled by user')
        try:
            from src.core.task_persistence import TaskPersistenceManager
            tp = TaskPersistenceManager()
            task = tp.load_task(task_id)
            if task:
                task.fail('Cancelled by user')
                tp.save_task(task)
        except Exception as e:
            logger.warning(f"Failed to persist cancel state: {e}")
        cm.cleanup(task_id)
        return {'task_id': task_id, 'status': 'cancelled', 'message': 'Research task cancelled'}

    def _on_sse_disconnect(self, task_id):
        """Called when SSE connection drops — schedule delayed pause with reconnect check."""
        session = session_manager.get(task_id)
        if not session:
            return
        research_result = session.get('research_result', {})
        _terminal = ('completed', 'failed', 'cancelled', 'error')
        if research_result.get('status') in _terminal:
            logger.info(f"SSE disconnected for {task_id}, research {research_result.get('status')} - not pausing")
            return
        logger.info(f"SSE disconnected for {task_id}, scheduling delayed pause")
        async def _delayed_pause():
            await asyncio.sleep(30)
            s2 = session_manager.get(task_id)
            if s2 and s2.get('research_result', {}).get('status') not in _terminal:
                from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
                get_cancel_manager().pause(task_id)
        task = safe_create_task(_delayed_pause(), name=f"delayed_pause_{task_id}")
        self._background_tasks[f"_sse_disconnect_{task_id}"] = task
        task.add_done_callback(lambda _: self._background_tasks.pop(f"_sse_disconnect_{task_id}", None))

    async def modify_requirements(self, task_id, new_aspects, new_topic=None):
        """
        Modify research requirements (add new requirements while paused)
        """
        session = session_manager.get(task_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        if new_topic:
            context['topic'] = new_topic
        existing_sections = framework.get('sections', [])
        merged_sections = list(dict.fromkeys(existing_sections + new_aspects))
        framework['sections'] = merged_sections
        context['framework'] = framework
        session['research_context'] = context
        try:
            from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
            topic = context.get('topic', '')
            adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
            routing_result = adapter.analyze_incremental(
                user_request=topic,
                requirement={'topic': topic, 'aspects': merged_sections, 'details': context.get('details', {})},
                completed_aspects=existing_sections,
                topic=topic)
            new_plan = routing_result.execution_plan.to_dict()
            new_plan['topic'] = topic
            new_plan['output_type'] = framework.get('output_type', 'industry_report')
            new_plan['skip_phases'] = routing_result.skip_phases
            session['final_plan'] = new_plan
        except Exception as e:
            logger.warning(f"Intelligent routing failed during modify: {e}")
            new_plan = session.get('final_plan', {})
            new_plan['aspects'] = merged_sections
            if not existing_sections:
                new_plan['skip_phases'] = []
            session['final_plan'] = new_plan
        return {'task_id': task_id, 'status': 'requirements_updated', 'message': f"Requirements updated, added sections: {new_aspects}", 'plan': {'topic': context.get('topic'), 'sections': merged_sections}}

    def _get_revision_lock(self, session_id):
        """Get or create a per-session revision lock (lazy init)."""
        if session_id not in self._revision_locks:
            self._revision_locks[session_id] = asyncio.Lock()
        return self._revision_locks[session_id]

    def _recursive_traverse_sections(self, sections, callback):
        """subsections"""
        for sec in sections:
            if isinstance(sec, dict):
                callback(sec)
                self._recursive_traverse_sections(sec.get('subsections', []), callback)

    async def _ask_user_via_sse(self, session_id, question):
        """通过 SSE 推送澄清问题，等待用户通过 /interact 回复"""
        from src.core.session_streamer import SessionStreamer
        clarification_id = str(uuid.uuid4())
        SessionStreamer.push_clarification(session_id, question, clarification_id)
        event = asyncio.Event()
        self._pending_clarifications[clarification_id] = event
        session = session_manager.get(session_id)
        if session:
            session['_pending_clarification_id'] = clarification_id
        try:
            await asyncio.wait_for(event.wait(), timeout=120)
            response = self._clarification_responses.pop(clarification_id, '')
            self._pending_clarifications.pop(clarification_id, None)
            if session:
                session.pop('_pending_clarification_id', None)
            return response
        except asyncio.TimeoutError:
            self._pending_clarifications.pop(clarification_id, None)
            if session:
                session.pop('_pending_clarification_id', None)
            return '__TIMEOUT__'
        except Exception:
            self._pending_clarifications.pop(clarification_id, None)
            if session:
                session.pop('_pending_clarification_id', None)

    def _apply_lightweight(self, session, action):
        """research_result"""
        research = session.setdefault('research_result', {})
        op_type = action.action_type.value
        session['_report_version'] = (session.get('_report_version', 0) + 1)
        if op_type == 'update_title':
            new_title = (action.content or '').strip()
            if new_title:
                research['topic'] = new_title
                if isinstance(research.get('report'), dict):
                    research['report']['topic'] = new_title
            return
        if op_type == 'replace_text':
            old_text = action.parameters.get('old_text', '')
            new_text = (action.content or '').strip()
            if old_text:
                sections = research.get('report', {}).get('sections', [])
                def _replace(sec):
                    for k in list(sec.keys()):
                        if isinstance(sec[k], str) and old_text in sec[k]:
                            sec[k] = sec[k].replace(old_text, new_text)
                self._recursive_traverse_sections(sections, _replace)
            return
        if op_type == 'change_case':
            style = action.parameters.get('case_style', 'upper')
            sections = research.get('report', {}).get('sections', [])
            def _case(sec):
                for k in list(sec.keys()):
                    if isinstance(sec[k], str):
                        if style == 'upper':
                            sec[k] = sec[k].upper()
                        elif style == 'lower':
                            sec[k] = sec[k].lower()
                        elif style == 'title':
                            sec[k] = sec[k].title()
            self._recursive_traverse_sections(sections, _case)
            return
        if op_type == 'fix_punctuation':
            rule = action.parameters.get('punct_rule', 'cn2en')
            punct_map = {'cn2en': {'，': ',', '。': '.', '；': ';', '：': ':', '“': '"', '”': '"', '！': '!', '？': '?'}, 'en2cn': {',': '，', '.': '。', ';': '；', ':': '：', '"': '“', '!': '！', '?': '？'}}
            mapping = punct_map.get(rule, {})
            if mapping:
                sections = research.get('report', {}).get('sections', [])
                def _punct(sec):
                    for k in list(sec.keys()):
                        if isinstance(sec[k], str):
                            for oc, nc in mapping.items():
                                sec[k] = sec[k].replace(oc, nc)
                self._recursive_traverse_sections(sections, _punct)
            return
        return

    def _lightweight_message(self, action):
        """update_title"""
        op_type = action.action_type.value
        if op_type == 'update_title':
            return f"""标题已修改为「{action.content}」"""
        if op_type == 'replace_text':
            old = action.parameters.get('old_text', '')
            new = (action.content or '').strip()
            return f"""已将「{old}」替换为「{new}」"""
        if op_type == 'change_case':
            style = action.parameters.get('case_style', 'upper')
            names = {'upper': '大写', 'lower': '小写', 'title': '首字母大写'}
            return f"""已改为{names.get(style, style)}"""
        if op_type == 'fix_punctuation':
            rule = action.parameters.get('punct_rule', 'cn2en')
            names = {'cn2en': '中文标点→英文标点', 'en2cn': '英文标点→中文标点'}
            return f"""标点已转换：{names.get(rule, rule)}"""
        return '修订已应用。'

    def _sync_lightweight_to_preview(self, session_id, session, action):
        """update_title"""
        from src.core.preview_storage import PreviewStorage
        preview_path = PreviewStorage.path(session_id)
        if not preview_path.exists():
            return
        html = preview_path.read_text(encoding='utf-8')
        original_html = html
        op_type = action.action_type.value
        if op_type == 'update_title':
            new_title = (action.content or '').strip()
            if new_title:
                html = re.sub(r'(<h1[^>]*>).*?(</h1>)', lambda m: m.group(1) + new_title + m.group(2), html)
                html = re.sub(r'(<title[^>]*>).*?(</title>)', lambda m: m.group(1) + new_title + m.group(2), html)
        if op_type == 'replace_text':
            old_text = action.parameters.get('old_text', '')
            new_text = (action.content or '').strip()
            if old_text:
                html = html.replace(old_text, new_text)
        if op_type == 'change_case':
            style = action.parameters.get('case_style', 'upper')
            try:
                from bs4 import BeautifulSoup, Comment
                doctype = ''
                m = re.match(r'\s*<!DOCTYPE[^>]*>', html, re.IGNORECASE)
                if m:
                    doctype = m.group(0)
                    html = html[m.end():]
                soup = BeautifulSoup(html, 'html.parser')
                for text_node in soup.find_all(string=True):
                    if not isinstance(text_node, Comment):
                        parent = text_node.parent
                        if parent and parent.name not in ('script', 'style', 'code', 'pre'):
                            if style == 'upper':
                                text_node.replace_with(text_node.upper())
                            elif style == 'lower':
                                text_node.replace_with(text_node.lower())
                            elif style == 'title':
                                text_node.replace_with(text_node.title())
                html = str(soup)
                if doctype:
                    html = doctype + '\n' + html
            except ImportError:
                pass
        if op_type == 'fix_punctuation':
            rule = action.parameters.get('punct_rule', 'cn2en')
            punct_map = {'cn2en': {'，': ',', '。': '.', '；': ';', '：': ':', '“': '"', '”': '"', '！': '!', '？': '?'}, 'en2cn': {',': '，', '.': '。', ';': '；', ':': '：', '"': '“', '!': '！', '?': '？'}}
            mapping = punct_map.get(rule, {})
            for old_ch, new_ch in mapping.items():
                html = html.replace(old_ch, new_ch)
        if html != original_html:
            PreviewStorage.write(session_id, html)
        return

    async def _handle_v2_revision(self, session_id, conv_result):
        """v2 修订入口：LLM 返回 revise_report 时调用"""
        MAX_TOTAL_REVISIONS = 10
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        
        adjustment = conv_result.get('adjustment') or conv_result.get('user_input', '')
        
        quality_lock = self._get_quality_lock(session_id)
        async with quality_lock:
            quality_state_data = session.get("quality_state", {})
            if quality_state_data:
                import copy
                quality_state_data = copy.deepcopy(quality_state_data)
                if quality_state_data.get("phase") in ("reviewing", "revising"):
                    quality_state_data["phase"] = "revising"
                session["quality_state"] = quality_state_data
                
                version_id = f"v{int(time.time())}"
                html_path = str(PreviewStorage.path(session_id))
                md_path = str(Path('data') / session_id / 'report.md')
                report_content = session.get("research_result", {}).get("report", {})
                if not report_content:
                    quality_state_data["phase"] = "reviewing"
                    session["quality_state"] = quality_state_data
                    return self._chat_response(session_id)
                
                version_n = len(quality_state_data.get("version_stack", []))
                snapshot_copy = copy.deepcopy({k: v for k, v in quality_state_data.items() if k != "version_stack"})
                quality_state_data.setdefault("version_stack", []).append({
                    "id": version_id,
                    "created_at": datetime.now().isoformat(),
                    "html_path": f"data/snapshots/{session_id}/{version_id}.html",
                    "md_path": f"data/snapshots/{session_id}/{version_id}.md",
                    "quality_state_snapshot": snapshot_copy,
                    "overall_score": quality_state_data.get("overall_score", 0),
                    "label": f"修订前快照 v{version_n}",
                })
                
                session['quality_state_snapshot'] = quality_state_data
                session["quality_state"] = quality_state_data
            
            MAX_ISSUE_REVISIONS = 3
            modified_sections = []
            aspects = conv_result.get("aspects", [])
            if aspects:
                modified_sections = aspects
            else:
                flow_pending = session.get("_pending_v2_revision")
                if flow_pending:
                    for task in getattr(flow_pending.get("flow", {}), 'tasks', []):
                        if getattr(task, 'section_name', None):
                            modified_sections.append(task.section_name)
            
            if not modified_sections:
                pending_input = session.get("_pending_revision_input")
                if pending_input and isinstance(pending_input, dict):
                    sn = pending_input.get("sectionName")
                    if sn:
                        modified_sections.append(sn)
            
            for sec_name, sec_data in quality_state_data.get("section_scores", {}).items():
                for issue in sec_data.get("issues", []):
                    if issue.get("state") == "open" and (not modified_sections or issue.get("section") in modified_sections):
                        if issue.get("revision_count", 0) >= MAX_ISSUE_REVISIONS:
                            issue["state"] = "max_retries_reached"
                        else:
                            issue["state"] = "revising"
                            issue["revision_count"] = issue.get("revision_count", 0) + 1
                            issue["revising_since"] = time.time()
            session["quality_state"] = quality_state_data
        
        current_task = asyncio.current_task()
        old_task = self._revision_task
        self._revision_task = current_task
        if old_task and not old_task.done():
            old_task.cancel()
        from src.core.adjustment.report_adapter import SessionReportAdapter
        from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
        from src.core.adjustment.revision_types import ExecutionStatus, TaskStatus
        adapter = SessionReportAdapter(session)
        if not hasattr(self, '_v2_lock_manager'):
            from src.core.adjustment.report_lock_manager import ReportLockManager
            self._v2_lock_manager = ReportLockManager()
        notifier = ProgressNotifier()
        executor = RevisionExecutor(lock_manager=self._v2_lock_manager, notifier=notifier)
        revision_task = safe_create_task(executor.handle_feedback(adjustment, adapter), name=f"rev_{session_id}")
        self._executor_tasks[f"""rev_{session_id}"""] = revision_task
        revision_task.add_done_callback(lambda _: self._executor_tasks.pop(f"rev_{session_id}", None))
        try:
            flow = await asyncio.shield(revision_task)
        except asyncio.CancelledError:
            logger.info(f"""[BP3-FIX] SSE cancelled, revision continues in background for {session_id}""")
            session['_pending_revision_task'] = revision_task
            return {'session_id': session_id, 'status': 'executing', 'message': '修订正在后台继续执行...'}
        except Exception as rev_err:
            logger.warning(f"Revision execution failed: {rev_err}")
            self._rollback_revising_issues(session)
            return self._chat_response(session_id, f"修订执行失败: {rev_err}")
        if flow.status == ExecutionStatus.LIGHTWEIGHT_DONE:
            if flow.tasks:
                action = flow.tasks[0].action
                self._apply_lightweight(session, action)
                self._sync_lightweight_to_preview(session_id, session, action)
            if quality_state_data:
                await self._post_revision_recheck(session)
            return self._chat_response(session_id)
        if flow.current_index < len(flow.tasks):
            has_pending = (flow.tasks[flow.current_index].status == TaskStatus.CONFIRMING)
            pending_data = {'flow': flow, 'adapter': adapter, 'snapshot_id': flow.snapshot_id}
            session['_pending_v2_revision'] = pending_data
            if has_pending:
                task = flow.tasks[flow.current_index]
            return self._chat_response(session_id)
        if flow.status == ExecutionStatus.PREVIEW_READY:
            msg = '以下是对报告的修改预览：\n\n'
            if flow.preview and flow.preview.commit_message:
                msg += flow.preview.commit_message + '\n\n'
            msg += '请确认修改(y)或拒绝(n)'
            return self._chat_response(session_id, msg)
        if flow.status == ExecutionStatus.ABORTED:
            self._rollback_revising_issues(session)
            if quality_state_data:
                await self._post_revision_recheck(session)
            return self._chat_response(session_id)
        if flow.status == ExecutionStatus.CLARIFICATION_FAILED:
            self._rollback_revising_issues(session)
            user_msg = '未能理解您的修订意图。请重新描述要修改的内容，例如："修改第三节的市场规模数据"。'
            if flow.error:
                user_msg += f"""\n({flow.error})"""
            return self._chat_response(session_id, user_msg)
        if flow.status == ExecutionStatus.ROLLED_BACK:
            self._rollback_revising_issues(session)
            if quality_state_data:
                await self._post_revision_recheck(session)
            return self._chat_response(session_id)
        if flow.status == ExecutionStatus.FULL_RESEARCH_NEEDED:
            self._rollback_revising_issues(session)
            routing_result = getattr(flow, '_routing_result', None)
            if routing_result:
                session['mode'] = 'research'
                session['_routing_result'] = routing_result
                return await self._start_execution_with_routing(session_id, routing_result)
            return self._chat_response(session_id)
        if flow.error:
            err_detail = flow.error or '未知错误'
            return self._chat_response(session_id)
        return self._chat_response(session_id)

    async def _confirm_v2_revision(self, session_id, accept):
        """用户确认/拒绝 v2 修订结果"""
        session = session_manager.get(session_id)
        if not session:
            return self._chat_response(session_id)
        quality_lock = self._get_quality_lock(session_id)
        async with quality_lock:
            pending = session.pop('_pending_v2_revision', None)
            if not pending:
                return self._chat_response(session_id)
            flow = pending['flow']
            adapter = pending['adapter']
            snapshot_id = flow.snapshot_id
            from src.core.adjustment.snapshot_manager import SnapshotManager
            sm = SnapshotManager.get_instance()
            checkpoint_ids = []
            for t in flow.tasks:
                if hasattr(t, 'checkpoint_id') and t.checkpoint_id:
                    checkpoint_ids.append(t.checkpoint_id)
            all_snapshot_ids = [snapshot_id] + checkpoint_ids
            try:
                if accept:
                    from src.core.adjustment.version_manager import VersionManager
                    if flow.preview:
                        await VersionManager.get_instance().commit_revision(
                            report=adapter.to_dict(), plan=flow.plan,
                            snapshot_id=snapshot_id,
                            message=flow.preview.commit_message or '')
                    pp = Path('data') / session_id
                    await self._generate_documents_from_cache(session_id, session.get('research_result', {}), pp, session)
                    await sm.delete_snapshots(all_snapshot_ids)
                else:
                    restored = await sm.restore_snapshot(snapshot_id)
                    if restored and isinstance(restored, dict):
                        adapter.restore_from_dict(restored)
                    self._rollback_revising_issues(session)
                    await sm.delete_snapshots(all_snapshot_ids)
                    from src.core.session_streamer import SessionStreamer
                    SessionStreamer.push_quality_result(session_id, session.get("quality_state", {}))
            except Exception as e:
                logger.warning(f"Revision confirm failed: {e}")
                await sm.delete_snapshots(all_snapshot_ids)
                return self._chat_response(session_id)
        if accept and session.get("quality_state"):
            await self._post_revision_recheck(session)
        return self._chat_response(session_id)

    async def _handle_task_confirmation(self, session_id, flow, pending, user_input):
        """处理用户在修订任务确认中的选择"""
        session = session_manager.get(session_id)
        if not session:
            return self._chat_response(session_id)
        from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier, parse_choice_extended
        from src.core.adjustment.structural_analyzer import StructuralAnalyzer
        from src.core.adjustment.revision_types import ExecutionStatus
        choice = parse_choice_extended(user_input)
        adapter = pending['adapter']
        notifier = ProgressNotifier()
        executor = RevisionExecutor(lock_manager=self._v2_lock_manager, notifier=notifier)
        analyzer = StructuralAnalyzer()
        analyzer.begin_session(adapter)
        report_tree = analyzer.analyze_tree(adapter)
        analyzer.end_session()
        flow = await executor.continue_revision(flow, choice, user_input, adapter, report_tree)
        pending['flow'] = flow
        if flow.status == ExecutionStatus.PREVIEW_READY:
            msg = '以下是对报告的最终修改预览：\n\n'
            if flow.preview and flow.preview.commit_message:
                msg += flow.preview.commit_message + '\n\n'
            msg += '请确认提交(y)或拒绝(n)'
            return self._chat_response(session_id, msg)
        if flow.status == ExecutionStatus.ABORTED:
            session.pop('_pending_v2_revision', None)
            return self._chat_response(session_id)
        task = flow.tasks[flow.current_index]
        return self._chat_response(session_id)

    async def _handle_inject_requirement(self, session_id, inject_ops, user_message):
        """Session not found"""
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        current_sections = list(framework.get('sections', []))
        if not current_sections:
            return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': '当前没有研究框架，无法处理此操作。', 'suggestions': [], 'next_step': 'continue_research'}
        add_sections = []
        for op in (inject_ops or []):
            if op.get('op') == 'add_section':
                sn = op.get('section_name', '')
                if sn:
                    add_sections.append(sn)
        if add_sections:
            return await self._handle_modify_research(session_id=session_id, modifications={'add_aspects': add_sections}, adjustment=user_message)
        results = []
        for op in (inject_ops or []):
            op_type = op.get('op', '')
            if op_type == 'add_section':
                r = self._inject_add_section(session, op)
            elif op_type == 'cancel_section':
                r = self._inject_cancel_section(session, op)
            elif op_type == 'merge_to_section':
                r = self._inject_merge_to_section(session, op)
            else:
                r = {'status': 'error', 'summary': f"""unknown op: {op_type}"""}
            results.append(r)
        ok = any(r.get('status') == 'ok' for r in results)
        summary = 'Changes applied.' if ok else 'No changes applied.'
        return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': f"""已处理：{summary}。研究继续执行中。""", 'suggestions': [], 'next_step': 'continue_research'}

    def _inject_add_section(self, session, op):
        """section_name"""
        section_name = op.get('section_name', '').strip()
        if not section_name:
            return {'status': 'error', 'summary': 'empty section name'}
        context = session.setdefault('research_context', {})
        framework = context.setdefault('framework', {})
        sections = list(framework.get('sections', []))
        if section_name in sections:
            return {'status': 'skipped', 'summary': f"""'{section_name}' already exists"""}
        sections.append(section_name)
        framework['sections'] = sections
        pending = session.setdefault('_pending_section_injects', [])
        pending.append({'op': 'add_section', 'section_name': section_name})
        return {'status': 'ok', 'summary': f"""added '{section_name}'"""} 

    def _inject_cancel_section(self, session, op):
        """section_name"""
        section_name = op.get('section_name', '').strip()
        if not section_name:
            return {'status': 'error', 'summary': 'empty section name'}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        sections = list(framework.get('sections', []))
        if section_name not in sections:
            return {'status': 'skipped', 'summary': f"""'{section_name}' not in framework"""}
        sections.remove(section_name)
        framework['sections'] = sections
        pending = session.setdefault('_pending_section_injects', [])
        pending.append({'op': 'cancel_section', 'section_name': section_name})
        return {'status': 'ok', 'summary': f"""cancelled '{section_name}'"""} 

    @staticmethod
    def _get_section_status(session_id, section_name):
        """research_result_cache.json"""
        cache_path = Path('data') / session_id / 'research_result_cache.json'
        if not cache_path.exists():
            return 'pending'
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
            for s in data.get('sections', []):
                if s.get('title') == section_name or s.get('id') == section_name:
                    return 'completed'
            return 'pending'
        except Exception:
            return 'pending'

    def _inject_merge_to_section(self, session, op):
        """section_name"""
        section_name = op.get('section_name', '').strip()
        requirement = op.get('requirement', '').strip()
        if not section_name or not requirement:
            return {'status': 'error', 'summary': 'missing section name or requirement'}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        if not framework:
            return {'status': 'error', 'summary': 'no framework defined'}
        sections = framework.get('sections', [])
        if section_name not in sections:
            return {'status': 'error', 'summary': f"""'{section_name}' not in framework"""}
        section_reqs = session.setdefault('section_requirements', {})
        section_reqs.setdefault(section_name, [])
        if requirement not in section_reqs[section_name]:
            section_reqs[section_name].append(requirement)
        sid = session.get('_session_id', '')
        status = self._get_section_status(sid, section_name)
        op_type = 'revise'
        pending = session.setdefault('_pending_section_injects', [])
        pending.append({'op': op_type, 'section_name': section_name, 'requirement': requirement})
        return {'status': 'ok', 'summary': f"""merged into '{section_name}' ({op_type})"""} 

    async def _handle_modify_research(self, session_id, modifications, adjustment):
        """
        
        Handle mid-research requirement changes from the user.
        
        Flow: pause → save completed data → re-analyze → resume with skip_phases
        
        """
        add_aspects = modifications.get('add_aspects', [])
        remove_aspects = modifications.get('remove_aspects', [])
        modify_aspects = modifications.get('modify_aspects', {})
        session = session_manager.get(session_id)
        if not session:
            return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
        context = session.get('research_context', {})
        framework = context.get('framework', {})
        current_sections = list(framework.get('sections', []))
        if not framework.get('sections'):
            logger.warning(f"modify_research with no framework sections for {session_id}, switching to framework mode")
            await self._save_cancel_snapshot(session_id, session)
            self._cancel_existing_task(session_id)
            session['mode'] = 'chat'
            return self._enter_framework_mode(session_id, adjustment)
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        get_cancel_manager().pause(session_id)
        await self._save_cancel_snapshot(session_id, session)
        self._cancel_existing_task(session_id)
        output_dir = Path('data') / session_id
        cache_path = output_dir / 'research_result_cache.json'
        completed_aspects = []
        if cache_path.exists():
            cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
            completed_aspects = [s.get('title', s.get('id', '')) for s in cache_data.get('sections', [])]
        for a in add_aspects:
            if a not in current_sections:
                current_sections.append(a)
        for r in remove_aspects:
            if r in current_sections:
                current_sections.remove(r)
        for old_name, new_name in modify_aspects.items():
            if old_name in current_sections:
                idx = current_sections.index(old_name)
                current_sections[idx] = new_name
        framework['sections'] = current_sections
        context['framework'] = framework
        session['research_context'] = context
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
        topic = context.get('topic', '')
        existing_intent = self._get_cached_intent_result(session)
        routing_result = adapter.analyze_incremental(
            user_request=adjustment,
            requirement={'topic': topic, 'aspects': current_sections},
            completed_aspects=completed_aspects or current_sections,
            topic=topic,
            existing_intent_result=existing_intent,
        )
        new_plan = {}
        if hasattr(routing_result, 'execution_plan'):
            plan = routing_result.execution_plan
            if hasattr(plan, 'to_dict'):
                new_plan = plan.to_dict()
        if not new_plan:
            new_plan = {'phases': [], 'total_agents': 0}
        new_plan['topic'] = topic
        new_plan['output_type'] = framework.get('output_type', 'industry_report')
        new_plan['skip_phases'] = getattr(routing_result, 'skip_phases', [])
        session['final_plan'] = new_plan
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_agent_message(session_id, {'agent_id': 'modify', 'agent_name': 'Plan Modification', 'action': 'completed', 'content': f"""Plan updated. Added: {add_aspects}, Removed: {remove_aspects}. Resuming..."""})
        task = safe_create_task(self._resume_after_modify(session_id, new_plan), name=f"modify_{session_id}")
        self._executor_tasks[session_id] = task
        task.add_done_callback(lambda t: self._executor_tasks.pop(session_id, None))
        def _log_resume_error(t):
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.error(f"_resume_after_modify failed: {exc}")
        task.add_done_callback(_log_resume_error)
        return {'session_id': session_id, 'step': 6, 'mode': 'research', 'status': 'processing', 'message': f"""Research plan updated. Added: {add_aspects}, Removed: {remove_aspects}. Continuing...""", 'next_step': 'resume_execution'}


    async def _resume_after_modify(self, session_id, new_plan):
        """Resume research execution after mid-flow requirement change."""
        from src.api.research_executor import get_executor
        session = session_manager.get(session_id)
        if not session:
            return
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        get_cancel_manager().resume(session_id)
        session['mode'] = 'research'
        executor = get_executor()
        await executor.execute(session_id, new_plan, session_manager)
        return

    def _rollback_revising_issues(self, session):
        """Roll back all revising issues to open state after revision failure"""
        import copy
        quality_data = copy.deepcopy(session.get("quality_state", {}))
        if not quality_data:
            return
        changed = False
        for sec_name, sec_data in quality_data.get("section_scores", {}).items():
            for issue in sec_data.get("issues", []):
                if issue.get("state") == "revising":
                    issue["state"] = "open"
                    issue["revision_count"] = max(0, issue.get("revision_count", 0) - 1)
                    changed = True
        if changed:
            quality_data["phase"] = "reviewing"
            session["quality_state"] = quality_data
            session_id = session.get("_session_id", "")
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_quality_result(session_id, quality_data)

    async def _post_revision_recheck(self, session):
        """修订完成后重新质检，合并新旧issue状态"""
        from src.core.quality.quality_state import merge_issues_on_recheck, QualityIssue, SectionScore
        from src.core.session_streamer import SessionStreamer

        session_id = session.get("_session_id", "")
        quality_data = session.get("quality_state", {})
        if not quality_data:
            return

        sections = session.get("research_result", {}).get("report", {}).get("sections", [])
        if not sections:
            return

        try:
            recheck_result = await self._recheck_quality(session, sections, push_preview=False)
            if not recheck_result:
                return

            existing_sections = {}
            for sec_name, sec_data in quality_data.get("section_scores", {}).items():
                issues = []
                for raw_issue in sec_data.get("issues", []):
                    if isinstance(raw_issue, QualityIssue):
                        issues.append(raw_issue)
                    elif isinstance(raw_issue, dict):
                        try:
                            issues.append(QualityIssue(
                                id=raw_issue.get("id", ""),
                                type=raw_issue.get("type", "completeness"),
                                severity=raw_issue.get("severity", "medium"),
                                message=raw_issue.get("message", ""),
                                section=raw_issue.get("section", sec_name),
                                state=raw_issue.get("state", "open"),
                                revision_count=raw_issue.get("revision_count", 0),
                            ))
                        except Exception:
                            continue
                existing_sections[sec_name] = SectionScore(
                    score=sec_data.get("score", 0.0),
                    status=sec_data.get("status", "warning"),
                    issues=issues,
                )

            new_section_results = recheck_result.get("section_results", {})
            merged = merge_issues_on_recheck(existing_sections, new_section_results)

            merged_dict = {}
            for sec_name, sec_score in merged.items():
                merged_dict[sec_name] = {
                    "score": sec_score.score,
                    "status": sec_score.status,
                    "issues": [iss.model_dump() for iss in sec_score.issues],
                }

            quality_data["section_scores"] = merged_dict
            quality_data["overall_score"] = recheck_result.get("overall_score", quality_data.get("overall_score", 0))
            quality_data["overall_status"] = recheck_result.get("overall_status", quality_data.get("overall_status", "warning"))
            quality_data["phase"] = "reviewing"
            session["quality_state"] = quality_data

            SessionStreamer.push_quality_result(session_id, quality_data)
        except Exception as e:
            logger.warning(f"Post-revision recheck failed: {e}")

    async def _recheck_quality(self, session, sections, push_preview=False):
        """对指定sections重新执行质检，返回质检结果dict"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        from src.core.session_streamer import SessionStreamer

        session_id = session.get("_session_id", "")
        try:
            if not hasattr(self, '_quality_checker') or self._quality_checker is None:
                self._quality_checker = QualityCheckAgent()
            checker = self._quality_checker
            check_input = {
                "session_id": session_id,
                "sections": sections,
                "report": session.get("research_result", {}).get("report", {}),
            }
            result = await checker.execute(check_input)
            if not result.get("success"):
                logger.warning(f"Recheck quality failed: {result.get('error', 'unknown')}")
                return None

            if push_preview:
                SessionStreamer.push_quality_result(session_id, result)

            return result
        except Exception as e:
            logger.warning(f"Recheck quality exception: {e}")
            return None

    def _expire_stale_revising_issues(self, session):
        """将长时间处于revising状态的issue标记为max_retries_reached"""
        import time
        quality_data = session.get("quality_state", {})
        if not quality_data:
            return

        changed = False
        now = time.time()
        stale_threshold = 600

        for sec_name, sec_data in quality_data.get("section_scores", {}).items():
            for issue in sec_data.get("issues", []):
                if issue.get("state") == "revising":
                    revising_since = issue.get("revising_since", 0)
                    if revising_since and (now - revising_since > stale_threshold):
                        issue["state"] = "max_retries_reached"
                        changed = True
                    elif not revising_since:
                        issue["state"] = "open"
                        changed = True

        if changed:
            session["quality_state"] = quality_data

    def _get_quality_lock(self, session_id: str):
        """Get or create quality-specific lock for thread-safe operations"""
        key = f"_quality_{session_id}"
        if key not in self._session_locks:
            self._session_locks[key] = asyncio.Lock()
        return self._session_locks[key]

    async def handle_quality_action(self, request) -> dict:
        """Handle quality review action"""
        session_id = getattr(request, 'session_id', None)
        action = getattr(request, 'action', None)
        if not session_id:
            return {"error": "Missing session_id", "error_code": "MISSING_SESSION_ID"}
        
        lock = self._get_quality_lock(session_id)
        
        async with lock:
            session = session_manager.get(session_id)
            if not session:
                return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
        
            self._expire_stale_revising_issues(session)
        
            quality_lock = self._get_quality_lock(session_id)
            async with quality_lock:
                quality_data = session.get("quality_state", {})
                if not quality_data:
                    return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
                
                sections = session.get("research_result", {}).get("report", {}).get("sections", [])
                if not sections:
                    return {"error": "No sections in report", "error_code": "NO_SECTIONS"}
                
                await self._recheck_quality(session, sections, push_preview=True)
                
                quality_data = session.get("quality_state", {})
                quality_data["phase"] = "reviewing"
                session["quality_state"] = quality_data
                
                from src.core.session_streamer import SessionStreamer
                SessionStreamer.push_quality_result(session_id, quality_data)
                
                from src.core.quality.preview_health import check_preview_health
                html_path = str(PreviewStorage.path(session_id))
                old_html_length = 0
                if quality_data.get("version_stack"):
                    last_version = quality_data["version_stack"][-1]
                    old_snap_html = Path(last_version.get("html_path", ""))
                    if old_snap_html.exists():
                        old_html_length = len(old_snap_html.read_text(encoding="utf-8"))
                
                health = check_preview_health(html_path, old_html_length)
                if not health["healthy"]:
                    from src.core.session_streamer import SessionStreamer
                    SessionStreamer.push_agent_message(session_id, {
                        "agent_id": "system",
                        "agent_name": "系统",
                        "action": "warning",
                        "content": f"修订完成但预览可能存在排版问题: {', '.join(i['message'] for i in health['issues'])}。可在质量面板中使用版本回滚恢复。",
                    })



# Create default instance
research_api = ResearchAPI()

__all__ = ["ResearchAPI", "research_api"]


class QualityActionRequest:
    """Request model for quality review actions"""
    def __init__(self, **kwargs):
        self.session_id = kwargs.get('session_id')
        self.action = kwargs.get('action')
        self.data = kwargs.get('data', {})
        self.issue_id = kwargs.get('issue_id')
        self.version_id = kwargs.get('version_id')
        self.section_name = kwargs.get('section_name')