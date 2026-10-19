# -*- coding: utf-8 -*-
"""Fixed-format delimiter contract: primary chapter output contract.

Root fix for cross-provider JSON fragility (ses_d6417b3a: a coding model
produced 10.5k chars of reasoning instead of chapter JSON; long-form Chinese
inside JSON demands perfect escaping).  Contract:

- ``_parse_delimiter_format`` parses the canonical marker format (ready and
  failed statuses, optional DATAPOINTS, whitespace tolerant) and mirrors
  ``_parse_output``'s post-processing (content sanitization, manifest-owned
  title, chapter-scoped data points);
- the write/rewrite parse hooks try the delimiter contract FIRST, keep JSON
  as compatibility fallback and keep the meta-reasoning gate for raw output
  without markers;
- final assembly replaces contract-marker leakage with the failed placeholder;
- ``strict_json_prefix`` variations reinforce the marker format, never JSON.
"""
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    DELIMITER_OUTPUT_CONTRACT,
    ChapterWriter,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteInput,
    ChapterWriteOutput,
    ReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.core.llm_retry import (
    Budget,
    CandidateDesc,
    RetryEngine,
    RetryVariations,
)

_SPEC = {"section_id": "s1", "section_name": "市场规模"}

_LONG_CONTENT = (
    "## 核心结论\n2025年中国市场规模达到2000亿元，同比增长12%。\n"
    "## 论证与分析\n据IDC数据显示，出货量增长带动市场规模稳步扩大，"
    "市场集中度持续提升，头部厂商份额进一步巩固。\n"
) * 3

_DELIMITER_RAW = (
    "<<<REPORT_CHAPTER>>>\n"
    "STATUS: ready\n"
    "TITLE: 市场规模\n"
    "<<<CONTENT>>>\n"
    + _LONG_CONTENT +
    "<<<CONCLUSIONS>>>\n"
    "中国市场规模2025年达到2000亿元\n"
    "- 同比增长12%，增速较上年放缓\n"
    "<<<DATAPOINTS>>>\n"
    "市场规模|2000|亿元|IDC\n"
    "增速|12|%|IDC\n"
    "<<<END_REPORT_CHAPTER>>>\n"
)

_JSON_RAW = json.dumps({
    "status": "ready", "content": "正文" * 300,
    "data_points_used": [{"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"}],
}, ensure_ascii=False)

_META_REPAIR = (
    'The task is to repair the chapter. The main issue: quantitative claims in '
    'the body text are "unbound". Let me look at the current chapter content...'
) + ("市场规模数据需要核对后再写入正文。" * 40)

_PLACEHOLDER = "本章节未生成可验证内容。系统已记录该章节失败状态，请在补充证据后重新生成。"


def _writer():
    writer = ChapterWriter(use_streaming=False)
    writer._prompts = MagicMock()
    writer._prompts.get.return_value = "prompt"
    return writer


def _input(**overrides):
    spec = {"section_id": "s1", "section_name": "测试章节", "section_role": "analysis"}
    defaults = dict(
        framework_config={"name": "行业研究"},
        task_structure={"topic": "新能源汽车"},
        chapter_spec=spec,
        chapter_data={"市场规模": "2000亿"},
    )
    defaults.update(overrides)
    return ChapterWriteInput(**defaults)


