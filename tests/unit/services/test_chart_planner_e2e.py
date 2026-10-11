# -*- coding: utf-8 -*-
import json
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.chart_planner import ChartPlannerAgent, ChartPlan
from src.services.chart_generator import ChartGenerator, ChartType, ChartConfig


REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "data",
    "e2e_v4_report.json",
)


def _load_report():
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestEndToEndPlanRenderInsert(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.gen = ChartGenerator(output_dir="output/e2e_integration")
        os.makedirs("output/e2e_integration", exist_ok=True)

    def _plan_to_chart_dict(self, plan, render_result, aspect="核心财务指标与盈利能力"):
        return {
            "chart_type": plan.chart_type.value,
            "title": plan.title,
            "path": render_result.image_path,
            "caption": plan.caption,
            "aspect": aspect,
            "insertion_anchor": plan.insertion_anchor,
            "anchor_type": plan.anchor_type,
        }

    def test_plan_compose_validate_render_bar(self):
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2023-12-31", "营业总收入": 602315000000, "净利润": 312444000000},
                    {"报告期": "2024-12-31", "营业总收入": 777102000000, "净利润": 413260000000},
                    {"报告期": "2025-12-31", "营业总收入": 803900000000, "净利润": 445000000000},
                ],
            }
        }
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        data = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertFalse(self.agent._has_empty_chart_data(data, ChartType.BAR))

        plan = ChartPlan(
            chart_type=ChartType.BAR,
            title="比亚迪年度营收（亿元）",
            subtitle="数据来源：比亚迪财报",
            data=data,
            caption="2024年营收突破7700亿",
            xlabel="年度",
            ylabel="亿元",
            confidence=0.85,
            reason="营收趋势",
            insertion_anchor="营业收入1,502.25亿元",
            anchor_type="after_paragraph",
            unit="亿元",
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))
        self.assertTrue(self.agent._check_value_range(plan))

        config = ChartConfig(
            chart_type=plan.chart_type,
            title=plan.title,
            data=plan.data,
            xlabel=plan.xlabel,
            ylabel=plan.ylabel,
            caption=plan.caption,
            source=plan.source,
        )
        result = self.gen.generate(config)
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(result.image_path))

        chart_dict = self._plan_to_chart_dict(plan, result)
        self.assertIn("insertion_anchor", chart_dict)
        self.assertIn("anchor_type", chart_dict)
        self.assertEqual(chart_dict["anchor_type"], "after_paragraph")

    def test_plan_compose_validate_render_barline(self):
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2022-12-31", "营业总收入": 424061000000, "净利润": 166224000000},
                    {"报告期": "2023-12-31", "营业总收入": 602315000000, "净利润": 312444000000},
                    {"报告期": "2024-12-31", "营业总收入": 777102000000, "净利润": 413260000000},
                    {"报告期": "2025-12-31", "营业总收入": 803900000000, "净利润": 445000000000},
                ],
            }
        }
        data = self.agent._compose_bar_line(fetched, [], [])
        self.assertIn("years", data)
        self.assertIn("bar", data)
        self.assertIn("line", data)

        plan = ChartPlan(
            chart_type=ChartType.BAR_LINE,
            title="比亚迪营收增速从42%骤降至3.4%",
            subtitle="数据来源：比亚迪财报",
            data=data,
            caption="增长引擎明显失速",
            xlabel="年度",
            ylabel="营业收入(元)",
            confidence=0.9,
            reason="营收趋势+增速双轴图",
            insertion_anchor="营收持续增长",
            anchor_type="after_paragraph",
            unit="元",
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))

        config = ChartConfig(
            chart_type=plan.chart_type,
            title=plan.title,
            data=plan.data,
            xlabel=plan.xlabel,
            ylabel=plan.ylabel,
            caption=plan.caption,
        )
        result = self.gen.generate(config)
        self.assertTrue(result.success)

    def test_anchor_insertion_into_html(self):
        from src.content.content_orchestrator import ContentOrchestrator

        md_content = (
            "## 核心财务指标与盈利能力\n\n"
            "**核心结论**：2026年第一季度，比亚迪营业收入1,502.25亿元，同比下降11.82%。\n\n"
            "更为严峻的是，归母净利润仅为40.85亿元，同比大幅下滑55.38%。\n\n"
            "| 指标 | 2026Q1 | 同比变化 |\n|---|---|---|\n"
            "| 营业收入 | 1502.25亿元 | -11.82% |\n| 归母净利润 | 40.85亿元 | -55.38% |\n"
        )

        html = (
            "<h2>核心财务指标与盈利能力</h2>\n"
            "<p><strong>核心结论</strong>：2026年第一季度，比亚迪营业收入1,502.25亿元，同比下降11.82%。</p>\n"
            "<p>更为严峻的是，归母净利润仅为40.85亿元，同比大幅下滑55.38%。</p>\n"
            "<table><tr><td>指标</td><td>2026Q1</td><td>同比变化</td></tr>"
            "<tr><td>营业收入</td><td>1502.25亿元</td><td>-11.82%</td></tr></table>\n"
        )

        charts = [{
            "path": "output/e2e_integration/test_anchor.png",
            "caption": "营收与利润双降",
            "insertion_anchor": "营业收入1,502.25亿元",
            "anchor_type": "after_paragraph",
            "title": "比亚迪营收利润变动",
            "chart_type": "bar",
        }]

        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="测试锚点",
            data={"categories": ["A", "B"], "values": [1, 2]},
        )
        result = self.gen.generate(config)
        charts[0]["path"] = result.image_path

        orchestrator = ContentOrchestrator()
        result_html = orchestrator._insert_charts_into_html(html, charts, md_content)

        self.assertIn('<figure class="chart-container">', result_html)
        self.assertIn("营收与利润双降", result_html)

    def test_section_start_anchor(self):
        from src.content.content_orchestrator import ContentOrchestrator

        md_content = "## 行业分析\n\n比亚迪在新能源领域占据主导地位。"
        html = "<h2>行业分析</h2>\n<p>比亚迪在新能源领域占据主导地位。</p>\n"

        charts = [{
            "path": "",
            "caption": "行业格局",
            "insertion_anchor": "行业分析",
            "anchor_type": "section_start",
            "title": "新能源行业格局",
            "chart_type": "line",
        }]

        orchestrator = ContentOrchestrator()
        result_html = orchestrator._insert_charts_into_html(html, charts, md_content)

        self.assertIn('<figure class="chart-container">', result_html)
        figure_pos = result_html.index('<figure class="chart-container">')
        h2_pos = result_html.index("<h2>")
        self.assertLess(figure_pos, h2_pos, "section_start chart should appear before <h2>")

    def test_section_end_anchor(self):
        from src.content.content_orchestrator import ContentOrchestrator

        md_content = "## 行业分析\n\n比亚迪在新能源领域占据主导地位。"
        html = "<h2>行业分析</h2>\n<p>比亚迪在新能源领域占据主导地位。</p>\n"

        charts = [{
            "path": "",
            "caption": "总结",
            "insertion_anchor": "",
            "anchor_type": "section_end",
            "title": "行业总结",
            "chart_type": "bar",
        }]

        orchestrator = ContentOrchestrator()
        result_html = orchestrator._insert_charts_into_html(html, charts, md_content)

        self.assertIn('<figure class="chart-container">', result_html)

    def test_full_chain_with_real_report(self):
        report = _load_report()
        section = report["sections"][0]
        content = section["content"]

        tables = self.agent._extract_tables(content)
        self.assertGreaterEqual(len(tables), 1)

        filtered = self.agent._prefilter_tables(tables, report["topic"], section["title"])
        self.assertGreaterEqual(len(filtered), 0)

        plan = ChartPlan(
            chart_type=ChartType.BAR_LINE,
            title="比亚迪营收增速放缓，利润同比腰斩",
            subtitle="数据来源：比亚迪财报",
            data={
                "years": ["2022", "2023", "2024", "2025"],
                "bar": [4241, 6023, 7771, 8039],
                "line": [None, 42.0, 29.0, 3.4],
                "bar_label": "营业收入(亿元)",
                "line_label": "同比增速(%)",
            },
            caption="营收规模持续扩大但增速显著放缓",
            xlabel="年度",
            ylabel="营业收入(亿元)",
            confidence=0.85,
            reason="营收趋势+增速",
            insertion_anchor="营业收入1,502.25亿元",
            anchor_type="after_paragraph",
            unit="亿元",
        )

        validated = self.agent._validate_plans([plan])
        self.assertEqual(len(validated), 1)

        config = ChartConfig(
            chart_type=plan.chart_type,
            title=plan.title,
            data=plan.data,
            xlabel=plan.xlabel,
            ylabel=plan.ylabel,
            caption=plan.caption,
        )
        render_result = self.gen.generate(config)
        self.assertTrue(render_result.success)
        self.assertTrue(os.path.exists(render_result.image_path))
        self.assertGreater(os.path.getsize(render_result.image_path), 5000)

    def test_planner_disabled_falls_back_to_legacy(self):
        with patch("src.config.settings") as mock_settings:
            mock_cp = MagicMock()
            mock_cp.enabled = False
            mock_settings.chart_planner = mock_cp

            from src.config import settings
            planner_enabled = getattr(settings, 'chart_planner', None)
            if planner_enabled is not None:
                planner_enabled = getattr(planner_enabled, 'enabled', True)
            else:
                planner_enabled = True
            self.assertFalse(planner_enabled)

    def test_waterfall_full_chain(self):
        plan = ChartPlan(
            chart_type=ChartType.WATERFALL,
            title="比亚迪Q1利润变动拆解",
            subtitle="",
            data={
                "factors": [
                    {"label": "去年同期利润", "value": 91.5, "is_total": True},
                    {"label": "营收下滑", "value": -17.8},
                    {"label": "汇兑亏损", "value": -21.0},
                    {"label": "毛利压缩", "value": -15.0},
                    {"label": "本期利润", "value": 40.85, "is_total": True},
                ]
            },
            caption="汇兑亏损+价格战是主因",
            xlabel="",
            ylabel="亿元",
            confidence=0.8,
            reason="利润拆解",
            insertion_anchor="利润下滑",
            anchor_type="after_paragraph",
            unit="亿元",
        )
        validated = self.agent._validate_plans([plan])
        self.assertEqual(len(validated), 1)

        config = ChartConfig(
            chart_type=plan.chart_type,
            title=plan.title,
            data=plan.data,
            ylabel=plan.ylabel,
            caption=plan.caption,
        )
        result = self.gen.generate(config)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
