# src/core/llm_retry.py
# -*- coding: utf-8 -*-
"""Failure-mode-aware retry engine for LLM calls.

Spec: docs/superpowers/specs/2026-10-15-llm-retry-engine-design.md
This module is stdlib-only by design: llm_client injects its transport and
candidate list, so llm_retry never imports llm_client (no cycles).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence  # Callable: used by RetryEngine (Task 4)

logger = logging.getLogger(__name__)  # used by RetryEngine (Task 4)


class LLMErrorClass(str, Enum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    AUTH = "auth"
    BALANCE = "balance"
    CONTEXT_OVERFLOW = "context_overflow"
    EMPTY_CONTENT = "empty_content"
    DEGENERATE = "degenerate"
    BAD_JSON_TRUNCATED = "bad_json_truncated"
    BAD_JSON_FORMAT = "bad_json_format"
    UNKNOWN = "unknown"


DEGENERATE_MIN_LEN = int(os.environ.get("LLM_DEGENERATE_MIN_LEN", "30"))
# 10-14 实锤样本（spec §5）：默认模式集，A1 回放夹具的基础。
DEGENERATE_EXACT = {"...", "。。。", "。"}
DEGENERATE_PREFIXES = ("Hmm", "Let me", "嗯")
# M11: 预计算小写前缀，匹配时对 stripped.lower() 使用（大小写不敏感）
_DEGENERATE_PREFIXES_LOWER = tuple(p.lower() for p in DEGENERATE_PREFIXES)

_STATUS_RE = re.compile(r"\b(4\d\d|5\d\d|529)\b")
# I2: 不放裸数字状态码（"401"/"402"/"429"）——子串匹配会把 "req_4401 failed"
# 误判为 AUTH。数字状态一律走 _http_status（词边界）+ classify 的 429/401/402 分支。
_AUTH_MARKERS = ("unauthorized", "invalid api key", "authentication")
_BALANCE_MARKERS = ("insufficient_balance", "quota", "billing")
_CONTEXT_MARKERS = ("context length", "maximum context", "context_length_exceeded",
                    "too many tokens", "input tokens exceed")
_RATE_MARKERS = ("too many requests", "rate limit")
_TIMEOUT_MARKERS = ("timeout", "timed out")
_TRANSPORT_MARKERS = ("connection", "remote end closed", "connection reset",
                      "server disconnected", "name or service not known",
                      "temporarily unavailable", "overloaded")


@dataclass(frozen=True)
class ParseOutcome:
    """Caller-supplied parse result for output-shape classification."""
    ok: bool
    failure_kind: str = ""   # "" | truncated | no_json | degenerate | schema
    value: Any = None


@dataclass(frozen=True)
class Classification:
    error_class: LLMErrorClass
    detail: str = ""
    http_status: Optional[int] = None
    raw_len: int = 0


def _http_status(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 400 <= value <= 599:
            return value
    match = _STATUS_RE.search(str(exc))
    return int(match.group(1)) if match else None


def _marker_class(text: str) -> Optional[LLMErrorClass]:
    lowered = text.lower()
    if any(m in lowered for m in _RATE_MARKERS):
        return LLMErrorClass.RATE_LIMIT
    if any(m in lowered for m in _AUTH_MARKERS):
        return LLMErrorClass.AUTH
    if any(m in lowered for m in _BALANCE_MARKERS):
        return LLMErrorClass.BALANCE
    if any(m in lowered for m in _CONTEXT_MARKERS):
        return LLMErrorClass.CONTEXT_OVERFLOW
    if any(m in lowered for m in _TIMEOUT_MARKERS):
        return LLMErrorClass.TIMEOUT
    if any(m in lowered for m in _TRANSPORT_MARKERS):
        return LLMErrorClass.TRANSPORT
    return None


def classify(
    exc: Optional[BaseException] = None,
    parse_outcome: Optional[ParseOutcome] = None,
    raw: Optional[str] = None,
) -> Classification:
    """Pure classifier.

    Priority: TimeoutError types > HTTP status > string markers > output shape.
    Signals are evaluated exclusively: if exc is given, parse_outcome/raw are
    ignored (test Fixture155 passes both but only parse_outcome matters).
    """
    if exc is not None:
        status = _http_status(exc)
        text = str(exc)
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            # M13: http_status=None —— "timed out after 500 ms" 正则提取出的
            # "500" 是误导，超时类不该携带 HTTP 状态。
            return Classification(LLMErrorClass.TIMEOUT, detail=text, http_status=None)
        if status == 429:
            return Classification(LLMErrorClass.RATE_LIMIT, detail=text, http_status=status)
        if status == 401:
            return Classification(LLMErrorClass.AUTH, detail=text, http_status=status)
        if status == 402:
            return Classification(LLMErrorClass.BALANCE, detail=text, http_status=status)
        if status == 400 and any(m in text.lower() for m in _CONTEXT_MARKERS):
            return Classification(LLMErrorClass.CONTEXT_OVERFLOW, detail=text, http_status=status)
        if status is not None and status >= 500:
            return Classification(LLMErrorClass.TRANSPORT, detail=text, http_status=status)
        if status is not None and 400 <= status < 500:
            # 4xx that is not 429/401/402/overflow: string markers may refine
            marker = _marker_class(text)
            if marker is not None:
                return Classification(marker, detail=text, http_status=status)
            return Classification(LLMErrorClass.UNKNOWN, detail=text, http_status=status)
        marker = _marker_class(text)
        if marker is not None:
            return Classification(marker, detail=text, http_status=status)
        return Classification(LLMErrorClass.UNKNOWN, detail=text, http_status=status)

    if parse_outcome is not None and not parse_outcome.ok:
        kind = parse_outcome.failure_kind
        mapped = {
            "truncated": LLMErrorClass.BAD_JSON_TRUNCATED,
            "no_json": LLMErrorClass.BAD_JSON_FORMAT,
            "schema": LLMErrorClass.BAD_JSON_FORMAT,
            "degenerate": LLMErrorClass.DEGENERATE,
        }.get(kind, LLMErrorClass.UNKNOWN)
        return Classification(mapped, detail=f"parse_outcome:{kind}")

    if raw is not None:
        stripped = raw.strip()
        if not stripped:
            return Classification(LLMErrorClass.EMPTY_CONTENT, raw_len=0)
        if stripped in DEGENERATE_EXACT or len(stripped) < DEGENERATE_MIN_LEN:
            return Classification(LLMErrorClass.DEGENERATE, raw_len=len(stripped))
        # M11: 大小写不敏感前缀匹配
        lowered = stripped.lower()
        if any(lowered.startswith(p) for p in _DEGENERATE_PREFIXES_LOWER):
            return Classification(LLMErrorClass.DEGENERATE, raw_len=len(stripped))
        return Classification(LLMErrorClass.UNKNOWN, raw_len=len(stripped))

    return Classification(LLMErrorClass.UNKNOWN)


# ---- 变异阶梯（spec §6）----

@dataclass(frozen=True)
class RetryVariations:
    """Mutation instruction for one attempt. prompt_builder merges prefixes.

    Contracts (spec §4 R1 / §6):
    - ``switch_model``: use the *current candidate's* fallback_model —— 不是
      自由选模型；candidate 排序（如 max_context_tokens 大者优先）是 llm_client
      的职责。
    - ``ban_profile``: 拉黑当前 profile，推进到下一个 candidate。
    - ``compress_wrapper``: 永远只是 REQUEST —— 执行方必须先确认调用方显式
      opt-in 才能压缩任何东西，且绝不触碰研究数据（``chapter_data``）。
    """
    temperature: Optional[float] = None       # absolute override
    max_tokens_factor: float = 1.0
    strict_json_prefix: bool = False
    strip_reasoning: bool = False
    switch_model: bool = False                # profile.fallback_model
    ban_profile: bool = False                 # blacklist current profile, next candidate
    compress_wrapper: bool = False            # R1: request only; caller must opt in


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    ladder: Sequence[RetryVariations]
    backoff_base: float = 1.0
    backoff_cap: float = 8.0

    def step(self, index: int) -> RetryVariations:
        return self.ladder[min(index, len(self.ladder) - 1)]


_V = RetryVariations
POLICIES: Dict[LLMErrorClass, RetryPolicy] = {
    # RATE_LIMIT: 同模型退避 2/4/8s（引擎处理 backoff），3 次后换 profile
    LLMErrorClass.RATE_LIMIT: RetryPolicy(3, (_V(), _V(), _V(ban_profile=True)),
                                          backoff_base=2.0, backoff_cap=8.0),
    LLMErrorClass.TIMEOUT: RetryPolicy(3, (_V(), _V(switch_model=True), _V(ban_profile=True))),
    LLMErrorClass.TRANSPORT: RetryPolicy(3, (_V(), _V(switch_model=True), _V(ban_profile=True))),
    # AUTH/BALANCE: 不重试，拉黑换下一 profile（引擎按 max_attempts==0 处理）
    LLMErrorClass.AUTH: RetryPolicy(0, (_V(ban_profile=True),)),
    LLMErrorClass.BALANCE: RetryPolicy(0, (_V(ban_profile=True),)),
    # CONTEXT_OVERFLOW: 只动输出侧/换端（I7 契约）：
    # - rung 1 (ban_profile=True) = "advance to next candidate"；candidate 排序
    #   （max_context_tokens 大者优先）由 llm_client 负责（spec §4 R1）。
    # - compress_wrapper 只会是 REQUEST（本策略从不设置）：执行方必须先确认
    #   调用方显式 opt-in，且绝不触碰 chapter_data。
    LLMErrorClass.CONTEXT_OVERFLOW: RetryPolicy(
        2, (_V(max_tokens_factor=0.5), _V(ban_profile=True))),
    LLMErrorClass.EMPTY_CONTENT: RetryPolicy(
        3, (_V(strip_reasoning=True), _V(temperature=0.3), _V(switch_model=True))),
    LLMErrorClass.DEGENERATE: RetryPolicy(
        3, (_V(strict_json_prefix=True, temperature=0.1), _V(switch_model=True),
            _V(ban_profile=True))),
    LLMErrorClass.BAD_JSON_TRUNCATED: RetryPolicy(
        2, (_V(max_tokens_factor=1.5), _V(max_tokens_factor=1.5, switch_model=True))),
    LLMErrorClass.BAD_JSON_FORMAT: RetryPolicy(
        2, (_V(strict_json_prefix=True, temperature=0.1), _V(strict_json_prefix=True,
            temperature=0.1, switch_model=True))),
    LLMErrorClass.UNKNOWN: RetryPolicy(1, (_V(),)),
}


def next_step(error_class: LLMErrorClass, attempt_index: int) -> Optional[RetryVariations]:
    """Resolve the mutation instruction for attempt_index of error_class.

    A policy with max_attempts == 0 has no retries; its ladder[0] is a TERMINAL
    INSTRUCTION (ban_profile) that the engine applies before moving to the next
    candidate. attempt_index is ignored for such policies.
    """
    # M10: .get() + UNKNOWN 兜底，未来新增枚举成员不会 KeyError
    policy = POLICIES.get(error_class, POLICIES[LLMErrorClass.UNKNOWN])
    if policy.max_attempts == 0:
        # C1: 零重试策略的 ladder[0] 是终止指令（ban_profile），引擎先执行它
        # 再换下一个 candidate。
        return policy.ladder[0]
    if attempt_index >= policy.max_attempts:
        return None
    return policy.step(attempt_index)


# ---- 双层预算（spec §4 R3, §7）----

@dataclass
class Budget:
    max_calls: int = 4
    max_seconds: float = 600.0
    calls_used: int = 0
    started: float = field(default_factory=time.monotonic)

    def consume(self) -> None:
        self.calls_used += 1

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def exhausted(self) -> bool:
        return self.calls_used >= self.max_calls or self.elapsed() >= self.max_seconds

    @classmethod
    def scale_to(
        cls,
        expected_output_chars: float,
        *,
        max_calls: int = 5,
        chars_per_second: float = 25.0,
        floor_seconds: float = 600.0,
        slack_seconds: float = 180.0,
    ) -> "Budget":
        """R3: budget scales with expected output size so a large chapter
        generating normally never trips the budget (spec §4)."""
        seconds = max(floor_seconds, float(expected_output_chars) / chars_per_second
                      + slack_seconds)
        return cls(max_calls=max_calls, max_seconds=seconds)


class LLMBudgetExhausted(RuntimeError):
    """Raised when an operation's Budget is spent without a usable result."""

    def __init__(self, classification: Classification, attempts: int, elapsed: float,
                 profile_notes: Optional[List[str]] = None):
        self.classification = classification
        self.attempts = attempts
        self.elapsed = elapsed
        self.profile_notes = profile_notes or []
        super().__init__(
            f"LLM budget exhausted after {attempts} attempts / {elapsed:.0f}s "
            f"(final class={classification.error_class.value}, detail={classification.detail}); "
            f"profiles: {'; '.join(self.profile_notes)}"
        )


