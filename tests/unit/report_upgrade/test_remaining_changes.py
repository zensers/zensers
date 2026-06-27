import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


class TestP6ExecSummaryStructure:
    """P6: exec_summary.tmpl - 增加结构约束"""

    def test_exec_summary_prompt_includes_structure(self):
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
        import tempfile, os
        tmpl_dir = Path(tempfile.mkdtemp())
        (tmpl_dir / "exec_summary.tmpl").write_text(
            "## 执行摘要结构\n1. **核心结论**\n2. **关键数据**\n3. **风险展望**\n4. 禁止使用一方面另一方面",
            encoding="utf-8",
        )
        pm = PromptManager(prompts_dir=tmpl_dir)
        rendered = pm.get("exec_summary", topic="test", all_conclusions="c", conflict_descriptions="none")
        assert "核心结论" in rendered
        assert "关键数据" in rendered
        assert "风险展望" in rendered
        assert "一方面" in rendered or "禁止" in rendered


class TestP4IntraChapterConsistency:
    """P4: 章内数据自洽性检查"""

    def test_detects_conflict_in_same_chapter(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="财务",
            content="归母净利润40.85亿元。调整后归母净利润21.11亿元。",
            data_points_used=[
                DataPoint(metric="归母净利润", value="40.85", unit="亿元", source="A", chapter_id="ch1"),
                DataPoint(metric="归母净利润", value="21.11", unit="亿元", source="B", chapter_id="ch1"),
            ],
        )
        orchestrator = MagicMock()
        # 验证两个不同值指向同一metric
        dps = ReportOrchestrator._extract_and_validate_data_points(ch)
        metric_values = {}
        for dp in dps:
            metric_values.setdefault(dp.metric, set()).add(dp.value)
        conflicts = {m: vals for m, vals in metric_values.items() if len(vals) > 1}
        assert "归母净利润" in conflicts, "同一章节内同一指标的不同值应被检测到"
        assert len(conflicts["归母净利润"]) >= 2


class TestD1ConflictResolutionWithCaliber:
    """D1: ConflictResolver 标注口径差异"""

    def test_resolution_includes_caliber_note(self):
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        from src.agents.fixed_agents.report_upgrade.models import DataPoint
        registry = DataRegistry()
        # 注册两个不同值 (不同口径)
        registry.register("归母净利润", "40.85", "亿元", "ch1", "财报")
        registry.register("归母净利润", "21.11", "亿元", "ch2", "财报(调整后)")
        conflicts = registry.get_conflicts()
        assert len(conflicts) >= 1
        # 检查冲突条目中包含口径线索
        conflict = conflicts[0]
        assert conflict.metric == "归母净利润"
        sources = [e["source"] for e in conflict.entries]
        assert any("调整" in s for s in sources), "来源中应包含口径线索"


class TestE5PrecisePatchValues:
    """E5: patch指令包含精确数值"""

    def test_precise_value_in_patch_instruction(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, ChapterIssue
        issues = [ChapterIssue(
            category="data_support", severity="HIGH",
            location="p:1", description="缺失营收数据",
            suggestion="补充营收数据",
        )]
        chapter_data = {"content": "分析正文", "营收": "2000亿元"}
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, chapter_data, raw_data_summary="营收: 2000亿元")
        assert len(result) >= 1
        assert any("2000" in r for r in result), "patch指令应包含精确数值2000"
