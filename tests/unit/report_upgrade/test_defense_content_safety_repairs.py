# -*- coding: utf-8 -*-
"""G10（F2/F3）：防御修复注入点约束。

ses_92c64980 实证缺陷：
- F2：定量句剥离的句界类含 "."，"1.2" 的小数点被当句界，句子被拦腰
  切成孤儿碎片（"…基于1." + "2万亿元等宏观数据推演…"）。
- F3：scope_collision 口径替换不识别 markdown 表格行，把整行单元格
  替换成散文免责声明，破坏表格结构。

修复约束：小数点保护 + 表格行跳过。修复动作不得制造新损伤。
"""
import pytest

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def _chapter(content: str, values=None) -> ChapterWriteOutput:
    return ChapterWriteOutput(
        chapter_id="ch1",
        title="竞争格局",
        content=content,
        data_points_used=[
            DataPoint(metric="中国AI核心产业规模", value=v, unit=u, source="新华社")
            for v, u in (values or [])
        ],
        key_conclusions=[],
    )


def _audit(codes=("unbound_numeric_claim",), chapter_id="ch1"):
    return {
        "issues": [{"code": code, "chapter_id": chapter_id} for code in codes],
    }


class TestDecimalPointProtection:
    """F2：句子不得在小数点处被切断。"""

    def test_bound_decimal_sentence_survives_whole(self):
        content = (
            "中国竞争格局的显著特征是开源生态的崛起。"
            "（推断：基于1.2万亿元等宏观数据推演，缺乏细分环节企业分布数据直接验证）。"
            "中国AI核心产业规模突破1.2万亿元。"
        )
        chapter = _chapter(content, values=[("1.2", "万亿元")])
        repaired = ReportOrchestrator._apply_defense_content_safety_repairs(
            [chapter], _audit()
        )
        # 数字已有绑定 → 句子必须原样保留，不允许出现孤儿碎片
        assert "基于1.2万亿元等宏观数据推演，缺乏细分环节企业分布数据直接验证" in chapter.content
        assert "中国AI核心产业规模突破1.2万亿元" in chapter.content
        # 句子头部完整（"基于1.2" 未被数点切开成 "…基于1." + "2万亿元…"）
        assert "（推断：基于1.2万亿元等宏观数据推演" in chapter.content

    def test_unbound_decimal_sentence_strips_cleanly_without_orphans(self):
        content = (
            "行业总盘子大概是3.7万亿元的体量。"
            "中国AI核心产业规模突破1.2万亿元。"
        )
        chapter = _chapter(content, values=[("1.2", "万亿元")])
        ReportOrchestrator._apply_defense_content_safety_repairs([chapter], _audit())
        # 未绑定小数句整体剥离，但不得留下 "7万亿元的体量" 孤儿碎片
        assert "3.7万亿元" not in chapter.content
        assert "7万亿元" not in chapter.content
        assert "万亿元的体量" not in chapter.content
        assert "中国AI核心产业规模突破1.2万亿元" in chapter.content


class TestTableLineGuard:
    """F3：markdown 表格行绝不被改写。"""

    def test_scope_collision_replacement_skips_table_rows(self):
        content = (
            "全球和中国市场的规模口径不同，需要分别说明。\n\n"
            "| 环节 | 指标 |\n"
            "|---|---|\n"
            "| 全产业链 | 全球AI市场规模1.85万亿美元，中国市场4500亿美元 |\n"
        )
        chapter = _chapter(content, values=[("1.85", "万亿美元"), ("4500", "亿美元")])
        ReportOrchestrator._apply_defense_content_safety_repairs(
            [chapter], _audit(codes=("scope_collision",))
        )
        # 散文句被替换；表格行原样保留
        assert "全球与中国市场统计口径不同，本文不将两者直接合并比较" in chapter.content
        assert "| 全产业链 | 全球AI市场规模1.85万亿美元，中国市场4500亿美元 |" in chapter.content

    def test_unbound_strip_skips_table_rows(self):
        content = (
            "行业总盘子大概是3.7万亿元的体量。\n"
            "| 全球市场规模 | 3.7万亿美元 |\n"
        )
        chapter = _chapter(content, values=[("1.2", "万亿元")])
        ReportOrchestrator._apply_defense_content_safety_repairs([chapter], _audit())
        # 散文句剥离；表格行中相同未绑定数字保留（表格数据有自己的列结构）
        assert "3.7万亿元的体量" not in chapter.content
        assert "| 全球市场规模 | 3.7万亿美元 |" in chapter.content