class LLMStreamCommitted(RuntimeError):
    """Raised when a streaming attempt already emitted user-visible tokens;
    retrying would duplicate them."""


# ---- 轻量调用统计（spec §9 观测性）----

# 进程级累计：按 (task_tag, candidate_name, error_class_value) 计失败尝试数。
# 只含标签与分类值，绝无 prompt 内容或凭证。
_CALL_STATS: Counter = Counter()


def _record_stat(task_tag: str, candidate_name: str, error_class_value: str) -> None:
    """累计一次失败尝试到进程级计数器（键为三元组）。"""
    _CALL_STATS[(task_tag, candidate_name, error_class_value)] += 1


def get_retry_stats() -> Dict[str, Any]:
    """Snapshot of cumulative retry-failure counters, for diagnostics only.

    Exposed for diagnostics/observability; keys are stringified
    ``(task_tag, candidate_name, error_class_value)`` tuples — the stats
    never contain prompt content or credentials. Returns a fresh copy:
    mutating it does not affect internal state.
    """
    return {
        "by_task_candidate_class": {
            str(key): count for key, count in _CALL_STATS.items()
        },
        "total": sum(_CALL_STATS.values()),
    }


# ---- RetryEngine（spec §3.1, §6）----

@dataclass(frozen=True)
class CandidateDesc:
    """llm_client 注入的轻量 profile 描述（非 LLMProfile 本体，避免 import 环）。

    ``api_key`` / ``base_url`` 让候选切换真正跨端点（仅改 model 名的切换救不了
    单端点故障）。凭证只驻留内存、随 CandidateDesc 传递：引擎日志（LLM_RETRY
    行与 attempt_log）只记 candidate.name，绝不记录这两个字段。
    """
    name: str
    model: str
    fallback_model: str = ""
    max_context_tokens: int = 0
    api_key: str = ""
    base_url: str = ""
    # Profile-constrained temperature (e.g. kimi only accepts 1): when set,
    # the transport uses it instead of the settings default so the base
    # attempt (variation.temperature is None) does not 400.  Explicit engine
    # variations still win — the mutation ladder keeps its right to override.
    temperature: Optional[float] = None
    # Profile-constrained top_p (e.g. kimi-k3 rejects top_p != 0.95 with
    # "invalid top_p"): when set, the transport forwards it instead of the
    # settings default so the base attempt does not 400.
    top_p: Optional[float] = None


