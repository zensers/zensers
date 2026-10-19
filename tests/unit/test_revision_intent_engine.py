# -*- coding: utf-8 -*-
"""Task 8 retry-point #11: RevisionIntentAnalyzer 迁移到 call_llm_ex 重试引擎。

行为契约：
- analyze(): 单次引擎调用（output_contract=json、expected_output_chars=500、
  Budget(max_calls=3, max_seconds=120)、task_tag=revision_intent），
  盲目 MAX_LLM_RETRIES 原样重试循环移除。
- 解析钩子：合法 JSON dict → ok(value=dict)；否则 (False, "no_json")。
- LLMBudgetExhausted / 引擎失败 → 既有 fallback_to_regex 兜底，不 raise。
- analyze() 公开签名与 regex fallback 语义不变。
"""
import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from src.core.adjustment.revision_types import RevisionOpType
from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass

_EX_PATH = "src.core.llm_client.call_llm_ex"

_GOOD_INTENT = {
    "intents": [
        {
            "action_type": "modify",
            "target": {
                "raw_text": "市场规模",
                "section_refs": [],
                "location_strategy": "keyword",
                "is_ambiguous": False,
            },
            "confidence": 0.9,
        }
    ],
    "needs_clarification": False,
    "is_global_feedback": False,
    "confidence": 0.9,
}


class TestAnalyzeUsesEngine:
    def test_valid_json_success_single_engine_call(self):
        analyzer = RevisionIntentAnalyzer()
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return dict(_GOOD_INTENT)

        with patch(_EX_PATH, new_callable=AsyncMock, side_effect=fake_ex) as mock_ex:
            result = asyncio.run(analyzer.analyze("修改市场规模章节", None))

        mock_ex.assert_awaited_once()
        assert result.intents, "合法 JSON 应解析出意图"
        assert result.intents[0].action_type == RevisionOpType.MODIFY
        assert not result.intents[0].ambiguity_flags, "引擎路径不应带 regex_fallback 标记"
        assert captured["output_contract"] == "json"
        assert captured["expected_output_chars"] == 500
        assert captured["task_tag"] == "revision_intent"
        budget = captured["budget"]
        assert budget.max_calls == 3
        assert budget.max_seconds == 120
        assert callable(captured["parse"])

    def test_parse_hook_accepts_json_dict_rejects_prose(self):
        analyzer = RevisionIntentAnalyzer()
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return '{"intents": []}'

        with patch(_EX_PATH, new_callable=AsyncMock, side_effect=fake_ex):
            asyncio.run(analyzer.analyze("随便看看", None))

        parse = captured["parse"]
        ok = parse('{"intents": []}')
        assert ok.ok is True and isinstance(ok.value, dict)
        bad = parse("完全不是JSON")
        assert bad.ok is False and bad.failure_kind == "no_json"

    def test_budget_exhausted_falls_back_to_regex(self):
        analyzer = RevisionIntentAnalyzer()
        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.BAD_JSON_FORMAT, detail="parse_outcome:no_json"),
            attempts=3, elapsed=130.0, profile_notes=["mimo:3x no_json"],
        )
        with patch(_EX_PATH, new_callable=AsyncMock, side_effect=exhausted) as mock_ex:
            result = asyncio.run(analyzer.analyze("修改第三章的内容", None))

        mock_ex.assert_awaited_once()
        assert result.intents, "预算耗尽应走 regex 兜底而非空结果"
        assert result.intents[0].action_type == RevisionOpType.MODIFY
        assert "regex_fallback" in result.intents[0].ambiguity_flags

    def test_unusable_engine_dict_falls_back_without_second_call(self):
        # 引擎返回不含可用意图的 dict → 单次调用后直接 regex 兜底（无盲目重试）。
        analyzer = RevisionIntentAnalyzer()
        with patch(_EX_PATH, new_callable=AsyncMock,
                   side_effect=AsyncMock(return_value={"intents": []})) as mock_ex:
            result = asyncio.run(analyzer.analyze("修改第三章的内容", None))

        mock_ex.assert_awaited_once()
        assert result.intents
        assert "regex_fallback" in result.intents[0].ambiguity_flags


class TestBlindRetryLoopRemoved:
    def test_max_llm_retries_no_longer_drives_loop(self):
        assert not hasattr(RevisionIntentAnalyzer, "MAX_LLM_RETRIES") or \
            "range(self.MAX_LLM_RETRIES)" not in inspect.getsource(
                RevisionIntentAnalyzer.analyze)

    def test_analyze_signature_unchanged(self):
        sig = inspect.signature(RevisionIntentAnalyzer.analyze)
        assert list(sig.parameters) == ["self", "user_message", "report",
                                        "previous_analysis"]
