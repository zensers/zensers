# tests/unit/core/test_llm_retry_budget.py
# -*- coding: utf-8 -*-
import pytest
from src.core.llm_retry import Budget, LLMBudgetExhausted, LLMErrorClass, Classification


class TestBudget:
    def test_defaults_and_consume(self):
        b = Budget(max_calls=3, max_seconds=60)
        b.consume()
        assert b.calls_used == 1 and not b.exhausted()

    def test_call_exhaustion(self):
        b = Budget(max_calls=2, max_seconds=60)
        b.consume(); b.consume()
        assert b.exhausted()

    def test_time_exhaustion(self):
        b = Budget(max_calls=100, max_seconds=-1)
        assert b.exhausted()

    def test_scale_to_small_chapter(self):
        b = Budget.scale_to(2000)
        assert b.max_seconds == 600.0            # floor

    def test_scale_to_21k_chapter(self):
        # R3: 21000/25 + 180 = 1020s ≈ 17min（匹配 10-14 实测流式速度）
        b = Budget.scale_to(21000)
        assert b.max_seconds == pytest.approx(1020.0)

    def test_scale_to_huge_does_not_explode(self):
        b = Budget.scale_to(100000)
        assert b.max_seconds == pytest.approx(100000 / 25 + 180)

    def test_scale_to_calls_small(self):
        assert Budget.scale_to(21000).max_calls == 5


class TestExhaustedError:
    def test_carries_payload(self):
        cls = Classification(LLMErrorClass.DEGENERATE, detail="155c", raw_len=155)
        err = LLMBudgetExhausted(cls, attempts=5, elapsed=812.3,
                                 profile_notes=["mimo:3x degen", "deepseek:2x empty"])
        assert err.classification.error_class == LLMErrorClass.DEGENERATE
        assert err.attempts == 5
        assert "mimo:3x degen" in str(err)
