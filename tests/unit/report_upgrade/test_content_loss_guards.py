# -*- coding: utf-8 -*-
"""Regression tests for report-upgrade content-loss bugs found in ses_c0d6cd9f.

F1: patch_data must reject a parse-"successful" but degenerate patch (like
    '...') that would overwrite a full chapter with scraps.
F1b: rewrite() must not swap a full chapter for scraps either.
F2: the defense loop must rewrite failed chapters from cached write material
    instead of leaving 37-char placeholders in a delivered report.

Engine migration (Task 14): the F1/F1b acceptance rules live in the retry
engine's parse hooks (_rewrite_parse_with_outcome / _patch_parse_with_outcome).
Degenerate output is now classified so the engine retries with mutations;
budget exhaustion keeps the original chapter — the public contract ("last
known good wins") is unchanged, expressed through the engine path.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass

_CALL_LLM_EX_PATH = "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex"


def _exhausted() -> LLMBudgetExhausted:
    return LLMBudgetExhausted(
        Classification(LLMErrorClass.DEGENERATE, detail="degenerate"),
        attempts=5, elapsed=123.0, profile_notes=["mimo:3x degen"],
    )


def _chapter(content: str, status: str = "ready", chapter_id: str = "section_8") -> ChapterWriteOutput:
    return ChapterWriteOutput(
        chapter_id=chapter_id,
        title="进口贸易政策",
        content=content,
        sub_section_id="",
        key_conclusions=[],
        self_check_passed=True,
        self_check_issues=[],
        status=status,
        error="",
    )


class TestPatchDataDegenerateGuard(unittest.TestCase):
    """F1: degenerate-but-parseable patches must not destroy chapters.

    The acceptance rule lives in the engine parse hook; the engine retries
    with mutations and budget exhaustion preserves the original chapter.
    """

    def _writer(self) -> ChapterWriter:
        writer = ChapterWriter(use_streaming=False)
        writer._prompts = MagicMock()
        writer._prompts.get.return_value = "prompt"
        return writer

    def test_degenerate_patch_is_rejected(self):
        # A degenerate patch is classified by the parse hook, the engine
        # retries, and exhaustion keeps the original chapter (identity).
        writer = self._writer()
        chapter = _chapter("正文" * 10000)  # 20000 chars of real content
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()) as mock_ex:
            result = asyncio.run(writer.patch_data(
                chapter=chapter, patch_instructions=["修复数据"], framework_config={},
            ))
        mock_ex.assert_awaited_once()
        self.assertIs(result, chapter)
        self.assertEqual(len(result.content), len(chapter.content))

    def test_reasonable_patch_is_accepted(self):
        writer = self._writer()
        patched_body = "补丁正文。" * 300  # 1500 chars >= max(200, 600//3)
        good_raw = '{"status": "ready", "content": "' + patched_body + '"}'
        chapter = _chapter("正文" * 300)  # 600 chars -> floor max(200, 200)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   return_value=good_raw) as mock_ex:
            result = asyncio.run(writer.patch_data(
                chapter=chapter, patch_instructions=["修复数据"], framework_config={},
            ))
        mock_ex.assert_awaited_once()
        self.assertNotIsInstance(result, type(None))
        self.assertEqual(result.content, patched_body)

    def test_failed_patch_still_keeps_original(self):
        # A failed/unparsable patch is retried by the engine; exhaustion
        # keeps the original chapter (repair attempt, not replacement).
        writer = self._writer()
        chapter = _chapter("正文" * 1000)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()):
            result = asyncio.run(writer.patch_data(
                chapter=chapter, patch_instructions=["修复"], framework_config={},
            ))
        self.assertIs(result, chapter)
        self.assertEqual(len(result.content), len(chapter.content))


class TestRescueFailedChapters(unittest.TestCase):
    """F2: defense loop rescue rewrite for failed chapters with material."""

    def _orchestrator(self) -> ReportOrchestrator:
        writer = MagicMock()
        orchestrator = ReportOrchestrator(
            chapter_writer=writer,
            chapter_reviewer=MagicMock(),
            global_reviewer=MagicMock(),
        )
        orchestrator._report_progress = MagicMock()
        return orchestrator

    def test_failed_chapter_is_rescued_from_cache(self):
        orchestrator = self._orchestrator()
        failed = _chapter("本章节未生成可验证内容。", status="failed", chapter_id="section_5")
        failed.title = "政策效果评估"
        orchestrator._chapter_rescue_cache["section_5"] = {
            "section_spec": {"section_id": "section_5", "section_name": "政策效果评估"},
            "chapter_data": {"content": "政策效果原始素材" * 100},
            "base_content": "政策效果原始素材" * 100,
            "upstream_data_points": None,
            "raw_data_summary": "无",
        }
        rewritten = _chapter("重写后的政策效果评估。" * 100, chapter_id="section_5")
        rewritten.title = "政策效果评估"
        orchestrator._chapter_writer.write = AsyncMock(return_value=rewritten)

        chapters, rescued = asyncio.run(orchestrator._rescue_failed_chapters(
            [failed], {"output_format": "docx"}, {"name": "测试框架"},
        ))
        self.assertEqual(len(rescued), 1)
        self.assertEqual(rescued[0]["chapter_id"], "section_5")
        self.assertEqual(chapters[0].status, "ready")

    def test_ready_chapter_is_untouched(self):
        orchestrator = self._orchestrator()
        good = _chapter("正常章节内容。" * 50)
        orchestrator._chapter_writer.write = AsyncMock()
        chapters, rescued = asyncio.run(orchestrator._rescue_failed_chapters(
            [good], {}, {},
        ))
        self.assertEqual(rescued, [])
        orchestrator._chapter_writer.write.assert_not_called()

    def test_rescue_without_material_keeps_failed_chapter(self):
        orchestrator = self._orchestrator()
        failed = _chapter("本章节未生成可验证内容。", status="failed", chapter_id="section_6")
        orchestrator._chapter_writer.write = AsyncMock()
        chapters, rescued = asyncio.run(orchestrator._rescue_failed_chapters(
            [failed], {}, {},
        ))
        self.assertEqual(rescued, [])
        orchestrator._chapter_writer.write.assert_not_called()

    def test_unusable_rescue_output_is_rejected(self):
        orchestrator = self._orchestrator()
        failed = _chapter("本章节未生成可验证内容。", status="failed", chapter_id="section_5")
        orchestrator._chapter_rescue_cache["section_5"] = {
            "section_spec": {"section_id": "section_5"},
            "chapter_data": {"content": "素材"},
            "base_content": "素材",
            "upstream_data_points": None,
            "raw_data_summary": "无",
        }
        still_bad = _chapter("...", status="failed", chapter_id="section_5")
        orchestrator._chapter_writer.write = AsyncMock(return_value=still_bad)
        chapters, rescued = asyncio.run(orchestrator._rescue_failed_chapters(
            [failed], {}, {},
        ))
        self.assertEqual(rescued, [])
        self.assertEqual(chapters[0].status, "failed")


class TestRewriteDegenerateGuard(unittest.TestCase):
    """rewrite() must not swap a full chapter for parse-"successful" scraps.

    Engine-migrated: a degenerate rewrite is classified by the parse hook,
    the engine retries with mutations, and budget exhaustion preserves the
    original chapter object (identity contract, F1b).
    """

    def _writer(self) -> ChapterWriter:
        writer = ChapterWriter(use_streaming=False)
        writer._prompts = MagicMock()
        writer._prompts.get.return_value = "prompt"
        return writer

    def test_degenerate_rewrite_is_rejected(self):
        writer = self._writer()
        original = _chapter("正文" * 10000)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()):
            result = asyncio.run(writer.rewrite(
                original_chapter=original,
                review_feedback=MagicMock(issues=[]),
                framework_config={}, chapter_spec={},
                preceding_summary="",
            ))
        self.assertIs(result, original)

    def test_degenerate_rewrite_on_micro_chapter_keeps_original(self):
        # F1b floor now applies to micro chapters too: a rewrite below 50
        # chars is classified degenerate; the engine retries and exhaustion
        # preserves the original chapter (was: scraps returned verbatim).
        writer = self._writer()
        original = _chapter("短文")
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_exhausted()):
            result = asyncio.run(writer.rewrite(
                original_chapter=original,
                review_feedback=MagicMock(issues=[]),
                framework_config={}, chapter_spec={},
                preceding_summary="",
            ))
        self.assertIs(result, original)


class TestLooksLikeFailedChapter(unittest.TestCase):
    """Depth defense: degenerate '...' ready output must be flagged too."""

    def test_dots_only_ready_content_is_flagged(self):
        chapter = _chapter("...", status="ready")
        self.assertTrue(ReportOrchestrator._looks_like_failed_chapter(chapter))

    def test_normal_ready_content_is_not_flagged(self):
        chapter = _chapter("正常章节内容。" * 50)
        self.assertFalse(ReportOrchestrator._looks_like_failed_chapter(chapter))


class TestCleanKeyFindings(unittest.TestCase):
    """F4: markdown table fragments must not appear in key findings."""

    def test_table_rows_filtered(self):
        raw = "核心结论\n| 数据 | 来源章节 |\n|---|---|\n粮食产量连续创新高达到新水平\n- 某条发现内容足够长"
        cleaned = ReportOrchestrator._clean_key_findings(raw)
        self.assertFalse(any(line.startswith("|") or line.endswith("|") for line in cleaned))
        self.assertTrue(any("连续创新高" in line for line in cleaned))

    def test_leading_dash_bullet_marker_is_stripped(self):
        """F4 (format standard): '- ' list markers must not leak into findings
        (ses_92c64980: findings rendered as '2. - 全球AI核心市场...')."""
        raw = "核心结论\n- 全球AI核心市场规模2026年达到3759.3亿美元\n• 中国AI核心产业规模2025年底突破1.2万亿元人民币"
        cleaned = ReportOrchestrator._clean_key_findings(raw)
        self.assertTrue(cleaned, "should keep the finding lines")
        for line in cleaned:
            self.assertFalse(line.startswith(("-", "•", "*", "· ")), f"bullet leaked: {line!r}")
        self.assertTrue(any(line.startswith("全球AI核心市场规模") for line in cleaned))
        self.assertTrue(any(line.startswith("中国AI核心产业规模") for line in cleaned))

    def test_dash_only_lines_still_filtered(self):
        raw = "核心结论\n-\n- 另一条足够长的发现内容保持原样"
        cleaned = ReportOrchestrator._clean_key_findings(raw)
        self.assertTrue(any(line.startswith("另一条") for line in cleaned))
        self.assertFalse(any(line == "-" for line in cleaned))


if __name__ == "__main__":
    unittest.main()