# tests/unit/core/test_llm_retry_engine.py
# -*- coding: utf-8 -*-
import asyncio
import pytest
from src.core.llm_retry import (
    Budget, CandidateDesc, LLMBudgetExhausted, LLMErrorClass, LLMStreamCommitted,
    ParseOutcome, RetryEngine,
)

CANDS = [
    CandidateDesc(name="mimo", model="mimo-v2.6-flash", fallback_model="mimo-v2.5",
                  max_context_tokens=131072),
    CandidateDesc(name="deepseek", model="deepseek-v4-flash", fallback_model="deepseek-v4-flash",
                  max_context_tokens=128000),
]


class ScriptedTransport:
    """Callable returning queued values; values may be Exception (raise) or str."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def __call__(self, candidate, **kwargs):
        self.calls.append((candidate.name, kwargs))
        value = self.script.pop(0)
        if isinstance(value, Exception):
            raise value
        await asyncio.sleep(0)
        return value


def _engine(transport, parse=None, budget=None, candidates=None, **kw):
    return RetryEngine(
        transport=transport,
        candidates=lambda: (candidates if candidates is not None else CANDS),
        parse=parse,
        budget=budget or Budget(max_calls=10, max_seconds=60),
        **kw,
    )


class TestEngineScripts:
    def test_first_try_success(self):
        t = ScriptedTransport(['{"ok": 1}'])
        result = asyncio.run(_engine(t, parse=lambda r: ParseOutcome(True, value=r)).run(
            prompt_builder=lambda v: "P", output_contract="json"))
        assert result == '{"ok": 1}'
        assert len(t.calls) == 1

    def test_rate_limit_retries_then_success(self):
        t = ScriptedTransport([RuntimeError("429 too many requests"), "GOOD"])
        result = asyncio.run(_engine(t).run(prompt_builder=lambda v: "P"))
        assert result == "GOOD"
        assert len(t.calls) == 2

    def test_degenerate_escalates_to_fallback_model_then_next_profile(self):
        t = ScriptedTransport(["...", "...", "...", "GOOD"])
        models = []

        async def transport(candidate, **kw):
            models.append((candidate.name, kw.get("model")))
            return await t(candidate, **kw)

        result = asyncio.run(_engine(transport).run(prompt_builder=lambda v: "P"))
        assert result == "GOOD"
        # attempt1 mimo base -> degen; attempt2 mimo strict_json+0.1 -> degen;
        # attempt3 mimo fallback_model -> degen (ladder exhausted) -> ban;
        # attempt4 deepseek base -> ok
        assert models[0] == ("mimo", "mimo-v2.6-flash")
        assert models[1][0] == "mimo" and t.calls[1][1]["temperature"] == pytest.approx(0.1)
        assert models[2] == ("mimo", "mimo-v2.5")
        assert models[3][0] == "deepseek"

    def test_auth_bans_profile_immediately(self):
        t = ScriptedTransport([RuntimeError("401 unauthorized"), "OK"])
        result = asyncio.run(_engine(t).run(prompt_builder=lambda v: "P"))
        assert result == "OK"
        assert t.calls[0][0] == "mimo" and t.calls[1][0] == "deepseek"
        # banned: only 1 attempt consumed on mimo (terminal instruction, not a retry)
        assert len(t.calls) == 2

    def test_budget_exhaustion_raises_with_payload(self):
        t = ScriptedTransport(["...", "...", "...", "...", "..."])
        with pytest.raises(LLMBudgetExhausted) as ei:
            asyncio.run(_engine(t, budget=Budget(max_calls=4, max_seconds=60)).run(
                prompt_builder=lambda v: "P"))
        assert ei.value.classification.error_class == LLMErrorClass.DEGENERATE
        assert ei.value.attempts == 4

    def test_max_tokens_factor_applied(self):
        captured = {}

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            captured["max_tokens"] = max_tokens
            if max_tokens == 1000:
                return "TRUNCATED"
            return "FINE"

        outcomes = [ParseOutcome(False, "truncated"), ParseOutcome(True, value="FINE")]

        def parse(raw):
            return outcomes.pop(0)

        eng = RetryEngine(
            transport=transport, candidates=lambda: CANDS[:1], parse=parse,
            budget=Budget(max_calls=5, max_seconds=60), base_max_tokens=1000)
        result = asyncio.run(eng.run(prompt_builder=lambda v: "P"))
        assert result == "FINE"
        assert captured["max_tokens"] == pytest.approx(1500)

    def test_strict_json_prefix_reaches_prompt_builder(self):
        seen = []

        def builder(variations):
            seen.append(variations)
            return "P"

        t = ScriptedTransport(["...", "GOOD"])
        asyncio.run(_engine(t).run(prompt_builder=builder))
        # builder 每次尝试都会被调用，第 1 次是无变异 base；strict_json rung
        # 在第 2 次调用上（阶梯索引契约：rung0 落在第 2 次传输调用）
        assert seen[1].strict_json_prefix is True
        assert seen[1].temperature == pytest.approx(0.1)

    def test_shape_check_no_parse_degenerate_then_success(self):
        t = ScriptedTransport(["...", "GOOD"])
        result = asyncio.run(_engine(t).run(prompt_builder=lambda v: "P"))
        assert result == "GOOD"

    def test_attempt_log_records_mutations(self):
        t = ScriptedTransport(["...", "GOOD"])
        eng = _engine(t)
        asyncio.run(eng.run(prompt_builder=lambda v: "P"))
        assert any(e["class"] == "degenerate" for e in eng.attempt_log)
        assert all({"class", "attempt", "mutation", "candidate"} <= set(e) for e in eng.attempt_log)

    def test_ban_is_instance_not_global(self):
        t1 = ScriptedTransport(["...", "...", "...", "GOOD"])
        eng1 = _engine(t1)
        asyncio.run(eng1.run(prompt_builder=lambda v: "P"))
        eng2 = _engine(ScriptedTransport(["GOOD"]))
        result = asyncio.run(eng2.run(prompt_builder=lambda v: "P"))
        assert result == "GOOD"  # fresh engine sees mimo again

    def test_context_overflow_advances_to_next_candidate(self):
        t = ScriptedTransport([
            RuntimeError("This model's maximum context length is 131072 tokens"),
            "GOOD",
        ])
        result = asyncio.run(_engine(t).run(prompt_builder=lambda v: "P"))
        assert result == "GOOD"
        assert t.calls[0][0] == "mimo" and t.calls[1][0] == "deepseek"

    def test_candidates_exhausted_raises_without_budget_trip(self):
        t = ScriptedTransport(["...", "...", "..."])
        with pytest.raises(LLMBudgetExhausted) as ei:
            asyncio.run(_engine(t, candidates=CANDS[:1]).run(
                prompt_builder=lambda v: "P"))
        assert ei.value.attempts == 3
        assert ei.value.classification.error_class == LLMErrorClass.DEGENERATE

    def test_switch_model_without_fallback_advances_candidate(self):
        no_fallback = CandidateDesc(name="nofb", model="ma", fallback_model="")
        t = ScriptedTransport(["...", "...", "GOOD"])
        result = asyncio.run(_engine(t, candidates=[no_fallback, CANDS[1]]).run(
            prompt_builder=lambda v: "P"))
        assert result == "GOOD"
        # rung0 strict_json 在 nofb 上真实变异重试一次；rung1 switch_model 因
        # fallback 为空无法改变参数 → 不做同参重试，直接换 deepseek
        assert [name for name, _ in t.calls] == ["nofb", "nofb", "deepseek"]

    def test_prose_contract_never_injects_strict_json_prefix(self):
        prompts = []

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            prompts.append(prompt)
            return "..." if len(prompts) == 1 else "GOOD"

        result = asyncio.run(_engine(transport).run(
            prompt_builder=lambda v: "P", output_contract="prose"))
        assert result == "GOOD"
        assert "只输出一个合法的 JSON 对象" not in prompts[-1]

    def test_json_contract_rejects_non_json_then_succeeds(self):
        prompts = []

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            prompts.append(prompt)
            return "plain prose answer, not json at all" if len(prompts) == 1 \
                else '{"ok": 1}'

        eng = _engine(transport)
        result = asyncio.run(eng.run(prompt_builder=lambda v: "P",
                                     output_contract="json"))
        assert result == '{"ok": 1}'
        assert any(e["class"] == "bad_json_format" for e in eng.attempt_log)


class TestStreamCommittedAndBanHook:
    def test_stream_committed_terminates_whole_run(self):
        calls = []

        async def transport(candidate, **kw):
            calls.append(candidate.name)
            raise LLMStreamCommitted("connection dropped after partial output")

        with pytest.raises(LLMStreamCommitted):
            asyncio.run(_engine(transport).run(prompt_builder=lambda v: "P"))
        # 立即终止：无重试、无下一候选推进（任何重试都会重复用户可见内容）
        assert calls == ["mimo"]

    def test_ban_hook_receives_banned_profile(self):
        t = ScriptedTransport([RuntimeError("401 unauthorized"), "OK"])
        banned = []
        result = asyncio.run(_engine(t, ban_hook=banned.append).run(
            prompt_builder=lambda v: "P"))
        assert result == "OK"
        assert banned == ["mimo"]
        # 实例内 ban 依然生效：mimo 未被再次尝试
        assert [name for name, _ in t.calls] == ["mimo", "deepseek"]


class TestCandidateProfileTemperature:
    """E1 契约：CandidateDesc 携带 profile 约束温度（kimi 只接受 1）。
    引擎只透传 variation 温度（base attempt 为 None）；candidate.temperature
    的解析发生在 transport 工厂（llm_client._ex_transport_factory，
    见 test_llm_client_ex.py::TestExTransportTemperature）。"""

    def test_desc_carries_profile_temperature(self):
        kimi = CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)
        assert kimi.temperature == 1
        # 缺省仍为 None：无约束候选不受影响
        assert CandidateDesc(name="mimo", model="m").temperature is None

    def test_engine_passes_variation_temperature_only(self):
        kimi = CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)
        t = ScriptedTransport(["OK"])
        asyncio.run(_engine(t, candidates=[kimi]).run(
            prompt_builder=lambda v: "P"))
        assert t.calls[0][1]["temperature"] is None

    def test_variation_temperature_beats_everything(self):
        # 显式变异温度仍是阶梯的权利（mutation ladder overrides profile）。
        # 在 kimi 这类温度锁定模型上，带显式温度的阶梯 rung 依然会 400 并推进
        # —— 这是正确行为：base attempt 现在可用，只有 base 失败时才烧阶梯。
        kimi = CandidateDesc(name="kimi", model="kimi-k2.7", temperature=1)
        t = ScriptedTransport(["...", "GOOD"])
        asyncio.run(_engine(t, candidates=[kimi]).run(
            prompt_builder=lambda v: "P"))
        # attempt1 = base (variation None)；attempt2 = DEGENERATE rung0 (0.1)
        assert t.calls[0][1]["temperature"] is None
        assert t.calls[1][1]["temperature"] == pytest.approx(0.1)
