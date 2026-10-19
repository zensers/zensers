# -*- coding: utf-8 -*-
"""Fix A (E1, ses_d6417b3a): output sanity gate for ChapterWriter.

Evidence: a reasoning-first profile returned raw repair narration ("The task
is to repair the chapter...") with no JSON envelope; the prose salvage path
accepted it and the delivered report opened with that meta-reasoning.  These
tests lock the gate:

- the retry-engine parse hooks classify meta-reasoning openings as
  ``degenerate`` so the engine mutates/advances and exhaustion keeps the
  previous good content;
- ``_parse_output`` keeps the failed placeholder instead of salvaging
  meta-reasoning as chapter prose;
- legitimate chapter prose (including Chinese headings) is unaffected.
"""
import json
from unittest.mock import MagicMock

import pytest

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    ChapterWriter,
    _looks_like_meta_reasoning,
)

_SPEC = {"section_id": "s1", "section_name": "测试章节"}

_META_REPAIR = (
    'The task is to repair the chapter. The main issue: quantitative claims in '
    'the body text are "unbound". Let me look at the current chapter content...'
    ' Wait, the content is truncated... Let me re-run the repair.\n\n'
    '## 修复草案\n\n'
) + ("市场规模数据需要核对后再写入正文。" * 40)

_META_LET_ME = (
    "Let me analyze the data before writing. First, I need to check the "
    "evidence pool. Okay, the metrics look consistent.\n\n"
    "## 分析草稿\n\n"
) + ("新能源汽车市场渗透率持续提升，竞争格局加速重塑。" * 40)

_GOOD_CN_HEADINGS = [
    "# 全球市场规模\n\n"
    + ("2025年全球新能源汽车市场规模达到2.1万亿元，同比增长24%，中国占比超过六成。" * 30),
    "## 一、市场规模概览\n\n"
    + ("2025年市场规模再创新高，供需两端同步扩张，出口占比稳步提升。" * 30),
]


def _writer():
    writer = ChapterWriter(use_streaming=False)
    writer._prompts = MagicMock()
    writer._prompts.get.return_value = "prompt"
    return writer


class TestLooksLikeMetaReasoning:
    @pytest.mark.parametrize("opening", [
        "The task is to repair the chapter",
        "Let me check the evidence",
        "I need to verify the numbers",
        "Wait, the content is truncated",
        "现在的任务是修复章节",
        "让我先查看数据",
        "我需要核对引用",
        "好的，我来检查",
        "首先，梳理数据来源",
        "等等，数据被截断了",
    ])
    def test_meta_openings_detected(self, opening):
        assert _looks_like_meta_reasoning(opening + " 后续内容" * 10)

    @pytest.mark.parametrize("opening", [
        "# 全球市场规模",
        "## 一、市场规模概览",
        "新能源汽车市场持续增长。",
        '{"content": "正文"}',
        "",
        None,
    ])
    def test_prose_and_json_openings_not_detected(self, opening):
        assert not _looks_like_meta_reasoning(opening)


class TestWriteParseHookSanityGate:
    def test_meta_repair_narration_is_degenerate(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(_META_REPAIR, _SPEC)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_let_me_narration_is_degenerate(self):
        writer = _writer()
        outcome = writer._parse_with_outcome(_META_LET_ME, _SPEC)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"


class TestParseOutputSalvageGate:
    @pytest.mark.parametrize("meta_raw", [_META_REPAIR, _META_LET_ME],
                             ids=["task_repair", "let_me"])
    def test_salvage_rejects_meta_reasoning(self, meta_raw):
        writer = _writer()
        chapter = writer._parse_output(meta_raw, _SPEC)
        assert chapter.status == "failed"
        assert chapter.content == ""
        assert "The task is to repair" not in chapter.content
        assert "Let me analyze" not in chapter.content

    @pytest.mark.parametrize("good_raw", _GOOD_CN_HEADINGS,
                             ids=["h1_global", "h2_section"])
    def test_good_chinese_prose_still_salvages(self, good_raw):
        # I1 起 C3 数据密度对非定性章节生效：salvage 路径不解析数据点，
        # 故本夹具使用定性章节（零数据点为 warn 级，设计 §I1 明示的豁免）。
        spec = {"section_id": "s1", "section_name": "政策与监管环境"}
        writer = _writer()
        chapter = writer._parse_output(good_raw, spec)
        assert chapter.status == "ready"
        assert len(chapter.content.strip()) >= 800

        outcome = writer._parse_with_outcome(good_raw, spec)
        assert outcome.ok is True
        assert outcome.value.status == "ready"

    def test_meta_after_valid_json_prefix_not_gated(self):
        # Only the OPENING is gated: meta text embedded inside a valid JSON
        # envelope is ordinary content and must flow through untouched.
        long_prose = ("正文论证翔实，数据支撑充分。" * 80) + " 让我再想想还有哪些数据遗漏。"
        raw = json.dumps({
            "content": long_prose,
            "data_points_used": [
                {"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"},
            ],
        }, ensure_ascii=False)
        writer = _writer()
        outcome = writer._parse_with_outcome(raw, _SPEC)
        assert outcome.ok is True
        assert "让我再想想" in outcome.value.content


class TestRewritePatchHookSanityGate:
    def test_rewrite_hook_gates_meta_reasoning(self):
        writer = _writer()
        outcome = writer._rewrite_parse_with_outcome(
            _META_REPAIR, _SPEC, original_len=1000)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_patch_hook_gates_meta_reasoning(self):
        writer = _writer()
        outcome = writer._patch_parse_with_outcome(
            _META_REPAIR, _SPEC, original_len=1000)
        assert outcome.ok is False
        assert outcome.failure_kind == "degenerate"

    def test_rewrite_hook_still_accepts_good_prose(self):
        writer = _writer()
        good = json.dumps({
            "status": "ready", "content": "重写正文" * 140,
            "data_points_used": [
                {"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "IDC"},
            ],
        }, ensure_ascii=False)
        outcome = writer._rewrite_parse_with_outcome(good, _SPEC, original_len=140)
        assert outcome.ok is True
