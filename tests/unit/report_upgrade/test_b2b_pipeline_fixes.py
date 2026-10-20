# -*- coding: utf-8 -*-
"""B 端评估（人形机器人样稿 4/10）驱动的一批管线修订回归。

A. 括号式英文认知标签清扫（（speculative，马斯克公开预测）等 11 处实证形态）
B. 枚举感知剥离（有"其二"无"其一"的断裂枚举实证）
C. Key Data 汇总表跨章 (metric, value) 去重（同条目重复 3-6 次实证）
D. 表格宽容规整（长短行致整段 markdown 泄漏实证）
"""
import re

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def _clean(content: str) -> str:
    sections = [{"section_id": "s0", "title": "T", "content": content}]
    ReportOrchestrator._normalize_emission_artifacts(sections)
    return sections[0]["content"]


class TestParenFormEpistemicTags:
    def test_paren_tag_with_note_converted(self):
        c = _clean("才能实现量产（speculative，马斯克公开预测）。基于此推算。")
        assert "[speculative" not in c and "（speculative" not in c
        assert "（推测性判断，马斯克公开预测）" in c

    def test_paren_tag_bare_converted(self):
        c = _clean("量产目标成本（speculative） | 2万—3万美元")
        assert "（推测性判断）" in c
        assert "speculative" not in c

    def test_bracket_form_still_converted(self):
        c = _clean("拓展新的增量空间[inferential]。")
        assert "（推理性判断）" in c

    def test_table_cell_paren_tag_converted(self):
        c = _clean("| 特斯拉2026年产量目标（speculative） | 5万—10万台 |")
        assert "（推测性判断）" in c


class TestEnumerationAwareStrip:
    """剥离枚举首句不得打断'其一/其二'链条（ses_ea193fac 实证）。"""

    def _repair(self, content, values=(("990.5", "亿美元"),)):
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="T", content=content,
            data_points_used=[DataPoint(metric="营收", value=v, unit=u, source="S")
                              for v, u in values],
        )
        audit = {"issues": [{"code": "unbound_numeric_claim", "chapter_id": "ch1"}]}
        ReportOrchestrator._apply_defense_content_safety_repairs([ch], audit)
        return ch.content

    def test_enum_head_replaced_with_placeholder_not_deleted(self):
        content = (
            "其一，全球市场规模达3000亿美元，同比增长很快。"
            "其二，出货量拐点已现，头部厂商交付放量。其三，政策持续加码。"
        )
        out = self._repair(content)
        assert "其二" in out and "其三" in out, "枚举主体必须保留"
        assert "该点当前尚缺少可核验的结构化证据" in out, "枚举首槽位以中性占位保留"
        assert "3000亿美元" not in out, "未绑定数字仍必须剥离"
        # 链条完整：不存在"有二无一"的断裂形态
        assert "其二" in out and "其一，全球" not in out

    def test_non_enum_sentence_strips_cleanly(self):
        content = "行业总盘子大概是3.7亿美元的体量。中国AI核心产业规模突破1.2万亿元。"
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="T", content=content,
            data_points_used=[DataPoint(metric="规模", value="1.2", unit="万亿元", source="S")],
        )
        ReportOrchestrator._apply_defense_content_safety_repairs(
            [ch], {"issues": [{"code": "unbound_numeric_claim", "chapter_id": "ch1"}]})
        assert "3.7亿美元" not in ch.content
        assert "中国AI核心产业规模突破1.2万亿元" in ch.content


class TestKeyDataCrossSectionDedup:
    """Key Data 汇总表按 (metric, value) 跨章去重（同条目重复 3-6 次实证）。"""

    def test_same_metric_value_across_sections_collapsed(self):
        sections = [
            {"section_id": "s0", "data_points": [
                {"metric": "全球市场规模", "value": "48.9亿美元", "source_url": "u1"}]},
            {"section_id": "s1", "data_points": [
                {"metric": "全球市场规模", "value": "48.9亿美元", "source_url": "u2"}]},
            {"section_id": "s2", "data_points": [
                {"metric": "全球市场规模", "value": "1651.3亿美元", "source_url": "u1"}]},
        ]
        flat = ReportOrchestrator._flatten_section_data_points(sections)
        assert len(flat) == 2, "同指标同数值跨章只保留首个"
        assert any(dp["value"] == "1651.3亿美元" for dp in flat), "不同数值必须保留"


class TestTableLenientRender:
    """长短行表格必须渲染为 <table>，不得整段 markdown 泄漏。"""

    def _render(self, markdown_table: str) -> str:
        from src.content.content_orchestrator import (
            ContentOrchestrator, ContentSection,
        )
        co = ContentOrchestrator()
        section = ContentSection(
            id="s0", title="T", content=markdown_table, order=0)
        return co._generate_word_html(
            "标题", [section], [], [])

    def test_short_row_padded_table_still_renders(self):
        md = ("| 指标 | 数值 | 来源 |\n|---|---|---|\n"
              "| 市场规模 | 62.4亿美元 | FBI |\n"
              "| 行业标准 | 标委会成立 | 2026年1月 | 多余列 |")
        html = self._render(md)
        assert 'data-table' in html, "长短行也要渲染成表格而非泄漏原文"
        assert "| 行业标准" not in html, "原始管道符不得出现在输出中"

    def test_well_formed_table_unchanged(self):
        md = "| 指标 | 值 |\n|---|---|\n| a | b |"
        html = self._render(md)
        assert ">a</td>" in html and ">b</td>" in html


class TestSpineRegressionUnchanged:
    def test_flatten_still_skips_husks(self):
        sections = [{"data_points": [
            {"title": "证据", "url": "https://x.test/a"},
            {"metric": "规模", "value": "1.2万亿"},
        ]}]
        flat = ReportOrchestrator._flatten_section_data_points(sections)
        assert len(flat) == 1 and flat[0]["metric"] == "规模"
