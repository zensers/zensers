# tests/unit/core/test_llm_retry_observability.py
# -*- coding: utf-8 -*-
"""观测日志格式锁定（spec §9，plan Task 11 Step 1）。

引擎 ``_log``（llm_retry.py）的实际输出格式为：
``LLM_RETRY <task_tag> <event> <k=v k=v ...>``
失败分类挂在 kv 键 ``cls`` 下（如 ``cls=degenerate``）。本文件锁定该格式：
改动 ``_log`` 输出形状时必须同步更新此处的断言（或证明下游无消费方）。
"""
import asyncio
import logging

import pytest

from src.core.llm_retry import (
    Budget, CandidateDesc, LLMBudgetExhausted, Classification,
    LLMErrorClass, ParseOutcome, RetryEngine, get_retry_stats,
)


def test_retry_and_final_log_lines(caplog):
    """重试 -> 成功的路径：LLM_RETRY 行携带 task_tag 与失败分类 kv。"""

    class T:
        def __init__(self, script):
            self.script = list(script)

        async def __call__(self, candidate, **kw):
            return self.script.pop(0)

    def parse(raw):
        if raw == "GOOD":
            return ParseOutcome(True, value=raw)
        return ParseOutcome(False, "degenerate")

    engine = RetryEngine(
        transport=T(["...", "GOOD"]),
        candidates=lambda: [
            CandidateDesc(name="alpha", model="model-a",
                          fallback_model="model-b", max_context_tokens=131072),
        ],
        parse=parse,
        budget=Budget(max_calls=5, max_seconds=60),
        task_tag="task_x",
    )
    with caplog.at_level(logging.INFO, logger="src.core.llm_retry"):
        result = asyncio.run(engine.run(prompt_builder=lambda v: "P"))

    assert result == "GOOD"
    text = "\n".join(r.getMessage() for r in caplog.records)
    # 前缀：task_tag 逐字出现
    assert "LLM_RETRY task_x" in text
    # 失败分类 kv（_log 的实际键名是 cls，非 error_class）
    assert "cls=degenerate" in text
    # 事件名：output_rejected（被拒）与 success（最终成功）都应出现
    assert "output_rejected" in text
    assert "success" in text


def test_budget_exhausted_payload_format():
    """LLMBudgetExhausted 载荷契约：str 包含 "budget exhausted"。"""
    exc = LLMBudgetExhausted(
        Classification(LLMErrorClass.DEGENERATE, detail="parse_outcome:degenerate"),
        attempts=3, elapsed=12.0, profile_notes=["alpha:3xdegenerate"],
    )
    assert "budget exhausted" in str(exc)
    assert "degenerate" in str(exc)


def _credential_candidate() -> CandidateDesc:
    """带凭证字段的候选：用于断言统计/日志绝不含凭证。"""
    return CandidateDesc(name="alpha", model="model-a", fallback_model="model-b",
                         max_context_tokens=1024, api_key="sk-SECRET-KEY",
                         base_url="https://secret-endpoint.example")


class TestCallFinalAndStats:
    def test_success_run_emits_call_final(self, caplog):
        """成功终止路径：call_final 行携带 success=True 与 attempts。"""

        class T:
            async def __call__(self, candidate, **kw):
                return "GOOD"

        engine = RetryEngine(
            transport=T(), candidates=lambda: [_credential_candidate()],
            parse=lambda r: ParseOutcome(True, value=r),
            budget=Budget(max_calls=3, max_seconds=30), task_tag="task_ok",
        )
        with caplog.at_level(logging.INFO, logger="src.core.llm_retry"):
            result = asyncio.run(engine.run(prompt_builder=lambda v: "P"))

        assert result == "GOOD"
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "call_final" in text
        assert "success=True" in text
        assert "attempts=1" in text

    def test_exhaustion_emits_call_final_and_counts_stats(self, caplog):
        """耗尽终止路径：call_final success=False；失败分类进统计；无内容泄漏。"""

        class T:
            async def __call__(self, candidate, **kw):
                return "..."

        engine = RetryEngine(
            transport=T(), candidates=lambda: [_credential_candidate()],
            parse=lambda r: ParseOutcome(False, "degenerate"),
            budget=Budget(max_calls=3, max_seconds=30), task_tag="task_ex",
        )
        with caplog.at_level(logging.INFO, logger="src.core.llm_retry"):
            with pytest.raises(LLMBudgetExhausted):
                asyncio.run(engine.run(
                    prompt_builder=lambda v: "PROMPT-CONTENT-SHOULD-NEVER-LEAK"))

        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "call_final" in text
        assert "success=False" in text
        assert "final_class=degenerate" in text

        stats = get_retry_stats()
        key = str(("task_ex", "alpha", "degenerate"))
        assert stats["by_task_candidate_class"].get(key, 0) >= 1
        assert stats["total"] >= 1
        # 统计只含标签/分类：prompt 内容与凭证绝不出现
        assert "PROMPT-CONTENT-SHOULD-NEVER-LEAK" not in str(stats)
        assert "sk-SECRET-KEY" not in str(stats)
        assert "secret-endpoint" not in str(stats)

    def test_stats_snapshot_is_a_copy(self):
        """get_retry_stats 返回快照：改动返回值不影响内部计数。"""
        before = get_retry_stats()
        snapshot = get_retry_stats()
        snapshot["total"] = -999
        snapshot["by_task_candidate_class"]["BOGUS-KEY"] = 123
        after = get_retry_stats()
        assert after["total"] == before["total"]
        assert "BOGUS-KEY" not in after["by_task_candidate_class"]