class TestParseDelimiterFormat:
    def test_happy_path_maps_all_fields(self):
        writer = _writer()
        chapter = writer._parse_delimiter_format(_DELIMITER_RAW, _SPEC)
        assert chapter is not None
        assert chapter.status == "ready"
        assert chapter.chapter_id == "s1"
        assert chapter.title == "市场规模"  # manifest owns the title
        assert chapter.content == _LONG_CONTENT.strip()
        assert chapter.key_conclusions == [
            "中国市场规模2025年达到2000亿元",
            "同比增长12%，增速较上年放缓",
        ]
        assert [dp.metric for dp in chapter.data_points_used] == ["市场规模", "增速"]
        assert chapter.data_points_used[0].value == "2000"
        assert chapter.data_points_used[0].unit == "亿元"
        assert chapter.data_points_used[0].source == "IDC"
        assert chapter.data_points_used[0].chapter_id == "s1"

    def test_write_hook_accepts_delimiter_output(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(_DELIMITER_RAW, _SPEC)
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterWriteOutput)
        assert outcome.value.status == "ready"
        assert outcome.value.data_points_used

    def test_rewrite_hook_accepts_delimiter_output(self):
        writer = _writer()
        # original_len=600 -> F1b floor = max(200, 200) = 200；_LONG_CONTENT(~500字) 通过
        outcome = writer._rewrite_parse_with_outcome(
            _DELIMITER_RAW, _SPEC, original_len=600)
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterWriteOutput)
        assert outcome.value.status == "ready"

    def test_rewrite_hook_shrink_guard_on_delimiter_output(self):
        """F1b 缩水规则对定界符输出同样生效：超长原文配迷你定界符重写 = 退化"""
        writer = _writer()
        outcome = writer._rewrite_parse_with_outcome(
            _DELIMITER_RAW, _SPEC, original_len=100000)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_datapoints_section_absent_ok_with_empty_dps(self):
        raw = (
            "<<<REPORT_CHAPTER>>>\n"
            "STATUS: ready\n"
            "TITLE: 市场规模\n"
            "<<<CONTENT>>>\n" + _LONG_CONTENT +
            "<<<CONCLUSIONS>>>\n结论一条：市场规模创历史新高\n<<<END_REPORT_CHAPTER>>>\n"
        )
        chapter = _writer()._parse_delimiter_format(raw, _SPEC)
        assert chapter is not None
        assert chapter.status == "ready"
        assert chapter.data_points_used == []
        assert chapter.key_conclusions == ["结论一条：市场规模创历史新高"]

    def test_status_failed_maps_to_failed_chapter(self):
        raw = (
            "<<<REPORT_CHAPTER>>>\n"
            "STATUS: failed\n"
            "TITLE: 市场规模\n"
            "<<<CONTENT>>>\n无法基于现有数据完成本章\n"
            "<<<END_REPORT_CHAPTER>>>\n"
        )
        writer = _writer()
        chapter = writer._parse_delimiter_format(raw, _SPEC)
        assert chapter is not None
        assert chapter.status == "failed"
        assert chapter.content == ""
        assert chapter.error
        # An explicit failed status is a definitive answer: accepted as the
        # engine's final value; the defense loop owns failed chapters.
        outcome = writer._parse_with_outcome(raw, _SPEC)
        assert outcome.ok is True
        assert outcome.value.status == "failed"

    def test_ready_with_short_content_maps_to_failed_chapter(self):
        raw = (
            "<<<REPORT_CHAPTER>>>\n"
            "STATUS: ready\n"
            "TITLE: 市场规模\n"
            "<<<CONTENT>>>\n太短了\n"
            "<<<END_REPORT_CHAPTER>>>\n"
        )
        chapter = _writer()._parse_delimiter_format(raw, _SPEC)
        assert chapter is not None
        assert chapter.status == "failed"

    def test_malformed_datapoint_lines_skipped(self):
        raw = (
            "<<<REPORT_CHAPTER>>>\n"
            "STATUS: ready\n"
            "TITLE: 市场规模\n"
            "<<<CONTENT>>>\n" + _LONG_CONTENT +
            "<<<CONCLUSIONS>>>\n结论一条\n"
            "<<<DATAPOINTS>>>\n"
            "没有竖线的整行垃圾\n"
            "|||\n"
            "缺值|\n"
            "\n"
            "正常指标|100|台|厂商\n"
            "<<<END_REPORT_CHAPTER>>>\n"
        )
        chapter = _writer()._parse_delimiter_format(raw, _SPEC)
        assert [dp.metric for dp in chapter.data_points_used] == ["正常指标"]
        assert chapter.data_points_used[0].value == "100"
        assert chapter.data_points_used[0].unit == "台"
        assert chapter.data_points_used[0].source == "厂商"

    def test_whitespace_tolerant_markers(self):
        raw = (
            "\n\n   <<<REPORT_CHAPTER>>>   \n\n"
            "STATUS: ready\n"
            "TITLE: 市场规模\n"
            "\n<<<CONTENT>>>\n\n" + _LONG_CONTENT +
            "\n\n<<<CONCLUSIONS>>>\n\n结论一条：市场规模创历史新高\n\n"
            "<<<END_REPORT_CHAPTER>>>\n\n"
        )
        chapter = _writer()._parse_delimiter_format(raw, _SPEC)
        assert chapter is not None
        assert chapter.status == "ready"
        assert chapter.content == _LONG_CONTENT.strip()
        assert chapter.key_conclusions == ["结论一条：市场规模创历史新高"]

    def test_contract_absent_returns_none(self):
        assert _writer()._parse_delimiter_format(_JSON_RAW, _SPEC) is None
        assert _writer()._parse_delimiter_format("", _SPEC) is None


