import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict


class TestEnforceStructureCompliance:
    """N1: _enforce_structure_compliance - 程序化结构后处理"""

    def test_removes_fanzheng_heading(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n市场规模持续增长。\n\n"
            "## 反证与边界条件\n需求下滑可能影响增速。\n\n"
            "## 数据支撑\n2025年市场规模2000亿元。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "反证与边界条件" not in result, "反证标题应被移除"
        assert "风险提示" in result, "应生成风险提示段落"

    def test_preserves_content_in_risk_section(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n市场增长。\n\n"
            "## 反证与边界条件\n需求下滑可能影响增速，需关注政策风险。\n\n"
            "## 数据支撑\n2025年2000亿元。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "需求下滑" in result, "反证段落内容应保留在风险提示中"
        assert "政策风险" in result, "反证段落内容应保留"

    def test_removes_mutiple_forbidden_headings(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "# 核心结论\n市场增长。\n\n"
            "## 反证\n反证内容。\n\n"
            "## 边界条件\n边界条件内容。\n\n"
            "## 决策启示\n启示内容。"
        )
        result = _enforce_structure_compliance(input_text)
        # "反证" heading removed but content may contain "反证" if moved to risk
        assert "## 反证" not in result, "反证标题应被移除"
        assert "## 反证与边界条件" not in result, "反证与边界条件标题应被移除"
        assert "## 边界条件" not in result
        assert "## 决策启示" not in result
        assert "风险提示" in result

    def test_clean_content_unchanged(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n市场增长。\n\n"
            "## 论证与分析\n需求推动增长。\n\n"
            "## 数据支撑\n2000亿元。\n\n"
            "#### 风险提示\n需求不确定性。"
        )
        result = _enforce_structure_compliance(input_text)
        assert result == input_text, "合规内容不应被修改"

    def test_empty_input(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        assert _enforce_structure_compliance("") == ""

    def test_already_has_risk_section_appends_to_it(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n市场增长。\n\n"
            "## 反证与边界条件\n需求下滑风险。\n\n"
            "#### 风险提示\n已有风险。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "已有风险" in result
        assert "需求下滑风险" in result
        # 反证内容应追加到风险提示段，而非替换

    def test_yingsiang_heading_only_at_line_end(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n受到影响但仍在增长。\n\n"
            "## 影响\n市场增速放缓。\n\n"
            "## 数据支撑\n15%增速。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "**受到**" not in result or "受到影响" in result, "正文中的'影响'不应被匹配"

    def test_forbidden_heading_with_subcontent_merged(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "## 反证与边界条件\n\n需求下滑。\n\n政策风险。\n\n"
            "## 数据支撑\n数据。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "需求下滑" in result
        assert "政策风险" in result

    def test_heading_with_bold_markdown_inside(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "**## 反证与边界条件**\n需求下滑。\n\n"
            "## 数据支撑\n数据。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "反证与边界条件" not in result, "即使有加粗也应处理"

    def test_no_double_risk_section(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "## 反证与边界条件\n需求下滑。\n\n"
            "#### 风险提示\n已有风险。\n\n"
            "## 反证证据\n更多风险。"
        )
        result = _enforce_structure_compliance(input_text)
        # 应只有一个风险提示段
        assert result.count("风险提示") == 1, "不应出现多个风险提示段"

    def test_zhengming_renamed_to_lunzheng(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "## 正面论证\n需求增长驱动。\n\n"
            "## 数据支撑\n数据。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "正面论证" not in result
        assert "论证分析" in result

    def test_han_yi_merged_to_last_analysis(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "## 论证与分析\n需求增长。\n\n"
            "## 含义\n这意味着市场前景广阔。\n\n"
            "## 数据支撑\n数据。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "含义" not in result, "含义标题应被移除"

    def test_complex_multi_level_headings(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "# 一级标题\n内容。\n\n"
            "## 反证与边界条件\n反证内容。\n\n"
            "### 子标题\n子内容。"
        )
        result = _enforce_structure_compliance(input_text)
        assert "反证与边界条件" not in result
        assert "风险提示" in result

    def test_content_preserved_at_right_position(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import _enforce_structure_compliance
        input_text = (
            "## 核心结论\n增长。\n\n"
            "## 数据支撑\n2000亿。\n\n"
            "## 反证证据\n下行风险。"
        )
        result = _enforce_structure_compliance(input_text)
        # 核心顺序应为: 核心结论 → 数据支撑 → 风险提示(含反证内容)
        conclusion_pos = result.index("核心结论")
        data_pos = result.index("数据支撑")
        risk_pos = result.index("风险提示")
        assert conclusion_pos < data_pos < risk_pos, "风险提示应为最后一段"

    def test_upstream_data_points_preserved_in_split(self):
        """A1: _split_chapter_data 保留 data_points 为 upstream_data_points"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        raw_data = {
            "content": "分析正文",
            "data_points": [
                {"metric": "营收", "value": "2000", "unit": "亿元", "source": "财报"},
                {"metric": "利润", "value": "300", "unit": "亿元", "source": "财报"},
            ],
            "other_field": "其他",
        }
        refined, _ = ReportOrchestrator._split_chapter_data(raw_data, "key", {})
        assert "upstream_data_points" in refined
        assert len(refined["upstream_data_points"]) == 2
        assert refined["upstream_data_points"][0]["metric"] == "营收"
        assert refined["content"] == "分析正文"
        assert refined["other_field"] == "其他"

    def test_split_data_points_empty_list(self):
        """A1: data_points为空列表时也保留"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        raw_data = {
            "content": "正文",
            "data_points": [],
        }
        refined, _ = ReportOrchestrator._split_chapter_data(raw_data, "key", {})
        assert "upstream_data_points" in refined
        assert refined["upstream_data_points"] == []

    def test_split_no_data_points(self):
        """A1: 没有data_points字段时，refined中不应有upstream_data_points"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        raw_data = {"content": "正文", "other": "值"}
        refined, _ = ReportOrchestrator._split_chapter_data(raw_data, "key", {})
        assert "upstream_data_points" not in refined

    def test_upstream_data_points_in_orchestrator_extract(self):
        """A1: 从orchestrator完整链路验证data_points被保留"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from tests.unit.report_upgrade.test_orchestrator import MockAggregationResult
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {
            "content": "分析正文",
            "data_points": [
                {"metric": "营收", "value": "2000", "unit": "亿元", "source": "财报"},
            ],
        }}}
        chapter_data, _ = ReportOrchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data.get("upstream_data_points") is not None
        assert len(chapter_data["upstream_data_points"]) == 1
        assert chapter_data["upstream_data_points"][0]["metric"] == "营收"

    def test_upstream_data_points_in_chapter_write_input(self):
        """A1: ChapterWriteInput 接受 upstream_data_points 字段"""
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteInput
        inp = ChapterWriteInput(
            framework_config={"name": "test"},
            task_structure={},
            chapter_spec={},
            chapter_data={},
            upstream_data_points=[{"metric": "营收", "value": "2000", "unit": "亿元", "source": "财报"}],
        )
        assert inp.upstream_data_points is not None
        assert len(inp.upstream_data_points) == 1
        assert inp.upstream_data_points[0]["metric"] == "营收"

    def test_upstream_data_points_default_none(self):
        """A1: upstream_data_points 默认为 None，兼容旧调用"""
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteInput
        inp = ChapterWriteInput(
            framework_config={"name": "test"},
            task_structure={},
            chapter_spec={},
            chapter_data={},
        )
        assert inp.upstream_data_points is None

    def test_raw_summary_still_extracted_from_stripped_data_points(self):
        """A1: data_points被保留为upstream_data_points后，raw_summary仍能从meta提取"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        raw_data = {
            "content": "正文",
            "data_points": [
                {"metric": "A", "value": "1", "unit": "亿", "source": "S"},
            ],
        }
        layered_content = {"analysis": {
            "key__meta": {"data_points": [
                {"metric": "A", "value": "1", "unit": "亿", "source": "S"},
            ]},
        }}
        refined, raw_summary = ReportOrchestrator._split_chapter_data(raw_data, "key", layered_content)
        # refined 应该同时有 content 和 upstream_data_points
        assert refined.get("content") == "正文"
        assert len(refined.get("upstream_data_points", [])) == 1
        # raw_summary 应该从 meta 提取
        assert raw_summary, "raw_summary不应为空"
