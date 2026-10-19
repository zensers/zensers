# -*- coding: utf-8 -*-
"""Task 14: ChapterWriter.rewrite()/patch_data() migration onto call_llm_ex.

- engine call contract (output_contract=chapter_delimiter, expected_output_chars
  scaled by original length, task_tag rewrite:/patch:, stream flag forwarded)
- budget exhaustion keeps the original chapter (last known good wins, F1/F1b)
- parse hooks (_rewrite_parse_with_outcome / _patch_parse_with_outcome)
  classify the F1/F1b degenerate-replacement rule
- prompt builders prepend the no-reasoning note on strip_reasoning variations
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
    ChapterWriteOutput,
    DataPoint,
)
from src.core.llm_retry import (
    Classification,
    LLMBudgetExhausted,
    LLMErrorClass,
    RetryVariations,
)

_CALL_LLM_EX_PATH = "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex"


def _writer():
    writer = ChapterWriter(use_streaming=False)
    writer._prompts = MagicMock()
    writer._prompts.get.return_value = "prompt"
    return writer


def _chapter(content, chapter_id="ch1"):
    return ChapterWriteOutput(
        chapter_id=chapter_id, title="市场规模", content=content,
        sub_section_id="", key_conclusions=[], self_check_passed=True,
        self_check_issues=[],
    )


def _exhausted():
    return LLMBudgetExhausted(
        Classification(LLMErrorClass.DEGENERATE, detail="degenerate"),
        attempts=5, elapsed=123.0, profile_notes=["mimo:3x degen"],
    )


class TestRewriteUsesEngine:
    def test_rewrite_success_passthrough(self):
        writer = _writer()
        spec = {"section_id": "ch1", "section_name": "市场规模"}
        original = _chapter("正文" * 300)  # 600 chars
        good_raw = json.dumps({
            "status": "ready", "content": "重写正文" * 140,
            "data_points_used": [{"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"}],
        }, ensure_ascii=False)
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return writer._rewrite_parse_with_outcome(good_raw, spec, 600).value

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=fake_ex) as mock_ex:
            result = asyncio.run(writer.rewrite(
                original_chapter=original,
                review_feedback=MagicMock(issues=[]),
                framework_config={}, chapter_spec=spec, preceding_summary="",
            ))

        mock_ex.assert_awaited_once()
        assert isinstance(result, ChapterWriteOutput)
        assert result.status == "ready"
        assert len(result.content) == 4 * 140
        assert captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert captured["task_tag"] == "rewrite:ch1"
        assert captured["expected_output_chars"] == 2000  # max(2000, 600)
        assert captured["stream"] is False

    def test_rewrite_expected_chars_scale_with_original(self):
        writer = _writer()
        spec = {"section_id": "ch1", "section_name": "市场规模"}
        original = _chapter("正文" * 1500)  # 3000 chars
        good_raw = '{"status": "ready", "content": "' + "重写正文" * 400 + '"}'
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return writer._rewrite_parse_with_outcome(good_raw, spec, 3000).value

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake_ex):
            asyncio.run(writer.rewrite(
                original_chapter=original,
                review_feedback=MagicMock(issues=[]),
                framework_config={}, chapter_spec=spec, preceding_summary="",
            ))

        assert captured["expected_output_chars"] == 3000

    def test_rewrite_budget_exhaustion_returns_original_identity(self):
        writer = _writer()
        original = _chapter("正文" * 300)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()) as mock_ex:
            result = asyncio.run(writer.rewrite(
                original_chapter=original,
                review_feedback=MagicMock(issues=[]),
                framework_config={}, chapter_spec={}, preceding_summary="",
            ))

        mock_ex.assert_awaited_once()
        assert result is original


class TestPatchDataUsesEngine:
    def test_patch_success_merges_data_points(self):
        writer = _writer()
        chapter = _chapter("正文" * 300)
        chapter.data_points_used = [DataPoint(
            metric="市场规模", value="2000", unit="亿元", source="来源",
            chapter_id="ch1", source_url="https://example.test/market",
            evidence_id="ev-1", evidence_status="verified",
        )]
        patched_raw = json.dumps({
            "title": "市场规模", "content": "修补后正文" * 50,
            "data_points_used": [{
                "metric": "市场规模", "value": "2500", "unit": "亿元", "source": "",
            }],
            "key_conclusions": [], "self_check_passed": True, "self_check_issues": [],
        }, ensure_ascii=False)
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return patched_raw  # raw string: patch_data converts via _parse_output

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=fake_ex) as mock_ex:
            result = asyncio.run(writer.patch_data(
                chapter=chapter, patch_instructions=["更新市场规模"],
                framework_config={},
            ))

        mock_ex.assert_awaited_once()
        assert captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert captured["task_tag"] == "patch:ch1"
        assert captured["expected_output_chars"] == 2000  # max(2000, 600)
        # patched value came through...
        assert result.content == "修补后正文" * 50
        assert result.data_points_used[0].value == "2500"
        # ...and evidence identity was merged back from the original chapter.
        assert result.data_points_used[0].source == "来源"
        assert result.data_points_used[0].source_url == "https://example.test/market"
        assert result.data_points_used[0].evidence_id == "ev-1"
        assert result.data_points_used[0].evidence_status == "verified"

    def test_patch_budget_exhaustion_returns_original_identity(self):
        writer = _writer()
        chapter = _chapter("正文" * 300)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()) as mock_ex:
            result = asyncio.run(writer.patch_data(
                chapter=chapter, patch_instructions=["修复"], framework_config={},
            ))

        mock_ex.assert_awaited_once()
        assert result is chapter


class TestRewriteParseHookDegenerateRule:
    """F1b acceptance rule expressed as parse-hook classification."""

    def test_rewrite_of_20k_original_with_1k_rewrite_is_degenerate(self):
        writer = _writer()
        raw = '{"status": "ready", "content": "' + "段" * 500 + '"}'  # 1000 chars
        outcome = writer._rewrite_parse_with_outcome(
            raw, {"section_id": "ch1", "section_name": "n"}, original_len=20000)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_rewrite_meeting_third_floor_is_ok(self):
        writer = _writer()
        # 20000 // 3 = 6666 -> a 6700-char rewrite is accepted.
        raw = json.dumps({
            "status": "ready", "content": "段" * 6700,
            "data_points_used": [
                {"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"},
                {"metric": "增速", "value": "12", "unit": "%", "source": "IDC"},
            ],
        }, ensure_ascii=False)
        outcome = writer._rewrite_parse_with_outcome(
            raw, {"section_id": "ch1", "section_name": "n"}, original_len=20000)
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterWriteOutput)

    def test_micro_rewrite_below_50_floor_is_degenerate(self):
        writer = _writer()
        raw = '{"status": "ready", "content": "短"}'
        outcome = writer._rewrite_parse_with_outcome(
            raw, {"section_id": "ch1", "section_name": "n"}, original_len=2)
        assert outcome.ok is False and outcome.failure_kind == "degenerate"

    def test_micro_rewrite_meeting_floor_is_ok(self):
        writer = _writer()
        raw = '{"status": "ready", "content": "' + "正文" * 30 + '"}'  # 60 chars
        outcome = writer._rewrite_parse_with_outcome(
            raw, {"section_id": "ch1", "section_name": "n"}, original_len=2)
        assert outcome.ok is True

    def test_patch_hook_shares_the_acceptance_rule(self):
        writer = _writer()
        raw = '{"status": "ready", "content": "' + "段" * 500 + '"}'
        outcome = writer._patch_parse_with_outcome(
            raw, {"section_id": "ch1", "section_name": "n"}, original_len=20000)
        assert outcome.ok is False and outcome.failure_kind == "degenerate"


class TestPromptNoReasoningNote:
    _NOTE = "直接输出正式章节内容，不要输出任何思考过程。\n"

    def test_rewrite_prompt_prepends_note_on_strip_reasoning(self):
        writer = _writer()
        spec = {"section_id": "ch1", "section_name": "市场规模"}
        base = writer._build_rewrite_prompt(
            _chapter("旧正文"), MagicMock(issues=[]), spec,
            RetryVariations(), "", None)
        assert self._NOTE not in base
        stripped = writer._build_rewrite_prompt(
            _chapter("旧正文"), MagicMock(issues=[]), spec,
            RetryVariations(strip_reasoning=True), "", None)
        assert stripped == self._NOTE + base

    def test_patch_prompt_prepends_note_on_strip_reasoning(self):
        writer = _writer()
        base = writer._build_patch_prompt(
            _chapter("旧正文"), ["修复数据"], {}, RetryVariations())
        assert self._NOTE not in base
        stripped = writer._build_patch_prompt(
            _chapter("旧正文"), ["修复数据"], {},
            RetryVariations(strip_reasoning=True))
        assert stripped == self._NOTE + base
