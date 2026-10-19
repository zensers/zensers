# -*- coding: utf-8 -*-
"""Phase R（报告格式标准 D1/D2）：组装层确定性处理。

D1 方法与口径前置：全文档只保留首次出现的口径声明句，其余删除并收集为
methodology_notes（渲染层前置呈现）。
D2 Exhibit 编号制：按章节顺序为数据表插入全局编号题注。
"""
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

DECL = "全球与中国市场统计口径不同，本文不将两者直接合并比较。"
DECL2 = "全价值链口径与核心口径不同，两者不可直接比较。"


def _sec(sid, title, content):
    return {"section_id": sid, "title": title, "content": content}


class TestDedupeMethodologyDeclarations:
    def test_keeps_first_occurrence_and_collects_note(self):
        sections = [
            _sec("s0", "市场规模", f"全球AI市场高速增长。{DECL}中国核心产业规模突破1.2万亿元。"),
            _sec("s1", "竞争格局", f"竞争分析。{DECL}开源生态崛起。"),
        ]
        out, notes = ReportOrchestrator._dedupe_methodology_declarations(sections)
        assert DECL in out[0]["content"], "首次出现保留在原位"
        assert DECL not in out[1]["content"], "后续重复删除"
        assert notes == [DECL]

    def test_distinct_declarations_all_collected(self):
        sections = [
            _sec("s0", "市场规模", f"正文。{DECL}"),
            _sec("s1", "技术", f"正文。{DECL2}"),
        ]
        out, notes = ReportOrchestrator._dedupe_methodology_declarations(sections)
        assert notes == [DECL, DECL2]
        assert DECL in out[0]["content"]
        assert DECL2 in out[1]["content"]

    def test_table_lines_never_touched(self):
        content = (
            "| 指标 | 来源 |\n|---|---|\n"
            f"| {DECL} | 新华社 |\n\n正文。{DECL}"
        )
        sections = [_sec("s0", "产业链", content), _sec("s1", "趋势", f"正文。{DECL}")]
        out, notes = ReportOrchestrator._dedupe_methodology_declarations(sections)
        # 表格行原样保留；正文首现保留；s1 重复删除
        assert f"| {DECL} | 新华社 |" in out[0]["content"]
        assert DECL in out[0]["content"].split("\n")[-1]
        assert DECL not in out[1]["content"]
        assert notes == [DECL]

    def test_no_declarations_yields_empty_notes(self):
        sections = [_sec("s0", "市场", "普通章节内容，没有口径声明。")]
        out, notes = ReportOrchestrator._dedupe_methodology_declarations(sections)
        assert notes == []
        assert out[0]["content"] == sections[0]["content"]

    def test_standalone_declaration_line_removed_cleanly(self):
        sections = [
            _sec("s0", "市场", f"正文一。{DECL}"),
            _sec("s1", "技术", f"{DECL}\n正文二。"),
        ]
        out, notes = ReportOrchestrator._dedupe_methodology_declarations(sections)
        assert out[1]["content"].strip() == "正文二。"
        assert notes == [DECL]


class TestApplyExhibitNumbering:
    def test_tables_numbered_sequentially_across_sections(self):
        sections = [
            _sec("s0", "市场规模", "前言。\n\n| 指标 | 值 |\n|---|---|\n| 规模 | 3759.3亿美元 |\n\n后文。"),
            _sec("s1", "技术", "| 指标 | 值 |\n|---|---|\n| 下载量 | 100亿次 |"),
        ]
        out = ReportOrchestrator._apply_exhibit_numbering(sections)
        c0, c1 = out[0]["content"], out[1]["content"]
        assert "**Exhibit 1｜市场规模**" in c0
        assert "**Exhibit 2｜技术**" in c1
        # 题注紧邻表格之前
        assert c0.index("**Exhibit 1｜市场规模**") < c0.index("| 指标 | 值 |")

    def test_idempotent_existing_captions_not_duplicated(self):
        content = "**Exhibit 3｜市场规模**\n\n| 指标 | 值 |\n|---|---|\n| 规模 | 1.2万亿元 |"
        sections = [_sec("s0", "市场规模", content)]
        out = ReportOrchestrator._apply_exhibit_numbering(sections)
        assert out[0]["content"].count("**Exhibit") == 1
        assert "**Exhibit 3｜市场规模**" in out[0]["content"]

    def test_no_tables_no_captions(self):
        sections = [_sec("s0", "市场", "纯文本章节，无表格。")]
        out = ReportOrchestrator._apply_exhibit_numbering(sections)
        assert "Exhibit" not in out[0]["content"]

    def test_separator_only_fragments_not_numbered(self):
        """孤立分隔符行（非完整表格）不编号。"""
        sections = [_sec("s0", "市场", "|---|---|\n正文。")]
        out = ReportOrchestrator._apply_exhibit_numbering(sections)
        assert "Exhibit" not in out[0]["content"]


class TestNormalizeEmissionArtifacts:
    """ses_ea193fac 实证三类 emission 伪影的清扫。"""

    def test_closed_bracket_tag_converted_to_chinese(self):
        sections = [{"section_id": "s0", "title": "T",
                     "content": "拓展新的增量空间[inferential]。后续正文。"}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        assert "[inferential]" not in sections[0]["content"]
        assert "（推理性判断）" in sections[0]["content"]

    def test_unclosed_bracket_repairs_sentence_boundary(self):
        sections = [{"section_id": "s0", "title": "T",
                     "content": "有望实现规模化放量[speculative；出货量预测的锚点已从样机转向量产目标。"}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        c = sections[0]["content"]
        assert "[speculative" not in c
        assert "（推测性判断）。出货量预测的锚点" in c, f"吞句未修复: {c}"

    def test_naked_url_artifact_removed(self):
        sections = [{"section_id": "s0", "title": "T",
                     "content": "出货量与产业主体数量是刻画其规模特征的最直接指标。zhihu.com/p/1951970206575499155）。\n\n需要说明的是，尚无统一口径。"}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        c = sections[0]["content"]
        assert "zhihu.com" not in c
        assert "刻画其规模特征的最直接指标。" in c, "正文句子必须保留"

    def test_markdown_link_survives(self):
        """数据支撑表的正常 markdown 链接不得误伤。"""
        content = (
            "| 指标 | 来源 |\n|---|---|\n"
            "| 规模 | [IIM研究报告](https://www.iim.net.cn/106/view-308889-1.html) |\n"
        )
        sections = [{"section_id": "s0", "title": "T", "content": content}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        assert "[IIM研究报告](https://www.iim.net.cn/106/view-308889-1.html)" in sections[0]["content"]

    def test_odd_bold_marker_dropped_pairs_kept(self):
        sections = [{"section_id": "s0", "title": "T",
                     "content": "口径声明。** 从产业主体看，**市场规模扩大**是主因。"}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        c = sections[0]["content"]
        assert c.count("**") % 2 == 0
        assert "**市场规模扩大**" in c, "成对粗体保留"

    def test_even_bold_untouched(self):
        sections = [{"section_id": "s0", "title": "T",
                     "content": "**Exhibit 1｜市场规模**\n\n| 指标 | 值 |\n|---|---|\n| a | b |"}]
        ReportOrchestrator._normalize_emission_artifacts(sections)
        assert "**Exhibit 1｜市场规模**" in sections[0]["content"]
