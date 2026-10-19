# tests/unit/core/test_llm_retry_policies.py
# -*- coding: utf-8 -*-
import pytest
from src.core.llm_retry import LLMErrorClass, POLICIES, RetryVariations, next_step


class TestPolicyTable:
    def test_all_spec_classes_have_policies(self):
        required = {
            LLMErrorClass.RATE_LIMIT, LLMErrorClass.TIMEOUT, LLMErrorClass.TRANSPORT,
            LLMErrorClass.AUTH, LLMErrorClass.BALANCE, LLMErrorClass.CONTEXT_OVERFLOW,
            LLMErrorClass.EMPTY_CONTENT, LLMErrorClass.DEGENERATE,
            LLMErrorClass.BAD_JSON_TRUNCATED, LLMErrorClass.BAD_JSON_FORMAT,
            LLMErrorClass.UNKNOWN,
        }
        assert required <= set(POLICIES)

    def test_attempt_counts_match_spec(self):
        assert POLICIES[LLMErrorClass.RATE_LIMIT].max_attempts == 3
        assert POLICIES[LLMErrorClass.TIMEOUT].max_attempts == 3
        assert POLICIES[LLMErrorClass.TRANSPORT].max_attempts == 3
        assert POLICIES[LLMErrorClass.EMPTY_CONTENT].max_attempts == 3
        assert POLICIES[LLMErrorClass.DEGENERATE].max_attempts == 3
        assert POLICIES[LLMErrorClass.CONTEXT_OVERFLOW].max_attempts == 2
        assert POLICIES[LLMErrorClass.BAD_JSON_TRUNCATED].max_attempts == 2
        assert POLICIES[LLMErrorClass.BAD_JSON_FORMAT].max_attempts == 2
        assert POLICIES[LLMErrorClass.UNKNOWN].max_attempts == 1
        assert POLICIES[LLMErrorClass.AUTH].max_attempts == 0
        assert POLICIES[LLMErrorClass.BALANCE].max_attempts == 0

    @pytest.mark.parametrize("error_class", [LLMErrorClass.AUTH, LLMErrorClass.BALANCE])
    def test_zero_retry_policy_terminal_instruction(self, error_class):
        # C1: max_attempts==0 policies surface ladder[0] as a TERMINAL INSTRUCTION
        step = next_step(error_class, 0)
        assert step is not None
        assert step.ban_profile is True

    def test_degenerate_ladder_mutation_sequence(self):
        policy = POLICIES[LLMErrorClass.DEGENERATE]
        steps = [policy.step(i) for i in range(policy.max_attempts)]
        assert steps[0].strict_json_prefix and steps[0].temperature == 0.1
        assert steps[1].switch_model
        assert steps[2].ban_profile  # 换 profile（拉黑当前）

    def test_truncated_ladder_raises_max_tokens(self):
        policy = POLICIES[LLMErrorClass.BAD_JSON_TRUNCATED]
        step0 = policy.step(0)
        assert step0.max_tokens_factor == pytest.approx(1.5)
        # 引擎累积: 1.5 * 1.5 = 2.25 (spec R2)
        assert policy.step(1).max_tokens_factor == pytest.approx(1.5)
        assert policy.step(1).switch_model is True

    def test_context_overflow_never_compresses_by_default(self):
        policy = POLICIES[LLMErrorClass.CONTEXT_OVERFLOW]
        for i in range(policy.max_attempts):
            step = policy.step(i)
            # R1: policy must not request compression
            assert not step.compress_wrapper
            assert step.max_tokens_factor <= 1.0  # 只减输出，不减输入数据

    def test_step_beyond_ladder_is_none(self):
        assert next_step(LLMErrorClass.RATE_LIMIT, 99) is None
