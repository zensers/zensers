# -*- coding: utf-8 -*-
"""Task 6: ChapterWriter.write() 迁移到 call_llm_ex 重试引擎的行为契约。

- _parse_with_outcome: 引擎的分类钩子（no_json / truncated / degenerate / ok）
- write(): 单次 call_llm_ex（output_contract=chapter_delimiter、
  expected_output_chars 随 word_count_target 缩放、task_tag=writer:<section_id>）
- 预算耗尽: 返回 failed 章节并携带 budget_exhausted:<error_class> 错误标记，
  交给下游 defense rescue（不再有 write() 内部的盲目重试）。
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    DELIMITER_OUTPUT_CONTRACT,
    ChapterWriter,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteInput,
    ChapterWriteOutput,
)
from src.core.llm_retry import (
    Classification,
    LLMBudgetExhausted,
    LLMErrorClass,
    ParseOutcome,
    RetryVariations,
)

_CALL_LLM_EX_PATH = "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex"

# I1 起 ready 章节 JSON 需携带结构化数据点（C3 数据密度以 data_points_used
# 计数，600 字零数据点的非定性章节会被契约门判 degenerate）。
_GOOD_RAW = json.dumps({
    "status": "ready", "content": "正文" * 300,
    "data_points_used": [{"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"}],
}, ensure_ascii=False)


def _writer():
    writer = ChapterWriter(use_streaming=False)
    writer._prompts = MagicMock()
    writer._prompts.get.return_value = "prompt"
    return writer


def _input(word_count_target=None, **overrides):
    spec = {"section_id": "s1", "section_name": "测试章节", "section_role": "analysis"}
    if word_count_target is not None:
        spec["word_count_target"] = word_count_target
    defaults = dict(
        framework_config={"name": "行业研究"},
        task_structure={"topic": "新能源汽车"},
        chapter_spec=spec,
        chapter_data={"市场规模": "2000亿"},
    )
    defaults.update(overrides)
    return ChapterWriteInput(**defaults)


class TestParseWithOutcome:
    def test_good_json_ok_with_chapter_value(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(
            _GOOD_RAW, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterWriteOutput)
        assert outcome.value.status == "ready"

    def test_empty_is_no_json(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(
            "   ", {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "no_json"

    def test_no_json_prose(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(
            "no json here at all " * 10, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "no_json"

    def test_truncated_json_detected(self):
        writer = _writer()
        # JSON-shaped output whose repair only recovers a sub-threshold
        # chapter: the budget cut hit a non-content field -> truncated.
        raw = '{"content": "短", "filler_until_budget_cut": "' + "x" * 200
        outcome = writer._parse_with_outcome(
            raw, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "truncated"

    @pytest.mark.parametrize("raw", ["...", "。。。", "。"])
    def test_degenerate_exact_markers(self, raw):
        writer = _writer()
        outcome = writer._parse_with_outcome(
            raw, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "degenerate"

    def test_29_chars_is_degenerate(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(
            "a" * 29, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "degenerate"

    def test_30_char_prose_is_no_json_not_degenerate(self):
        # Boundary: the degenerate rule is len<30; a 30-char non-marker string
        # falls through to _parse_output, which cannot salvage short JSON-less
        # prose, and is bucketed as no_json instead.
        writer = _writer()
        outcome = writer._parse_with_outcome(
            "a" * 30, {"section_id": "s1", "section_name": "n"})
        assert outcome.ok is False and outcome.failure_kind == "no_json"


class TestMaterialize:
    def test_ok_outcome_returns_chapter_value(self):
        writer = _writer()
        chapter = writer._parse_with_outcome(
            _GOOD_RAW, {"section_id": "s1", "section_name": "n"}).value
        assert writer._materialize(ParseOutcome(True, value=chapter), {}) is chapter

    def test_failed_outcome_returns_failed_placeholder(self):
        writer = _writer()
        result = writer._materialize(
            ParseOutcome(False, "degenerate"), {"section_id": "s1", "section_name": "n"})
        assert result.status == "failed"


class TestWriteUsesEngine:
    def test_write_routes_through_engine_once(self):
        writer = _writer()
        spec = {"section_id": "s1", "section_name": "测试章节",
                "section_role": "analysis", "word_count_target": 2000}
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return writer._parse_with_outcome(_GOOD_RAW, spec).value

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=fake_ex) as mock_ex:
            result = asyncio.run(writer.write(_input(chapter_spec=spec)))

        assert isinstance(result, ChapterWriteOutput)
        assert result.status == "ready"
        assert mock_ex.await_count == 1
        assert captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert captured["expected_output_chars"] == 2000
        assert captured["task_tag"].startswith("writer:")


class TestWriteBudgetExhausted:
    def test_exhaustion_returns_failed_chapter(self):
        writer = _writer()
        spec = {"section_id": "s9", "section_name": "章节九",
                "word_count_target": 2000}
        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.DEGENERATE, detail="155c"),
            attempts=5, elapsed=123.0, profile_notes=["mimo:3x degen"],
        )
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=exhausted) as mock_ex:
            result = asyncio.run(writer.write(_input(chapter_spec=spec)))

        mock_ex.assert_awaited_once()
        assert result.status == "failed"
        assert "budget_exhausted:degenerate" in (result.error or "")
        assert result.content == ""


class TestWordCountTargetScaling:
    def test_21k_target_scales_expected_chars(self):
        writer = _writer()
        spec = {"section_id": "s1", "section_name": "大章节",
                "word_count_target": 21000}
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return writer._parse_with_outcome(_GOOD_RAW, spec).value

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake_ex):
            result = asyncio.run(writer.write(_input(chapter_spec=spec)))

        assert captured["expected_output_chars"] == 21000
        assert result.status == "ready"


class _EchoPrompts:
    """Prompt double that echoes the guidance kwargs into the template text."""

    def get(self, name, **kwargs):
        return "\n".join(str(v) for v in kwargs.values())


class TestBuildWritePromptToolsFlag:
    def _writer_with_echo_prompts(self):
        writer = ChapterWriter(use_streaming=False)
        writer._prompts = _EchoPrompts()
        return writer

    def test_tools_promise_only_when_bound(self, tmp_path):
        cache = tmp_path / "research_result_cache.json"
        cache.write_text("{}", encoding="utf-8")
        writer = self._writer_with_echo_prompts()
        inp = _input(raw_data_location=str(cache))

        unbound = writer._build_write_prompt(
            inp, RetryVariations(), inp.preceding_summary, tools_bound=False)
        assert "你拥有只读工具" not in unbound
        assert "read_json(filepath=" not in unbound
        assert "不存在 read_json 工具" in unbound
        assert str(cache) in unbound

        bound = writer._build_write_prompt(
            inp, RetryVariations(), inp.preceding_summary, tools_bound=True)
        assert "你拥有只读工具 `read_json`" in bound
        assert f"read_json(filepath={cache})" in bound

    def test_default_is_unbound(self, tmp_path):
        cache = tmp_path / "research_result_cache.json"
        cache.write_text("{}", encoding="utf-8")
        writer = self._writer_with_echo_prompts()
        inp = _input(raw_data_location=str(cache))
        prompt = writer._build_write_prompt(
            inp, RetryVariations(), inp.preceding_summary)
        assert "你拥有只读工具" not in prompt


class TestWriteExhaustionToolsFallback:
    """Budget exhaustion + a real raw-data cache: one legacy tools attempt."""

    def _input_with_cache(self, tmp_path, spec):
        cache = tmp_path / "research_result_cache.json"
        cache.write_text("{}", encoding="utf-8")
        return _input(chapter_spec=spec, raw_data_location=str(cache))

    def _exhausted(self):
        return LLMBudgetExhausted(
            Classification(LLMErrorClass.DEGENERATE, detail="155c"),
            attempts=5, elapsed=123.0, profile_notes=["mimo:3x degen"],
        )

    def test_exhaustion_with_cache_falls_back_to_tools_once(self, tmp_path):
        writer = _writer()
        spec = {"section_id": "s7", "section_name": "章节七",
                "word_count_target": 2000}
        inp = self._input_with_cache(tmp_path, spec)
        good_raw = '{"status": "ready", "content": "' + "工具路径补写正文。" * 30 + '"}'

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=self._exhausted()), \
             patch.object(ChapterWriter, "_call_llm_with_tools",
                          new_callable=AsyncMock) as tools_fallback:
            tools_fallback.return_value = good_raw
            result = asyncio.run(writer.write(inp))

        tools_fallback.assert_awaited_once()
        assert result.status == "ready"
        assert "工具路径补写正文。" in result.content

    def test_exhaustion_with_failing_tools_fallback_stays_failed(self, tmp_path):
        writer = _writer()
        spec = {"section_id": "s8", "section_name": "章节八",
                "word_count_target": 2000}
        inp = self._input_with_cache(tmp_path, spec)

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=self._exhausted()), \
             patch.object(ChapterWriter, "_call_llm_with_tools",
                          new_callable=AsyncMock) as tools_fallback:
            tools_fallback.return_value = "not json"
            result = asyncio.run(writer.write(inp))

        tools_fallback.assert_awaited_once()
        assert result.status == "failed"
        assert "budget_exhausted:" in (result.error or "")
