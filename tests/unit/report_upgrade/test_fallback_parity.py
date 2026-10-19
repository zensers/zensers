# -*- coding: utf-8 -*-
"""I4 兜底同验收（Fallback Parity）合同测试。

设计文档 §I4 验收标准：每个兜底路径一个"兜底产垃圾 → 判失败"的合同测试，
兜底产出必须通过与主路径完全相同的 I1 内容契约（C1-C6），绝不降格验收。

覆盖三条兜底：
1. prose salvage（chapter_writer._parse_output 抢救路径）
2. defense rescue 重写（orchestrator._rescue_failed_chapters）
3. defense patch（chapter_writer.patch_data 解析钩子）
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter

_PLACEHOLDER_FLOOD = "本章内容待补充。" * 120  # >800 chars, C5 命中


def _failed_chapter():
    return ChapterWriteOutput(
        chapter_id="section_5", title="政策效果评估", content="",
        sub_section_id="", key_conclusions=[],
        self_check_passed=False, self_check_issues=["JSON解析失败"],
        status="failed", error="JSON解析失败",
    )


class TestSalvageFallbackParity:
    """兜底1：prose salvage 产出必须过全量 I1（垃圾 → failed 占位）。"""

    def test_salvage_placeholder_garbage_judged_failed(self):
        w = ChapterWriter(use_streaming=False)
        # 无 JSON 信封、超长的"散文"——但全部是占位符文本（C5 违约）
        raw = _PLACEHOLDER_FLOOD
        out = w._parse_output(raw, {"section_id": "s9", "section_name": "市场分析"})
        assert out.status == "failed", (
            "salvage 兜底产出占位符垃圾必须判失败（I4 同验收）"
        )
        assert _PLACEHOLDER_FLOOD.strip() not in (out.content or "")

    def test_salvage_healthy_prose_still_accepted(self):
        """反回归对照：健康散文抢救不受影响（防同验收门误杀）。"""
        w = ChapterWriter(use_streaming=False)
        body = "## 产业链全景\n\n" + "章节正文分析内容。" * 150
        out = w._parse_output(body, {"section_id": "s2", "section_name": "产业链全景"})
        assert out.status == "ready"
        assert len(out.content) >= 800


def _rescue_orchestrator():
    orchestrator = ReportOrchestrator(
        chapter_writer=MagicMock(),
        chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
    )
    orchestrator._report_progress = MagicMock()
    return orchestrator


class TestRescueFallbackParity:
    """兜底2：defense rescue 产出必须过全量 I1（垃圾 → 保留原失败章节）。"""

    def test_rescue_placeholder_garbage_rejected(self):
        orchestrator = _rescue_orchestrator()
        orchestrator._chapter_rescue_cache["section_5"] = {
            "base_content": "原始素材" * 50,
            "section_spec": {"section_id": "section_5", "section_name": "政策效果评估"},
            "chapter_data": {},
            "raw_data_summary": "无",
            "upstream_data_points": [],
        }
        polluted = ChapterWriteOutput(
            chapter_id="section_5", title="政策效果评估",
            content=_PLACEHOLDER_FLOOD,
            sub_section_id="", key_conclusions=[],
            self_check_passed=True, self_check_issues=[],
            status="ready", error="",
        )
        orchestrator._chapter_writer.write = AsyncMock(return_value=polluted)

        chapters, rescued = asyncio.new_event_loop().run_until_complete(
            orchestrator._rescue_failed_chapters(
                [_failed_chapter()],
                {"topic": "中国粮食政策研究", "output_format": "docx", "sections": []},
                {"name": "通用研究报告"},
            )
        )
        assert rescued == [], "垃圾 rescue 产出不得被接受（I4 同验收）"
        assert chapters[0].status == "failed", "原失败章节保持失败状态"
        orchestrator._chapter_writer.write.assert_awaited_once()


class TestDefensePatchFallbackParity:
    """兜底3：defense patch 产出经 writer 解析钩子同验收（垃圾 → 非 ready）。"""

    def test_patch_placeholder_garbage_not_ready(self):
        w = ChapterWriter(use_streaming=False)
        delimited = (
            "<<<CHAPTER_CONTENT>>>\n" + _PLACEHOLDER_FLOOD + "\n<<<END_CHAPTER_CONTENT>>>\n"
            "<<<KEY_CONCLUSIONS>>>\n- 待补充结论一\n- 待补充结论二\n<<<END_KEY_CONCLUSIONS>>>\n"
            "<<<DATA_POINTS_USED>>>\n[]\n<<<END_DATA_POINTS_USED>>>"
        )

        async def fake_ex(prompt_builder, **kwargs):
            parse = kwargs.get("parse")
            return parse(delimited)

        with patch(
            "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex",
            fake_ex,
        ):
            original = ChapterWriteOutput(
                chapter_id="s0", title="行业概览", content="## 行业概览\n\n完整正文" * 50,
            )
            patched = asyncio.new_event_loop().run_until_complete(
                w.patch_data(
                    chapter=original, patch_instructions=["修正数据"],
                    framework_config={},
                )
            )
        assert patched is None or patched.status != "ready", (
            "patch 兜底产出占位符垃圾不得以 ready 接受（I4 同验收）"
        )


class TestToolsFallbackParity:
    """终审 P1#1：预算耗尽后 tools 最后通道同样过 I1（垃圾 → 判失败）。"""

    def test_tools_fallback_placeholder_garbage_rejected(self, tmp_path):
        w = ChapterWriter(use_streaming=False)
        raw_cache = tmp_path / "raw_data.json"
        raw_cache.write_text('{"rows": []}', encoding="utf-8")

        async def fake_tools(prompt, raw_location):
            return _PLACEHOLDER_FLOOD  # 经合法 JSON 解析会产出的"散文"

        with patch(
            "src.agents.fixed_agents.report_upgrade.chapter_writer."
            "ChapterWriter._call_llm_with_tools", fake_tools
        ):
            from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass
            from src.agents.fixed_agents.report_upgrade.chapter_writer import (
                ChapterWriteInput,
            )

            async def exhausted_first(prompt_builder, **kwargs):
                raise LLMBudgetExhausted(
                    Classification(LLMErrorClass.BAD_JSON_FORMAT, detail="t"),
                    attempts=3, elapsed=1.0)

            input_data = ChapterWriteInput(
                framework_config={}, task_structure={"topic": "T"},
                chapter_spec={"section_id": "sT", "section_name": "测试章"},
                chapter_data={}, raw_data_summary="无",
                preceding_summary="", used_metrics_summary="",
                base_content="", upstream_data_points=None,
                global_evidence_pool=[], raw_search_results=[],
                raw_data_location=str(raw_cache),
                sibling_section_summaries=[], chapter_requirements={},
                used_evidence_ids=[], output_format="docx",
            )
            with patch(
                "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex",
                exhausted_first,
            ):
                chapter = asyncio.new_event_loop().run_until_complete(
                    w.write(input_data)
                )
        assert str(chapter.status).lower() != "ready", (
            "tools 兜底产出占位符垃圾不得以 ready 进入交付物（I4）"
        )