class TestJsonCompatFallback:
    def test_json_raw_still_parses(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(_JSON_RAW, _SPEC)
        assert outcome.ok is True
        assert isinstance(outcome.value, ChapterWriteOutput)
        assert outcome.value.status == "ready"

    def test_meta_reasoning_without_markers_still_rejected(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(_META_REPAIR, _SPEC)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_meta_reasoning_with_short_raw_rejected_before_delimiter(self):
        # No markers present: the delimiter attempt returns None and the
        # meta-reasoning gate keeps precedence.
        raw = "Let me repair the chapter... " + "正文" * 10
        writer = _writer()
        outcome = writer._parse_with_outcome(raw, _SPEC)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"


class TestStrictJsonVariationReinforcesMarkerFormat:
    _STRICT_JSON_PREFIX = "只输出一个合法的 JSON 对象"
    _REINFORCEMENT = "严格按上述标记格式输出，不要输出任何其他内容"

    def test_write_prompt_builder_reinforces_marker_format(self):
        writer = _writer()
        base = writer._build_write_prompt(_input(), RetryVariations(), "")
        varied = writer._build_write_prompt(
            _input(), RetryVariations(strict_json_prefix=True), "")
        assert self._REINFORCEMENT in varied
        assert self._STRICT_JSON_PREFIX not in varied
        assert varied == base + "\n严格按上述标记格式输出，不要输出任何其他内容。"

    def test_rewrite_prompt_builder_reinforces_marker_format(self):
        writer = _writer()
        chapter = ChapterWriteOutput(
            chapter_id="ch1", title="t", content="旧正文")
        varied = writer._build_rewrite_prompt(
            chapter, MagicMock(issues=[]), {"section_id": "ch1", "section_name": "n"},
            RetryVariations(strict_json_prefix=True), "", None)
        assert self._REINFORCEMENT in varied
        assert self._STRICT_JSON_PREFIX not in varied

    def test_patch_prompt_builder_reinforces_marker_format(self):
        writer = _writer()
        chapter = ChapterWriteOutput(
            chapter_id="ch1", title="t", content="旧正文")
        varied = writer._build_patch_prompt(
            chapter, ["修复数据"], {}, RetryVariations(strict_json_prefix=True))
        assert self._REINFORCEMENT in varied
        assert self._STRICT_JSON_PREFIX not in varied

    def test_engine_strict_json_rung_appends_reinforcement_not_json_prefix(self):
        writer = _writer()
        captured = []
        pending = ["...", _DELIMITER_RAW]  # first attempt degenerate -> strict rung

        async def transport(candidate, prompt="", **kwargs):
            captured.append(prompt)
            return pending.pop(0)

        engine = RetryEngine(
            transport=transport,
            candidates=lambda: [CandidateDesc(name="test-profile", model="test")],
            parse=lambda raw: writer._parse_with_outcome(raw, _SPEC),
            budget=Budget(max_calls=3, max_seconds=60),
        )
        result = asyncio.run(engine.run(
            prompt_builder=lambda v: writer._build_write_prompt(_input(), v, ""),
            output_contract=DELIMITER_OUTPUT_CONTRACT,
        ))
        assert isinstance(result, ChapterWriteOutput)
        assert result.status == "ready"
        assert len(captured) == 2
        assert self._REINFORCEMENT in captured[1]
        assert self._STRICT_JSON_PREFIX not in captured[1]


def _chapter(chapter_id, content, status="ready"):
    return ChapterWriteOutput(
        chapter_id=chapter_id, title="标题", content=content, sub_section_id="",
        key_conclusions=[], self_check_passed=True, self_check_issues=[],
        status=status, error="",
    )


class TestAssemblySanityGate:
    def _assemble(self, chapters):
        return ReportOrchestrator._assemble_final_report(
            chapters=chapters,
            exec_summary="执行摘要。",
            review=ReviewOutput(overall_score=80.0),
            topic="中国智能手机市场",
            original_sources=[],
            quality_report=None,
            conflicts_summary="",
        )

    def test_contract_marker_leakage_replaced_with_placeholder(self):
        leaked = (
            "# 市场规模\n\n以下是未清理的指令残留：\n"
            "<<<REPORT_CHAPTER>>>\nSTATUS: ready\n<<<CONTENT>>>\n"
            + ("正文内容。" * 60)
        )
        result = self._assemble([_chapter("s1", leaked)])
        section = next(s for s in result["sections"] if s["section_id"] == "s1")
        assert section["status"] == "failed"
        assert section["content"] == _PLACEHOLDER
        assert "<<<REPORT_CHAPTER>>>" not in section["content"]
        assert "<<<CONTENT>>>" not in section["content"]

    def test_meta_reasoning_leakage_replaced_with_placeholder(self):
        polluted = (
            "Let me think about how to structure this chapter. First, "
            "I need to check the evidence pool.\n"
        ) + ("正文内容。" * 60)
        result = self._assemble([_chapter("s2", polluted)])
        section = next(s for s in result["sections"] if s["section_id"] == "s2")
        assert section["status"] == "failed"
        assert section["content"] == _PLACEHOLDER

    def test_clean_chapter_unaffected(self):
        clean = "# 市场规模\n\n" + ("正文内容，数据翔实，论证充分。" * 60)
        result = self._assemble([_chapter("s3", clean)])
        section = next(s for s in result["sections"] if s["section_id"] == "s3")
        assert section["status"] == "ready"
        assert section["content"] == clean.strip()
