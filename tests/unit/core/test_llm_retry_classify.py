# tests/unit/core/test_llm_retry_classify.py
# -*- coding: utf-8 -*-
from dataclasses import FrozenInstanceError

import pytest
from src.core.llm_retry import (
    LLMErrorClass, ParseOutcome, classify, DEGENERATE_EXACT, DEGENERATE_PREFIXES,
)


class _HttpErr(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status_code = status


class TestClassifyExceptions:
    @pytest.mark.parametrize("exc,expected", [
        (_HttpErr("too many requests", 429), LLMErrorClass.RATE_LIMIT),
        (_HttpErr("rate limit exceeded"), LLMErrorClass.RATE_LIMIT),
        (_HttpErr("unauthorized", 401), LLMErrorClass.AUTH),
        (_HttpErr("invalid api key"), LLMErrorClass.AUTH),
        (_HttpErr("insufficient_balance", 402), LLMErrorClass.BALANCE),
        (_HttpErr("quota exceeded"), LLMErrorClass.BALANCE),
        (_HttpErr("This model's maximum context length is 131072 tokens", 400),
         LLMErrorClass.CONTEXT_OVERFLOW),
        (_HttpErr("internal server error", 500), LLMErrorClass.TRANSPORT),
        (_HttpErr("bad gateway", 502), LLMErrorClass.TRANSPORT),
        (_HttpErr("Remote end closed connection without response"), LLMErrorClass.TRANSPORT),
        (_HttpErr("Connection error"), LLMErrorClass.TRANSPORT),
        (_HttpErr("Request timed out"), LLMErrorClass.TIMEOUT),
        (_HttpErr("something odd"), LLMErrorClass.UNKNOWN),
    ])
    def test_exception_classes(self, exc, expected):
        assert classify(exc=exc).error_class == expected

    def test_timeout_type_wins(self):
        assert classify(exc=TimeoutError("timed out")).error_class == LLMErrorClass.TIMEOUT

    def test_timeout_no_bogus_http_status(self):
        # M13: regex-derived "500" from "timed out after 500 ms" is misleading
        assert classify(exc=TimeoutError("timed out after 500 ms")).http_status is None

    def test_4xx_marker_refinement(self):
        # 400 status but "timeout" in text -> marker refinement applies
        c = classify(exc=_HttpErr("client timeout junk", 400))
        assert c.error_class == LLMErrorClass.TIMEOUT
        assert c.http_status == 400

    def test_status_precedence_over_marker(self):
        # true precedence: status 401 wins over rate-limit marker
        assert classify(exc=_HttpErr("rate limit exceeded", 401)).error_class == LLMErrorClass.AUTH

    def test_status_regex_fallback(self):
        # I6: _STATUS_RE fallback covers exceptions without status attributes
        assert classify(exc=Exception("Error code: 503")).error_class == LLMErrorClass.TRANSPORT

    def test_status_regex_no_false_positive(self):
        # I6: word boundary prevents 429 extraction from 1429
        assert classify(exc=Exception("1429 items processed")).error_class == LLMErrorClass.UNKNOWN


class TestClassifyOutput:
    def test_parse_outcome_truncated(self):
        c = classify(parse_outcome=ParseOutcome(ok=False, failure_kind="truncated"))
        assert c.error_class == LLMErrorClass.BAD_JSON_TRUNCATED

    @pytest.mark.parametrize("kind,expected", [
        ("no_json", LLMErrorClass.BAD_JSON_FORMAT),
        ("schema", LLMErrorClass.BAD_JSON_FORMAT),
        ("degenerate", LLMErrorClass.DEGENERATE),
    ])
    def test_parse_outcome_kinds(self, kind, expected):
        assert classify(parse_outcome=ParseOutcome(ok=False, failure_kind=kind)).error_class == expected

    def test_empty_raw(self):
        assert classify(raw="   ").error_class == LLMErrorClass.EMPTY_CONTENT

    def test_raw_exact_degenerate(self):
        for s in DEGENERATE_EXACT:
            assert classify(raw=s).error_class == LLMErrorClass.DEGENERATE

    def test_raw_prefix_degenerate(self):
        for p in DEGENERATE_PREFIXES:
            assert classify(raw=p + " think about this").error_class == LLMErrorClass.DEGENERATE

    def test_degenerate_prefix_case_insensitive(self):
        # M11: prefix matching is case-insensitive; strings are long enough
        # (> DEGENERATE_MIN_LEN) so the prefix check is the deciding factor
        assert classify(raw="HMM think about this more carefully").error_class == LLMErrorClass.DEGENERATE
        assert classify(raw="LET ME think about this more carefully").error_class == LLMErrorClass.DEGENERATE

    def test_raw_too_short(self):
        assert classify(raw="好的。").error_class == LLMErrorClass.DEGENERATE

    def test_prose_ok_is_unknown_marker(self):
        # 300-char prose with no parse hook: not classifiable as failure here
        assert classify(raw="x" * 300).error_class == LLMErrorClass.UNKNOWN

    def test_classification_and_parse_outcome_are_frozen(self):
        # M12: Classification/ParseOutcome are immutable value objects
        c = classify(raw="x" * 300)
        with pytest.raises(FrozenInstanceError):
            c.error_class = LLMErrorClass.TIMEOUT
        outcome = ParseOutcome(ok=False, failure_kind="truncated")
        with pytest.raises(FrozenInstanceError):
            outcome.failure_kind = "no_json"


class TestFixture155:
    def test_155_char_refusal_fixture(self):
        # 10-14 实锤样本（A1 回放夹具的最小化版本）
        raw = '{"status": "ready", "content": "来源统计：total_sources: 25, 无实质性章节内容"}'
        outcome = ParseOutcome(ok=False, failure_kind="degenerate")
        assert classify(parse_outcome=outcome, raw=raw).error_class == LLMErrorClass.DEGENERATE