STRICT_JSON_PREFIX = "只输出一个合法的 JSON 对象：不要解释、不要 markdown 代码块、不要省略任何字段。"
REASONING_STRIP_NOTE = "直接给出正式回答正文，不要输出任何思考过程。"


class RetryEngine:
    """classify -> 变异 -> 尝试 的通用循环，依赖全部注入（spec §3.1）。

    - ``transport``: 单次供应商调用，抛异常即传输失败。
    - ``candidates``: 有序候选描述列表，run 开始时取一次。
    - ``parse``: 可选输出解析钩子；缺省时引擎做形状检测（:meth:`_shape_check`）。
    引擎持有策略表、退避、预算记账与 attempt_log。``_banned`` 是实例级黑名单
    （测试隔离，无模块级可变状态），用 :meth:`reset_banned` 清空。

    阶梯索引契约（测试 + A1 验收锁定）：0 基 attempt_index 的第 N 次尝试失败后，
    下一 rung = next_step(class, N)，即 rung0 应用在第 2 次传输调用上；
    max_attempts==0 的策略（AUTH/BALANCE）经 next_step 返回终止指令
    （ban_profile=True），引擎 ban+换候选，不计为同候选的重试尝试。
    """

    def __init__(self, *, transport: Callable[..., Any],
                 candidates: Callable[[], Sequence[CandidateDesc]],
                 parse: Optional[Callable[[str], ParseOutcome]] = None,
                 budget: Optional[Budget] = None,
                 base_max_tokens: Optional[int] = None,
                 allow_prompt_compression: bool = False,
                 task_tag: str = "",
                 ban_hook: Optional[Callable[[str], None]] = None):
        self._transport = transport
        self._candidates = candidates
        self._parse = parse
        self._budget = budget or Budget()
        self._base_max_tokens = base_max_tokens
        self._allow_compression = allow_prompt_compression
        self._task_tag = task_tag
        self._ban_hook = ban_hook
        self._banned: set = set()
        self.attempt_log: List[Dict[str, Any]] = []

    def reset_banned(self) -> None:
        self._banned.clear()

    # -- helpers ----------------------------------------------------------
    def _ban(self, name: str) -> None:
        """Single choke point for bans: instance-level set + durable hook.

        ``ban_hook``（llm_client 传 ban_profile）让 ban 跨引擎实例持久化，
        否则实例级 ``_banned`` 随引擎一起消亡、上层永远看不到拉黑结果。
        """
        self._banned.add(name)
        if self._ban_hook is not None:
            self._ban_hook(name)

    def _log(self, event: str, **kw: Any) -> None:
        logger.info("LLM_RETRY %s %s %s", self._task_tag, event,
                    " ".join(f"{k}={v}" for k, v in kw.items()))

    @staticmethod
    def _mutation_tag(v: RetryVariations) -> str:
        """attempt_log / LLM_RETRY 行用的紧凑变异标记（spec §9 风格）。"""
        parts: List[str] = []
        if v.temperature is not None:
            parts.append(f"temp{v.temperature}")
        if v.max_tokens_factor != 1.0:
            parts.append(f"mt{v.max_tokens_factor}")
        if v.strict_json_prefix:
            parts.append("strict_json")
        if v.strip_reasoning:
            parts.append("strip_reasoning")
        if v.switch_model:
            parts.append("switch_model")
        if v.compress_wrapper:
            parts.append("compress_req")  # R1：仅请求标记，压缩执行在调用方
        if v.ban_profile:
            parts.append("ban_profile")
        return "+".join(parts) if parts else "base"

    def _effective_max_tokens(self, factor: float) -> Optional[int]:
        if self._base_max_tokens is None:
            return None
        return int(self._base_max_tokens * factor)

    def _unapplicable(self, v: RetryVariations, candidate: CandidateDesc) -> bool:
        """无法改变任何请求参数的 rung —— 执行它就是同参数盲目重试（spec G1
        反模式），按阶梯耗尽处理（I7：换候选）。两种触发：
        - 纯 max_tokens 因子 rung 且无 base_max_tokens 可缩放；
        - switch_model rung 但候选没有可用 fallback（llm_client 对无备用端点
          的 profile 发空串，或 fallback 与主模型相同）。
        """
        if v.ban_profile:
            return False
        factor_only = (self._base_max_tokens is None
                       and v.max_tokens_factor != 1.0
                       and v.temperature is None
                       and not v.strict_json_prefix
                       and not v.strip_reasoning
                       and not v.switch_model)
        cannot_switch = (v.switch_model
                         and (not candidate.fallback_model
                              or candidate.fallback_model == candidate.model))
        return factor_only or cannot_switch

    def _advance(self, error_class: LLMErrorClass, attempt_index: int,
                 candidate: CandidateDesc, attempts: int,
                 notes: List[str]) -> Optional[RetryVariations]:
        """失败后解析下一 rung。返回下一变异；None = 本候选终局（ban/耗尽）。"""
        nxt = next_step(error_class, attempt_index)
        if nxt is not None and nxt.ban_profile:
            # 终止指令（AUTH/BALANCE 的 ladder[0]，或阶梯末位 ban rung）
            self._ban(candidate.name)
        if nxt is None or self._unapplicable(nxt, candidate) or nxt.ban_profile:
            notes.append(f"{candidate.name}:{attempts}x{error_class.value}")
            return None
        return nxt

    def _backoff(self, error_class: LLMErrorClass, attempt_index: int) -> float:
        policy = POLICIES.get(error_class, POLICIES[LLMErrorClass.UNKNOWN])
        if policy.backoff_base > 1:
            return min(policy.backoff_base * (2 ** (attempt_index - 1)),
                       policy.backoff_cap)
        return min(1.0 * attempt_index, policy.backoff_cap)

    @staticmethod
    def _shape_check(raw: str, output_contract: str) -> ParseOutcome:
        """无 parse 钩子时的输出形状检测。

        退化判定用模式集（EXACT/前缀，spec §5 实锤样本）而非 classify() 的
        len<30 启发式 —— 后者会把短合法输出（下游自定义成功标记等）误杀。
        """
        stripped = (raw or "").strip()
        if not stripped:
            return ParseOutcome(False, "no_json")
        if stripped in DEGENERATE_EXACT or any(
                stripped.lower().startswith(p) for p in _DEGENERATE_PREFIXES_LOWER):
            return ParseOutcome(False, "degenerate")
        if output_contract == "json" and not stripped.startswith("{"):
            return ParseOutcome(False, "no_json")
        return ParseOutcome(True, value=raw)

    # -- 主循环 ------------------------------------------------------------
    async def run(self, *, prompt_builder: Callable[[RetryVariations], str],
                  output_contract: str = "prose") -> Any:
        """驱动尝试直到产出可用结果或预算耗尽。

        每次迭代先查预算；每次尝试前 ``budget.consume()``。返回可用输出
        （parse 钩子的 value，缺省原始串）；候选/预算耗尽时抛
        ``LLMBudgetExhausted``（携带最终 Classification 与各候选摘要）。
        调用方侧的 bug 异常（prompt_builder / parse 抛出）原样上抛，不入
        重试循环。

        终态观测（spec §9）：无论成败，run 终止时经 finally 发一条
        ``call_final`` 终态行（success/attempts/budget_calls/elapsed_s/
        final_class），并把 attempt_log 逐条累计进 ``_record_stat``。
        """
        final_class = Classification(LLMErrorClass.UNKNOWN)
        attempts = 0
        notes: List[str] = []
        factor = 1.0  # 累积 max_tokens 因子：整个 run 内持续（R2：截断升级累积）
        run_started = time.monotonic()
        success = False
        try:
            for candidate in self._candidates():
                if candidate.name in self._banned:
                    continue
                current_class = LLMErrorClass.UNKNOWN
                attempt_index = 0
                variation = _V()  # 每个候选的第一跳：无变异
                while True:
                    # 1. 每次迭代最先查预算
                    if self._budget.exhausted():
                        raise LLMBudgetExhausted(final_class, attempts,
                                                 self._budget.elapsed(), notes)
                    # 2-3. 组装 prompt / 参数级变异
                    prompt = prompt_builder(variation)
                    if variation.strict_json_prefix and output_contract == "json":
                        prompt = f"{STRICT_JSON_PREFIX}\n{prompt}"
                    if variation.strip_reasoning:
                        prompt = f"{REASONING_STRIP_NOTE}\n{prompt}"
                    model = (candidate.fallback_model
                             if variation.switch_model and candidate.fallback_model
                             else candidate.model)
                    if variation.max_tokens_factor != 1.0:
                        factor *= variation.max_tokens_factor
                    self._budget.consume()
                    attempts += 1
                    started = time.monotonic()
                    try:
                        raw = await self._transport(
                            candidate, prompt=prompt, model=model,
                            max_tokens=self._effective_max_tokens(factor),
                            temperature=variation.temperature)
                    except Exception as exc:
                        # C1: 流式已向用户发出 token 后，任何重试（同候选或换候选）
                        # 都会重复用户可见内容 —— 立即终止整个 run：不分类、不退避、
                        # 不推进候选。
                        if isinstance(exc, LLMStreamCommitted):
                            self._log("stream_committed", candidate=candidate.name,
                                      attempt=attempts, detail=str(exc))
                            raise
                        # 4. 传输失败：分类 → 记账 → 解析下一 rung
                        classification = classify(exc=exc)
                        current_class = classification.error_class
                        final_class = classification
                        mutation = self._mutation_tag(variation)
                        elapsed = round(time.monotonic() - started, 1)
                        self._log("transport_error", candidate=candidate.name,
                                  attempt=attempts, mutation=mutation,
                                  cls=current_class.value, elapsed=elapsed)
                        self.attempt_log.append({"class": current_class.value,
                                                 "attempt": attempts,
                                                 "mutation": mutation,
                                                 "candidate": candidate.name,
                                                 "elapsed": elapsed})
                        variation = self._advance(current_class, attempt_index,
                                                  candidate, attempts, notes)
                        if variation is None:
                            break
                        attempt_index += 1
                        await asyncio.sleep(self._backoff(current_class, attempt_index))
                        continue

                    outcome = (self._parse(raw) if self._parse
                               else self._shape_check(raw, output_contract))
                    if outcome.ok:
                        self._log("success", candidate=candidate.name, attempt=attempts)
                        success = True
                        return outcome.value if outcome.value is not None else raw
                    # 5. 输出形状失败：分类 → 记账 → 解析下一 rung（无指数退避）
                    classification = classify(parse_outcome=outcome, raw=raw)
                    current_class = classification.error_class
                    final_class = classification
                    mutation = self._mutation_tag(variation)
                    self._log("output_rejected", candidate=candidate.name,
                              attempt=attempts, mutation=mutation,
                              cls=current_class.value, raw_len=len(raw.strip()))
                    self.attempt_log.append({"class": current_class.value,
                                             "attempt": attempts,
                                             "mutation": mutation,
                                             "candidate": candidate.name,
                                             "elapsed": round(time.monotonic() - started, 1)})
                    variation = self._advance(current_class, attempt_index,
                                              candidate, attempts, notes)
                    if variation is None:
                        break
                    attempt_index += 1
                    await asyncio.sleep(0)  # 让出事件循环即可，输出类失败无需退避
                    continue

            raise LLMBudgetExhausted(final_class, attempts, self._budget.elapsed(), notes)
        finally:
            # 每条终止路径（成功 return / 预算耗尽 raise / 流式已提交上抛）：
            # call_final 终态行 + 失败尝试统计（attempt_log 只含失败项）。
            self._log("call_final", success=success, attempts=attempts,
                      budget_calls=self._budget.calls_used,
                      elapsed_s=round(time.monotonic() - run_started, 1),
                      final_class=final_class.error_class.value)
            for entry in self.attempt_log:
                _record_stat(self._task_tag, entry["candidate"], entry["class"])
