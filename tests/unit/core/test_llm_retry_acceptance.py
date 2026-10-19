# tests/unit/core/test_llm_retry_acceptance.py
# -*- coding: utf-8 -*-
"""A1/A2/A3 回放验收断言（spec §9，10-14 事故回放）。"""
import asyncio
import json
import time

import pytest

from src.core.llm_retry import (
    Budget, CandidateDesc, LLMBudgetExhausted, ParseOutcome, RetryEngine,
)

CANDS = [
    CandidateDesc(name="mimo", model="mimo-v2.6-flash", fallback_model="mimo-v2.5",
                  max_context_tokens=131072),
    CandidateDesc(name="deepseek", model="deepseek-v4-flash", fallback_model="deepseek-v4-flash",
                  max_context_tokens=128000),
]

# A1 夹具：10-14 的 155 字符拒答形态（最小化版本，与
# test_llm_retry_classify.TestFixture155 保持一致：JSON 可解析但 content
# 低于 writer 的 50 字可用底线 -> degenerate）。
REFUSAL_155 = '{"status": "ready", "content": "来源统计：total_sources: 25, 无实质性章节内容"}'
GOOD_JSON = '{"status": "ready", "content": "' + "完整章节正文。" * 300 + '"}'


def _writer_parse(raw):
    # 模拟 ChapterWriter._parse_with_outcome（chapter_writer.py:448）：
    # 可用 = JSON 可解析且 content >= 50 字；过短 -> degenerate；坏 JSON -> no_json。
    try:
        data = json.loads(raw)
        content = str(data.get("content", ""))
        if len(content.strip()) >= 50:
            return ParseOutcome(True, value=raw)
        return ParseOutcome(False, "degenerate")
    except Exception:
        return ParseOutcome(False, "no_json")


class _Scripted:
    """脚本化 transport：依次返回队列值；Exception 值则抛出。"""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def __call__(self, candidate, **kw):
        self.calls.append((candidate.name, kw))
        value = self.script.pop(0)
        if isinstance(value, Exception):
            raise value
        await asyncio.sleep(0)
        return value


class TestA1_155CharRefusal:
    def test_escalates_through_degenerate_ladder(self):
        """A1：155 字符拒答 -> strict_json(temp0.1) -> fallback_model -> 换 profile。"""
        t = _Scripted([REFUSAL_155, REFUSAL_155, REFUSAL_155, GOOD_JSON])
        started = time.monotonic()
        result = asyncio.run(RetryEngine(
            transport=t, candidates=lambda: CANDS, parse=_writer_parse,
            budget=Budget(max_calls=5, max_seconds=480), base_max_tokens=4000,
        ).run(prompt_builder=lambda v: "P", output_contract="json"))
        elapsed = time.monotonic() - started
        assert result == GOOD_JSON
        # 退化升级序列（spec §6 DEGENERATE 阶梯）：call#1 mimo base ->
        # call#2 mimo strict_json+temp0.1 -> call#3 mimo fallback_model ->
        # call#4 deepseek base -> 成功（3 次变异内升级换模型）。
        assert [name for name, _ in t.calls] == ["mimo", "mimo", "mimo", "deepseek"]
        assert t.calls[0][1]["model"] == "mimo-v2.6-flash"
        assert t.calls[0][1]["temperature"] is None
        assert "只输出一个合法的 JSON 对象" not in t.calls[0][1]["prompt"]
        assert t.calls[1][1]["model"] == "mimo-v2.6-flash"
        assert t.calls[1][1]["temperature"] == pytest.approx(0.1)
        assert t.calls[1][1]["prompt"].startswith("只输出一个合法的 JSON 对象")
        assert t.calls[2][1]["model"] == "mimo-v2.5"
        assert t.calls[2][1]["temperature"] is None
        assert t.calls[3][1]["model"] == "deepseek-v4-flash"
        # 输出类失败无指数退避：mock 回放应近即时完成（对照 81 分钟事故）
        assert elapsed < 5

    def test_all_refusal_exhausts_budget_with_classification(self):
        t = _Scripted([REFUSAL_155] * 5)
        with pytest.raises(LLMBudgetExhausted) as ei:
            asyncio.run(RetryEngine(
                transport=t, candidates=lambda: CANDS, parse=_writer_parse,
                budget=Budget(max_calls=4, max_seconds=60),
            ).run(prompt_builder=lambda v: "P", output_contract="json"))
        assert ei.value.classification.error_class.value == "degenerate"
        assert ei.value.attempts == 4


class TestA2_LargeChapter:
    def test_21k_chapter_single_call_budget_holds(self):
        """A2：21k 字正常生成：预算不误触发、max_tokens 一步到位、无压缩请求。"""
        big = '{"status": "ready", "content": "' + "完整" * 10500 + '"}'  # 21k 字
        t = _Scripted([big])
        seen = []
        budget = Budget.scale_to(21000)
        assert budget.max_seconds >= 1000
        result = asyncio.run(RetryEngine(
            transport=t, candidates=lambda: CANDS[:1], parse=_writer_parse,
            budget=budget, base_max_tokens=18200, allow_prompt_compression=False,
        ).run(prompt_builder=lambda v: (seen.append(v), "P")[1], output_contract="json"))
        assert result == big
        assert len(result) > 20000
        assert len(t.calls) == 1
        assert t.calls[0][1]["max_tokens"] == 18200
        assert all(not v.compress_wrapper for v in seen)

    def test_scale_never_compression_requests(self):
        """R1：CONTEXT_OVERFLOW 阶梯也从不发起压缩请求（compress_wrapper 恒 False）。"""
        overflow = RuntimeError("This model's maximum context length is 131072 tokens")
        t = _Scripted([overflow, overflow, GOOD_JSON])
        seen = []
        result = asyncio.run(RetryEngine(
            transport=t, candidates=lambda: CANDS, parse=_writer_parse,
            budget=Budget(max_calls=6, max_seconds=60), base_max_tokens=28000,
            allow_prompt_compression=False,
        ).run(prompt_builder=lambda v: (seen.append(v), "P")[1], output_contract="json"))
        assert result == GOOD_JSON
        # max_tokens 缩放 rung 后仍无法回答 -> ban mimo -> deepseek 兜底成功
        assert [name for name, _ in t.calls] == ["mimo", "mimo", "deepseek"]
        assert all(not v.compress_wrapper for v in seen)


class TestA3_BudgetToRescueChain:
    def test_exhausted_payload_matches_writer_error_contract(self):
        """A3：Budget 耗尽 -> failed 章节 -> Defense rescue。锁定载荷契约：
        ChapterWriter 以 budget_exhausted:<class>（chapter_writer.py:107）构造
        error 字符串，rescue 按分类路由；此处回放全拒答耗尽路径。"""
        t = _Scripted([REFUSAL_155] * 5)
        with pytest.raises(LLMBudgetExhausted) as ei:
            asyncio.run(RetryEngine(
                transport=t, candidates=lambda: CANDS, parse=_writer_parse,
                budget=Budget(max_calls=4, max_seconds=60),
            ).run(prompt_builder=lambda v: "P", output_contract="json"))
        payload = f"budget_exhausted:{ei.value.classification.error_class.value}"
        assert payload == "budget_exhausted:degenerate"
