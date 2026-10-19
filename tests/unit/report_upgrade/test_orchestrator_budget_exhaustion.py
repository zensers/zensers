# -*- coding: utf-8 -*-
"""Spec §8#9: the phase-4 chapter loop must NOT blind-retry writer.write().

Since Task 6, ChapterWriter.write() runs the failure-aware retry engine
internally (bounded, mutating) and returns either a ready chapter or a
failed chapter with error="budget_exhausted:<class>". Re-running write()
with identical input cannot change a deterministic failure, so the
orchestrator must call it exactly once per section per phase-4 pass and
converge any non-ready outcome into a visible failed chapter that the
Defense rescue path can rewrite (spec A3).
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteInput, ChapterWriteOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def _failed_chapter(section_id):
    return ChapterWriteOutput(
        chapter_id=section_id, title="T", content="", sub_section_id="",
        key_conclusions=[], self_check_passed=False, self_check_issues=[],
        status="failed", error="budget_exhausted:degenerate",
    )


def _orch():
    orchestrator = ReportOrchestrator(
        chapter_writer=MagicMock(), chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
    )
    orchestrator._report_progress = MagicMock()
    return orchestrator


def _write_kwargs(**overrides):
    kwargs = dict(
        section_spec={"section_id": "section_5", "section_name": "政策效果评估"},
        section_id="section_5",
        task_structure={"topic": "t"},
        framework_config={"name": "f"},
        chapter_data={"content": "素材" * 50},
        preceding_summary="",
        raw_data_summary="无",
    )
    kwargs.update(overrides)
    return kwargs


class TestNoBlindRewriteOfFailedWrite:
    def test_failed_write_not_retried_with_identical_input(self):
        orchestrator = _orch()
        orchestrator._chapter_writer.write = AsyncMock(return_value=_failed_chapter("section_5"))
        chapter = asyncio.run(orchestrator._write_section_chapter(**_write_kwargs()))
        orchestrator._chapter_writer.write.assert_awaited_once()
        assert chapter.status == "failed"

    def test_ready_write_passes_through(self):
        orchestrator = _orch()
        good = ChapterWriteOutput(
            chapter_id="section_5", title="T", content="正文" * 200, sub_section_id="",
            key_conclusions=[], self_check_passed=True, self_check_issues=[],
            status="ready", error="")
        orchestrator._chapter_writer.write = AsyncMock(return_value=good)
        # Single passing review so the quality loop accepts the chapter as-is.
        orchestrator._chapter_reviewer.review = AsyncMock(
            return_value=SimpleNamespace(passed=True, score=95.0, issues=[]),
        )
        chapter = asyncio.run(orchestrator._write_section_chapter(**_write_kwargs(preceding_summary="s")))
        assert chapter is good
        orchestrator._chapter_reviewer.review.assert_awaited_once()

    def test_writer_exception_becomes_failed_chapter(self):
        # 非 LLMBudgetExhausted 的意外异常也必须收敛为 failed 章节（不向上抛）
        orchestrator = _orch()
        orchestrator._chapter_writer.write = AsyncMock(side_effect=RuntimeError("boom"))
        chapter = asyncio.run(orchestrator._write_section_chapter(**_write_kwargs(
            section_spec={"section_id": "s1", "section_name": "x"},
            section_id="s1", chapter_data=None,
        )))
        assert chapter.status == "failed"
        orchestrator._chapter_writer.write.assert_awaited_once()
