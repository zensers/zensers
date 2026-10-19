# -*- coding: utf-8 -*-
"""End-to-end defense-loop regression: a failed chapter with cached write
material must be rescued at the top of the repair loop and delivered.

Reproduces the production failure observed in ses_c0d6cd9f: sections 5/6
(writer-rejected JSON, status=failed) stayed as 37-char placeholders through
all three defense rounds because the loop only searched for evidence and
never rewrote the chapters.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def _failed_chapter() -> ChapterWriteOutput:
    """Production failure mode: writer returns a failed object, no exception."""
    return ChapterWriteOutput(
        chapter_id="section_5",
        title="政策效果评估",
        content="",
        sub_section_id="",
        key_conclusions=[],
        self_check_passed=False,
        self_check_issues=["JSON解析失败，输出格式不规范"],
        status="failed",
        error="JSON解析失败，输出格式不规范",
    )


def _rescued_chapter() -> ChapterWriteOutput:
    # Numeric-free prose so the defense audit has nothing to flag.
    return ChapterWriteOutput(
        chapter_id="section_5",
        title="政策效果评估",
        content="本节基于已有研究素材系统评估政策效果。" * 40,
        sub_section_id="",
        key_conclusions=["政策评估结论足够长足够长足够长"],
        self_check_passed=True,
        self_check_issues=[],
        status="ready",
        error="",
    )


def _orchestrator() -> ReportOrchestrator:
    orchestrator = ReportOrchestrator(
        chapter_writer=MagicMock(),
        chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
    )
    orchestrator._report_progress = MagicMock()
    orchestrator._call_llm_tracked = AsyncMock(return_value={
        "success": True,
        "content": "执行摘要。政策体系总体向好发展态势明确。",
    })
    return orchestrator


TASK_STRUCTURE = {"topic": "中国粮食政策研究", "output_format": "docx", "sections": []}
FRAMEWORK = {"name": "通用研究报告"}


class TestDefenseLoopRescueIntegration(unittest.TestCase):
    """The failed chapter must be rescued and the loop must deliver."""

    def test_rescue_at_loop_top_and_deliver(self):
        orchestrator = _orchestrator()
        failed = _failed_chapter()
        orchestrator._chapter_rescue_cache["section_5"] = {
            "section_spec": {"section_id": "section_5", "section_name": "政策效果评估"},
            "chapter_data": {"content": "政策效果分析素材" * 100},
            "base_content": "政策效果分析素材" * 100,
            "upstream_data_points": None,
            "raw_data_summary": "无",
        }
        orchestrator._chapter_writer.write = AsyncMock(return_value=_rescued_chapter())

        report = asyncio.run(orchestrator._run_defense_repair_loop(
            chapters=[failed],
            review=MagicMock(),
            framework_config=FRAMEWORK,
            topic="中国粮食政策研究",
            task_structure=TASK_STRUCTURE,
            original_sources=[],
            quality_report=None,
            conflicts_summary="",
            max_rounds=3,
        ))

        orchestrator._chapter_writer.write.assert_called_once()
        rescued_section = next(
            s for s in report["sections"] if s["section_id"] == "section_5"
        )
        self.assertEqual(rescued_section["status"], "ready")
        self.assertGreater(len(rescued_section["content"]), 400)
        history = report["defense_loop"]["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "passed")
        self.assertEqual(len(history[0]["rescued"]), 1)
        self.assertEqual(history[0]["rescued"][0]["chapter_id"], "section_5")

    def test_no_material_means_no_rescue_attempt(self):
        orchestrator = _orchestrator()
        failed = _failed_chapter()
        orchestrator._chapter_writer.write = AsyncMock()

        report = asyncio.run(orchestrator._run_defense_repair_loop(
            chapters=[failed],
            review=MagicMock(),
            framework_config=FRAMEWORK,
            topic="中国粮食政策研究",
            task_structure=TASK_STRUCTURE,
            original_sources=[],
            quality_report=None,
            conflicts_summary="",
            max_rounds=3,
        ))

        orchestrator._chapter_writer.write.assert_not_called()
        history = report["defense_loop"]["history"]
        self.assertEqual(history[0]["rescued"], [])


if __name__ == "__main__":
    unittest.main()