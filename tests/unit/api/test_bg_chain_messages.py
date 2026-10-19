# -*- coding: utf-8 -*-
"""E2/E3: 后台工具链的消息去重 + 引擎化 follow-up 契约。

- E3: follow-up LLM 调用必须走 `_llm_call_with_engine_retry`（call_llm_ex），
  不再用裸 `call_llm`（无引擎重试/变异）。
- E2: iteration-0 的 message 已随 'processing' 响应展示；后台链没有产生新的
  成功迭代、或最终 message 与之一致时，推送中性收尾语而不是重复同一文本。
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.research_api import ResearchAPI, _resolve_bg_final_message

# ``from src.api import research_api`` binds the singleton INSTANCE (the
# package __init__ shadows the submodule); import the real module for seams.
import importlib
research_api = importlib.import_module("src.api.research_api")

CLOSURE = research_api.BG_CHAIN_CLOSURE_ZH
FOREGROUND_MSG = "正在为您检索相关行业信息…"
FOREGROUND_PARSED = {
    "message": FOREGROUND_MSG,
    "action": "continue_chat",
    "topic": "新能源汽车",
    "directions": ["市场规模"],
    "suggestions": [],
}

CANCEL_MGR = "src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager"


def _make_api():
    """ResearchAPI via __new__ (skip heavy __init__ deps) + bg-chain attrs."""
    api = ResearchAPI.__new__(ResearchAPI)
    api._background_task_gen = {"s1": 0}
    api._tool_set = MagicMock()
    api._tool_set.execute_tool = AsyncMock(return_value={"success": True, "results": []})
    return api


def _run_bg_chain(api, call_llm_ex_return):
    """Drive _continue_tool_chain with seams patched; return pushed response."""
    pushed = []
    mock_cm = MagicMock()
    mock_cm.is_cancelled.return_value = False
    mock_cm.is_paused.return_value = False

    with patch("src.api.research_api.session_manager") as sm, \
         patch("src.api.research_api.call_llm_ex", AsyncMock(return_value=call_llm_ex_return)), \
         patch(CANCEL_MGR, return_value=mock_cm), \
         patch("src.core.progress_streamer.ProgressStreamer.push_chat_response",
               side_effect=lambda sid, data: pushed.append(data)), \
         patch("src.core.session_streamer.SessionStreamer.push_agent_message"):
        sm.get.return_value = None
        asyncio.run(api._continue_tool_chain(
            "s1", "最新新能源销量如何", "system prompt", {},
            "accumulated context", [], dict(FOREGROUND_PARSED),
            None, 0, 0))
    return pushed


class TestResolveBgFinalMessage:
    def test_no_new_iteration_yields_closure(self):
        result = _resolve_bg_final_message(FOREGROUND_MSG, FOREGROUND_PARSED, False)
        assert result == CLOSURE

    def test_duplicate_message_yields_closure(self):
        result = _resolve_bg_final_message(FOREGROUND_MSG, FOREGROUND_PARSED, True)
        assert result == CLOSURE

    def test_new_message_kept(self):
        new_parsed = dict(FOREGROUND_PARSED, message="2025年全球新能源销量约为…")
        result = _resolve_bg_final_message(FOREGROUND_MSG, new_parsed, True)
        assert result == "2025年全球新能源销量约为…"

    def test_duplicate_detection_ignores_whitespace(self):
        new_parsed = dict(FOREGROUND_PARSED, message="  " + FOREGROUND_MSG + "\n")
        result = _resolve_bg_final_message(FOREGROUND_MSG, new_parsed, True)
        assert result == CLOSURE

    def test_empty_parsed_no_new_iteration_yields_closure(self):
        result = _resolve_bg_final_message(FOREGROUND_MSG, None, False)
        assert result == CLOSURE

    def test_bilingual_closure(self):
        assert _resolve_bg_final_message("m", {}, False, lang="en") == \
            research_api.BG_CHAIN_CLOSURE_EN
        assert _resolve_bg_final_message("m", {}, False, lang="zh") == \
            research_api.BG_CHAIN_CLOSURE_ZH


class TestBgChainEngineCallAndMessages:
    def test_follow_up_uses_engine_helper_not_call_llm(self):
        """E3: 后台 follow-up 经 _llm_call_with_engine_retry（引擎），不再直呼
        call_llm（无重试/变异）。"""
        api = _make_api()
        mock_cm = MagicMock()
        mock_cm.is_cancelled.return_value = False
        mock_cm.is_paused.return_value = False
        pushed = []
        with patch("src.api.research_api.session_manager") as sm, \
             patch("src.api.research_api._llm_call_with_engine_retry",
                   AsyncMock(return_value=None)) as mock_helper, \
             patch("src.api.research_api.call_llm", AsyncMock()) as mock_legacy, \
             patch(CANCEL_MGR, return_value=mock_cm), \
             patch("src.core.progress_streamer.ProgressStreamer.push_chat_response",
                   side_effect=lambda sid, data: pushed.append(data)), \
             patch("src.core.session_streamer.SessionStreamer.push_agent_message"):
            sm.get.return_value = None
            asyncio.run(api._continue_tool_chain(
                "s1", "最新新能源销量如何", "system prompt", {},
                "accumulated context", [], dict(FOREGROUND_PARSED),
                None, 0, 0))
        mock_helper.assert_awaited_once()
        helper_kwargs = mock_helper.await_args.kwargs
        assert helper_kwargs["output_contract"] == "json"
        assert helper_kwargs["task_tag"] == "research_api_bg"
        assert helper_kwargs["expected_output_chars"] == 1500
        mock_legacy.assert_not_awaited()

    def test_engine_exhaustion_pushes_closure_not_foreground(self):
        """E2: follow-up 失败（预算耗尽返回 None）→ 推收尾语，不重复前台文本。"""
        api = _make_api()
        pushed = _run_bg_chain(api, None)
        assert len(pushed) == 1
        assert pushed[0]["message"] == CLOSURE
        assert pushed[0]["message"] != FOREGROUND_MSG
        # parsed 的其余字段保留
        assert pushed[0]["action"] == "continue_chat"
        assert pushed[0]["topic"] == "新能源汽车"

    def test_different_final_message_kept(self):
        api = _make_api()
        final_json = json.dumps(
            dict(FOREGROUND_PARSED, message="根据检索结果，2025年销量为…"),
            ensure_ascii=False)
        pushed = _run_bg_chain(api, final_json)
        assert len(pushed) == 1
        assert pushed[0]["message"] == "根据检索结果，2025年销量为…"

    def test_same_final_message_substituted_with_closure(self):
        api = _make_api()
        final_json = json.dumps(FOREGROUND_PARSED, ensure_ascii=False)
        pushed = _run_bg_chain(api, final_json)
        assert len(pushed) == 1
        assert pushed[0]["message"] == CLOSURE
        assert pushed[0]["message"] != FOREGROUND_MSG

    def test_resolver_invoked_by_body(self):
        """守卫必须经 _resolve_bg_final_message（单一决策点）。"""
        api = _make_api()
        with patch.object(research_api, "_resolve_bg_final_message",
                          wraps=research_api._resolve_bg_final_message) as spy:
            pushed = _run_bg_chain(api, None)
        spy.assert_called_once()
        assert pushed[0]["message"] == CLOSURE
