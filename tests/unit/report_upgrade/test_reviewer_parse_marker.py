# -*- coding: utf-8 -*-
"""Task 8: ChapterReviewer parse-failed 标记 + 迁移到 call_llm_ex 重试引擎。

行为契约：
- ChapterReviewOutput.parse_failed: reviewer 输出不可解析标记（驱动编排层
  rewrite 门控 —— 区分"章节真的很差"与"评审输出无法解析"）。
- review(): 单次 call_llm_ex（output_contract=chapter_delimiter、
  expected_output_chars=1500、Budget(max_calls=3, max_seconds=240)、
  task_tag=reviewer:<section_id>）。
- 非 JSON 输出 → parse_failed=True（passed=False, score=0.0 不变）。
- 预算耗尽 → 返回 parse_failed=True 结果，不再 raise。
- 编排层质量环：parse_failed 轮次必须跳过 rewrite()，且轮次照常计入
  MAX_REVIEW_RETRIES（持续失败的评审不能无限循环）。
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
from src.agents.fixed_agents.report_upgrade.chapter_writer import DELIMITER_OUTPUT_CONTRACT
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterReviewInput,
    ChapterReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass, ParseOutcome

_CALL_LLM_EX_PATH = "src.agents.fixed_agents.report_upgrade.chapter_reviewer.call_llm_ex"

_GOOD_RAW = '```json\n{"passed": true, "score": 85, "issues": []}\n```'
_BAD_RAW = "不是JSON的输出"

_DELIMITER_RAW = (
    "<<<CHAPTER_REVIEW>>>\n"
    "PASSED: false\n"
    "SCORE: 62\n"
    "<<<ISSUES>>>\n"
    "- CRITICAL | p:3 | 断言'行业竞争激烈'但无竞争格局数据支撑 | 补充竞争格局数据\n"
    "- HIGH | p:5 | 引用数值与前文不一致 | 统一为可用数据中的正确值\n"
    "<<<END_CHAPTER_REVIEW>>>\n"
)


def _reviewer():
    return ChapterReviewAgent(prompt_manager=MagicMock(
        get=MagicMock(return_value="review prompt")))


def _review_input(**overrides):
    defaults = dict(
        framework_config={"name": "行业研究"},
        chapter_spec={"section_id": "ch1", "section_name": "市场规模",
                      "section_role": "analysis"},
        chapter_content="市场规模达到2000亿元",
        preceding_summary="前文摘要",
        used_metrics_summary="暂无",
        topic="新能源汽车",
    )
    defaults.update(overrides)
    return ChapterReviewInput(**defaults)


class TestParseFailedMarker:
    def test_model_default_is_false(self):
        assert ChapterReviewOutput(passed=True, score=90.0).parse_failed is False

    def test_parse_with_outcome_valid_json_ok(self):
        reviewer = _reviewer()
        outcome = reviewer._parse_with_outcome(_GOOD_RAW)
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterReviewOutput)
        assert outcome.value.passed is True
        assert outcome.value.parse_failed is False

    def test_parse_with_outcome_non_json_rejected(self):
        reviewer = _reviewer()
        outcome = reviewer._parse_with_outcome(_BAD_RAW)
        assert outcome.ok is False
        assert outcome.failure_kind == "no_json"

    def test_parse_output_failure_sets_marker(self):
        reviewer = _reviewer()
        result = reviewer._parse_output(_BAD_RAW)
        assert result.passed is False
        assert result.score == 0.0
        assert result.parse_failed is True


class TestReviewRoutesThroughEngine:
    def test_non_json_llm_output_yields_parse_failed_review(self):
        reviewer = _reviewer()
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock) as mock_ex:
            mock_ex.return_value = _BAD_RAW
            result = asyncio.run(reviewer.review(_review_input()))

        assert isinstance(result, ChapterReviewOutput)
        assert result.parse_failed is True
        assert result.passed is False
        assert result.score == 0.0

    def test_valid_json_yields_clean_review(self):
        reviewer = _reviewer()
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock) as mock_ex:
            mock_ex.return_value = _GOOD_RAW
            result = asyncio.run(reviewer.review(_review_input()))

        assert result.parse_failed is False
        assert result.passed is True
        assert result.score == 85.0

    def test_engine_contract(self):
        reviewer = _reviewer()
        captured = {}

        def fake_ex(prompt_builder, **kwargs):
            captured.update(kwargs)
            return reviewer._parse_with_outcome(_GOOD_RAW).value

        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=fake_ex) as mock_ex:
            result = asyncio.run(reviewer.review(_review_input()))

        mock_ex.assert_awaited_once()
        assert result.passed is True
        assert captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert captured["expected_output_chars"] == 1500
        assert captured["task_tag"] == "reviewer:ch1"
        assert callable(captured["parse"])
        budget = captured["budget"]
        assert budget.max_calls == 3
        assert budget.max_seconds == 240


class TestReviewBudgetExhausted:
    def test_exhaustion_returns_parse_failed_without_raise(self):
        reviewer = _reviewer()
        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.BAD_JSON_FORMAT, detail="parse_outcome:no_json"),
            attempts=3, elapsed=250.0, profile_notes=["mimo:3x no_json"],
        )
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=exhausted) as mock_ex:
            result = asyncio.run(reviewer.review(_review_input()))

        mock_ex.assert_awaited_once()
        assert isinstance(result, ChapterReviewOutput)
        assert result.parse_failed is True
        assert result.passed is False
        assert result.score == 0.0


class TestReviewDelimiterContract:
    def test_delimiter_raw_maps_fields(self):
        reviewer = _reviewer()
        output = reviewer._parse_review_delimiter(_DELIMITER_RAW)
        assert output is not None
        assert output.parse_failed is False
        assert output.passed is False
        assert output.score == 62.0
        assert len(output.issues) == 2
        first = output.issues[0]
        assert first.severity == "CRITICAL"
        assert first.location == "p:3"
        assert "竞争格局" in first.description
        assert "补充" in first.suggestion
        second = output.issues[1]
        assert second.severity == "HIGH"
        assert second.location == "p:5"

    def test_delimiter_no_issues_maps_empty(self):
        raw = (
            "<<<CHAPTER_REVIEW>>>\n"
            "PASSED: true\n"
            "SCORE: 90\n"
            "<<<ISSUES>>>\n"
            "<<<END_CHAPTER_REVIEW>>>\n"
        )
        output = _reviewer()._parse_review_delimiter(raw)
        assert output is not None
        assert output.parse_failed is False
        assert output.passed is True
        assert output.score == 90.0
        assert output.issues == []

    def test_delimiter_marker_absent_returns_none_and_json_still_works(self):
        reviewer = _reviewer()
        assert reviewer._parse_review_delimiter(_GOOD_RAW) is None
        outcome = reviewer._parse_with_outcome(_GOOD_RAW)
        assert outcome.ok is True
        assert outcome.value.score == 85.0

    def test_parse_hook_prefers_delimiter_over_json(self):
        reviewer = _reviewer()
        outcome = reviewer._parse_with_outcome(_DELIMITER_RAW)
        assert outcome.ok is True
        assert outcome.value.score == 62.0
        assert outcome.value.passed is False

    def test_marker_present_but_fields_garbage_is_parse_failed(self):
        raw = "<<<CHAPTER_REVIEW>>>\n完全乱码没有字段\n<<<END_CHAPTER_REVIEW>>>"
        output = _reviewer()._parse_review_delimiter(raw)
        assert output is not None
        assert output.parse_failed is True
        assert output.passed is False
        assert output.score == 0.0

    def test_malformed_issue_lines_skipped(self):
        raw = (
            "<<<CHAPTER_REVIEW>>>\n"
            "PASSED: true\n"
            "SCORE: 88\n"
            "<<<ISSUES>>>\n"
            "没有竖线的垃圾行\n"
            "- MEDIUM | p:2 | 描述不够具体 | 补充具体位置与建议\n"
            "<<<END_CHAPTER_REVIEW>>>\n"
        )
        output = _reviewer()._parse_review_delimiter(raw)
        assert len(output.issues) == 1
        assert output.issues[0].severity == "MEDIUM"

    def test_total_garbage_rejected_by_hook(self):
        reviewer = _reviewer()
        outcome = reviewer._parse_with_outcome(_BAD_RAW)
        assert outcome.ok is False
        assert outcome.failure_kind == "no_json"
        assert reviewer._parse_output(_BAD_RAW).parse_failed is True


class TestOrchestratorSkipsRewriteOnParseFailed:
    def _orch(self):
        orchestrator = ReportOrchestrator(
            chapter_writer=MagicMock(), chapter_reviewer=MagicMock(),
            global_reviewer=MagicMock(),
        )
        orchestrator._report_progress = MagicMock()
        return orchestrator

    def _ready_chapter(self):
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
        return ChapterWriteOutput(
            chapter_id="s1", title="T", content="正文" * 200, sub_section_id="",
            key_conclusions=[], self_check_passed=True, self_check_issues=[],
            status="ready", error="")

    def _write_kwargs(self):
        return dict(
            section_spec={"section_id": "s1", "section_name": "市场规模"},
            section_id="s1",
            task_structure={"topic": "t"},
            framework_config={"name": "f"},
            chapter_data={"content": "素材" * 50},
            preceding_summary="",
            raw_data_summary="无",
        )

    def test_parse_failed_review_round_never_calls_rewrite(self):
        orchestrator = self._orch()
        orchestrator._chapter_writer.write = AsyncMock(return_value=self._ready_chapter())
        orchestrator._chapter_writer.rewrite = AsyncMock()
        orchestrator._chapter_writer.patch_data = AsyncMock()
        parse_failed_review = ChapterReviewOutput(
            passed=False, score=0.0, parse_failed=True)
        orchestrator._chapter_reviewer.review = AsyncMock(
            return_value=parse_failed_review)

        chapter = asyncio.run(orchestrator._write_section_chapter(**self._write_kwargs()))

        assert chapter.status == "ready"
        orchestrator._chapter_writer.rewrite.assert_not_awaited()
        orchestrator._chapter_writer.patch_data.assert_not_awaited()

    def test_parse_failed_rounds_still_bounded(self):
        # parse_failed 轮次照常消耗 review 轮预算：环在 MAX_REVIEW_RETRIES 内终止。
        orchestrator = self._orch()
        orchestrator._chapter_writer.write = AsyncMock(return_value=self._ready_chapter())
        orchestrator._chapter_writer.rewrite = AsyncMock()
        orchestrator._chapter_reviewer.review = AsyncMock(
            return_value=ChapterReviewOutput(passed=False, score=0.0, parse_failed=True))

        asyncio.run(orchestrator._write_section_chapter(**self._write_kwargs()))

        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        assert orchestrator._chapter_reviewer.review.await_count == RetryPolicy.MAX_REVIEW_RETRIES
