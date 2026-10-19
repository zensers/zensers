import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


class TestP2RefinementProcedure:
    """P2: chapter_write.tmpl - 逐段精修指令"""

    def test_refinement_procedure_in_template(self):
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
        tmpl_dir = Path(tempfile.mkdtemp())
        (tmpl_dir / "chapter_write.tmpl").write_text(
            "# 章节精修润色任务\n\n## 精修操作规程（严格遵循）\n1. 逐段对照初稿\n2. 段落A保留原文\n3. 段落B保留推理\n4. 段落C保留数值\n5. 段落D风险提示\n\n${base_content}\n",
            encoding="utf-8",
        )
        pm = PromptManager(prompts_dir=tmpl_dir)
        rendered = pm.get("chapter_write", topic="test", base_content="content")
        assert "精修操作规程" in rendered
        assert "逐段对照初稿" in rendered

    def test_actual_template_contains_refinement_procedure(self):
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
        pm = PromptManager()
        rendered = pm.get(
            "chapter_write", topic="test", framework_name="f",
            section_name="s", section_id="s1", section_role="r",
            preceding_summary="", used_metrics_summary="",
            base_content="content", chapter_data="", raw_data_summary="",
            upstream_data_points_json="[]",
        )
        assert "精修操作规程" in rendered, "chapter_write.tmpl应包含精修操作规程"


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
        dps = ReportOrchestrator._extract_and_validate_data_points(ch)
        metric_values = {}
        for dp in dps:
            metric_values.setdefault(dp.metric, set()).add(dp.value)
        conflicts = {m: vals for m, vals in metric_values.items() if len(vals) > 1}
        assert "归母净利润" in conflicts, "同一章节内同一指标的不同值应被检测到"
        assert len(conflicts["归母净利润"]) >= 2

    def test_review_template_includes_intra_chapter_consistency_dimension(self):
        from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
        pm = PromptManager()
        rendered = pm.get(
            "chapter_review", topic="test",
            section_name="s", section_role="r",
            preceding_summary="", used_metrics_summary="",
            chapter_data="", chapter_content="content",
            writer_self_check_issues="",
        )
        assert "章内" in rendered or "自洽" in rendered or "同一章" in rendered, "chapter_review.tmpl应包含章内自洽性维度"


class TestD1ConflictResolutionWithCaliber:
    """D1: ConflictResolver 标注口径差异"""

    def test_resolution_includes_caliber_note(self):
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        from src.agents.fixed_agents.report_upgrade.models import DataPoint
        registry = DataRegistry()
        registry.register("归母净利润", "40.85", "亿元", "ch1", "财报")
        registry.register("归母净利润", "21.11", "亿元", "ch2", "财报(调整后)")
        conflicts = registry.get_conflicts()
        assert len(conflicts) >= 1
        conflict = conflicts[0]
        assert conflict.metric == "归母净利润"
        sources = [e["source"] for e in conflict.entries]
        assert any("调整" in s for s in sources), "来源中应包含口径线索"

    def test_conflict_resolver_reason_includes_caliber_difference(self):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        from src.agents.fixed_agents.report_upgrade.models import DataConflict
        import asyncio
        conflict = DataConflict(
            metric="归母净利润",
            entries=[
                {"value": "40.85亿元", "unit": "亿元", "source": "2026年一季报", "chapter_id": "ch1", "description": "归母净利润40.85亿元"},
                {"value": "21.11亿元", "unit": "亿元", "source": "2026年一季报(调整后)", "chapter_id": "ch2", "description": "归母净利润21.11亿元(剔除汇兑亏损)"},
            ],
        )
        resolver = ConflictResolver()
        resolution = asyncio.run(resolver.resolve(conflict, "比亚迪"))
        assert "口径" in resolution.reason or "调整" in resolution.reason, f"reason应包含口径差异标注, got: {resolution.reason}"


class TestD2SkillRegistryUsage:
    """D2: _extract_chapter_data skill_registry - 数据预注入"""

    def test_skill_registry_cache_used_when_raw_value_missing(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from types import SimpleNamespace
        mock_stock_skill = SimpleNamespace()
        mock_stock_skill._memory_cache = {
            ("600519", "financials"): {"success": True, "data": [{"metric": "营收", "value": "100亿"}]},
        }
        mock_registry = SimpleNamespace()
        mock_registry.get = lambda name: mock_stock_skill if name == "stock_data" else None
        aggregated = SimpleNamespace(layered_content={}, content_provenance={})
        refined, raw_summary = ReportOrchestrator._extract_chapter_data(
            aggregated, "missing_section", [],
            skill_registry=mock_registry,
        )
        assert refined != {} or raw_summary != "", "skill_registry有缓存数据时应补充而非返回空"

    def test_skill_registry_none_returns_empty(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from types import SimpleNamespace
        aggregated = SimpleNamespace(layered_content={}, content_provenance={})
        refined, raw_summary = ReportOrchestrator._extract_chapter_data(
            aggregated, "missing_section", [],
            skill_registry=None,
        )
        assert refined == {}
        assert raw_summary == ""

    def test_extract_chapter_data_returns_data_when_matched(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from types import SimpleNamespace
        aggregated = SimpleNamespace(
            layered_content={"stage1": {"sec1": {"content": "test data", "data_points": [{"metric": "营收", "value": "100"}]}}},
            content_provenance={"sec1": SimpleNamespace(section_target="target_section")},
        )
        refined, raw_summary = ReportOrchestrator._extract_chapter_data(
            aggregated, "target_section", [],
            skill_registry=None,
        )
        assert refined.get("content") == "test data"
        assert refined.get("upstream_data_points") is not None


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

    def test_precise_value_from_chapter_data_not_raw_summary(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, ChapterIssue
        issues = [ChapterIssue(
            category="data_support", severity="HIGH",
            location="p:1", description='缺失"归母净利润"数据',
            suggestion="补充归母净利润数据",
        )]
        chapter_data = {
            "content": "分析正文",
            "upstream_data_points": [
                {"metric": "归母净利润", "value": "40.85", "unit": "亿元", "source": "一季报"},
            ],
        }
        result = ReportOrchestrator._build_anchor_patch_instructions(
            issues, chapter_data, raw_data_summary="",
        )
        assert len(result) >= 1
        assert any("40.85" in r for r in result), "应从chapter_data.upstream_data_points提取精确数值"

    def test_precise_value_from_chapter_data_dict_values(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, ChapterIssue
        issues = [ChapterIssue(
            category="data_support", severity="HIGH",
            location="p:1", description="缺失营收数据",
            suggestion="补充营收数据",
        )]
        chapter_data = {
            "content": "分析正文",
            "营收": "2000亿元",
            "upstream_data_points": [],
        }
        result = ReportOrchestrator._build_anchor_patch_instructions(
            issues, chapter_data, raw_data_summary="",
        )
        assert len(result) >= 1
        assert any("2000" in r for r in result), "应从chapter_data字典值提取精确数值"

    def test_fallback_to_raw_summary_when_chapter_data_has_no_match(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, ChapterIssue
        issues = [ChapterIssue(
            category="data_support", severity="HIGH",
            location="p:1", description="缺失未知指标数据",
            suggestion="补充数据",
        )]
        chapter_data = {"content": "正文", "upstream_data_points": []}
        result = ReportOrchestrator._build_anchor_patch_instructions(
            issues, chapter_data, raw_data_summary="未知指标: 999",
        )
        assert len(result) >= 1
