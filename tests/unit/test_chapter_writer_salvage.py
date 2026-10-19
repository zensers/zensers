# -*- coding: utf-8 -*-
"""ChapterWriter JSON 抢救 / patch 防护 / max_tokens env"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

import pytest

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    ChapterWriter,
    _chapter_max_tokens,
)
from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput


def test_chapter_max_tokens_default():
    os.environ.pop("ZENSERS_CHAPTER_MAX_TOKENS", None)
    assert _chapter_max_tokens() == 8192


def test_chapter_max_tokens_env():
    os.environ["ZENSERS_CHAPTER_MAX_TOKENS"] = "16384"
    assert _chapter_max_tokens() == 16384
    os.environ.pop("ZENSERS_CHAPTER_MAX_TOKENS", None)


def _writer_with_prompts():
    w = ChapterWriter(use_streaming=False)

    class _Prompts:
        def get(self, name, **kwargs):
            return "PROMPT %s" % name

    w._prompts = _Prompts()
    return w


def test_chapter_max_tokens_floor_and_cap():
    os.environ["ZENSERS_CHAPTER_MAX_TOKENS"] = "10"
    assert _chapter_max_tokens() == 4096
    os.environ["ZENSERS_CHAPTER_MAX_TOKENS"] = "999999"
    assert _chapter_max_tokens() == 32768
    os.environ.pop("ZENSERS_CHAPTER_MAX_TOKENS", None)


def test_parse_trailing_comma_repair():
    w = ChapterWriter(use_streaming=False)
    raw = '{"content": "## 章节\\n正文内容", "key_conclusions": ["a",], "data_points_used": [], }'
    out = w._parse_output(raw, {"section_id": "s1", "section_name": "章节"})
    assert out.content.startswith("## 章节")
    assert out.status == "ready"


def test_parse_truncated_json_salvage():
    w = ChapterWriter(use_streaming=False)
    body = "## 产业链全景\n\n" + "章节正文分析内容。" * 150
    raw = '{"content": "%s' % body  # 中途截断，无闭合
    out = w._parse_output(raw, {"section_id": "s2", "section_name": "产业链全景"})
    assert len(out.content) >= 800
    assert out.status == "ready"


def test_parse_markdown_salvage_fenced():
    w = ChapterWriter(use_streaming=False)
    body = "## 竞争格局\n\n" + "竞争格局分析正文。" * 300
    raw = "```markdown\n%s\n```" % body
    out = w._parse_output(raw, {"section_id": "s4", "section_name": "竞争格局"})
    assert out.content.startswith("## 竞争格局")
    assert len(out.content) >= 800
    assert not out.self_check_passed  # 抢救标记


def test_parse_garbage_still_fails():
    w = ChapterWriter(use_streaming=False)
    raw = "无法完成。"
    out = w._parse_output(raw, {"section_id": "sX", "section_name": "X"})
    assert out.status == "failed"
    assert out.content == ""


def test_parse_fence_label_envelope_still_decodes():
    """```json 围栏 + 带转义超长内容：应经 JSON 路径解码而不是泄露信封文本"""
    w = ChapterWriter(use_streaming=False)
    body = "## 核心结论\n\n本章分析正文。" * 150
    inner = body.replace("\n", "\\n")
    raw = "```json\n{\"content\": \"%s\"}\n```" % inner
    out = w._parse_output(raw, {"section_id": "s1", "section_name": "X"})
    assert out.status == "ready"
    assert out.content.startswith("## 核心结论")
    assert '"content"' not in out.content


def test_salvage_rejects_envelope_residue():
    """解码失败且含信封残迹的候选不得作为散文正文泄露"""
    w = ChapterWriter(use_streaming=False)
    body = "## 核心结论\n\n" + "正文" * 200
    raw = 'json\n{"content": "%s\\n", "broken' % body  # 未闭合且残缺
    out = w._parse_output(raw, {"section_id": "s2", "section_name": "Y"})
    assert out.status == "failed"
    assert '"content"' not in (out.content or "")


def test_patch_data_failure_keeps_original(monkeypatch):
    """预算耗尽（引擎判定无法产出可用补丁）→ 保留原章节（F1/F1b 契约）"""
    from src.core.llm_retry import Classification, LLMBudgetExhausted, LLMErrorClass
    w = _writer_with_prompts()

    async def fake_ex(prompt_builder, **kwargs):
        raise LLMBudgetExhausted(
            Classification(LLMErrorClass.BAD_JSON_FORMAT, detail="salvage-test"),
            attempts=3, elapsed=9.0)

    monkeypatch.setattr(
        "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex", fake_ex)
    original = ChapterWriteOutput(
        chapter_id="s0", title="行业概览", content="## 行业概览\n\n完整正文" * 50,
    )
    patched = asyncio.new_event_loop().run_until_complete(
        w.patch_data(chapter=original, patch_instructions=["修正"], framework_config={})
    )
    assert patched is original
    assert patched.content == original.content


def test_patch_data_success_replaces(monkeypatch):
    """可用补丁（走真实解析钩子）→ 替换内容并应用数据点合并"""
    w = _writer_with_prompts()
    body = "修订后的完整正文。" * 200
    good = (
        "<<<REPORT_CHAPTER>>>\n"
        "STATUS: ready\n"
        "TITLE: 行业概览\n"
        "<<<CONTENT>>>\n## 行业概览\n\n" + body + "\n"
        "<<<END_REPORT_CHAPTER>>>\n"
    )

    async def fake_ex(prompt_builder, **kwargs):
        spec = {"section_id": "s0", "section_name": "行业概览"}
        outcome = w._patch_parse_with_outcome(good, spec, original_len=3)
        assert outcome.ok, outcome.failure_kind
        return outcome.value

    monkeypatch.setattr(
        "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex", fake_ex)
    original = ChapterWriteOutput(chapter_id="s0", title="行业概览", content="旧内容")
    patched = asyncio.new_event_loop().run_until_complete(
        w.patch_data(chapter=original, patch_instructions=["修正"], framework_config={})
    )
    assert patched is not original
    assert "修订后的完整正文" in patched.content