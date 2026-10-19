# -*- coding: utf-8 -*-
import json
import os
import unittest

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


class TestExtractTablesFromRealReport(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.report = _load_report()

    def test_section0_has_table(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        self.assertGreaterEqual(len(tables), 1)

    def test_table_has_numeric_columns(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        for t in tables:
            self.assertGreater(len(t.numeric_columns), 0)

    def test_table_values_extractable(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        for t in tables:
            for col_idx in t.numeric_columns:
                vals = self.agent._extract_numeric_values(t, col_idx)
                self.assertGreater(len(vals), 0)
                has_nonzero = any(v != 0 for v in vals)
                self.assertTrue(has_nonzero)


class TestPrefilterTablesWithRealReport(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.report = _load_report()

    def test_tables_filtered_by_topic(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        filtered = self.agent._prefilter_tables(tables, self.report["topic"], section["title"])
        self.assertGreaterEqual(len(filtered), 1)

    def test_irrelevant_table_filtered_out(self):
        content = (
            "| 日期 | 天气 | 温度 |\n|---|---|---|\n"
            "| 2025-01-01 | 晴 | 15 |\n| 2025-01-02 | 雨 | 10 |\n"
        )
        tables = self.agent._extract_tables(content)
        filtered = self.agent._prefilter_tables(tables, "比亚迪财务分析", "核心财务指标")
        self.assertEqual(len(filtered), 0)


class TestPrepareLlmInputWithRealReport(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.report = _load_report()

    def test_section0_summary_not_empty(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        filtered = self.agent._prefilter_tables(tables, self.report["topic"], section["title"])
        summary, tables_json = self.agent._prepare_llm_input(section["content"], filtered)
        self.assertGreater(len(summary), 100)
        self.assertIn("11.82", summary)

    def test_tables_json_valid(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        filtered = self.agent._prefilter_tables(tables, self.report["topic"], section["title"])
        _, tables_json = self.agent._prepare_llm_input(section["content"], filtered)
        parsed = json.loads(tables_json)
        self.assertIsInstance(parsed, list)
        if parsed:
            self.assertIn("headers", parsed[0])


class TestComposeChartWithRealFinancialsData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_bar_from_real_financials(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2023-12-31", "营业总收入": 602315000000, "净利润": 312444000000},
                    {"报告期": "2024-12-31", "营业总收入": 777102000000, "净利润": 413260000000},
                    {"报告期": "2025-12-31", "营业总收入": 803900000000, "净利润": 445000000000},
                    {"报告期": "2026-03-31", "营业总收入": 150225000000, "净利润": 40850000000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertIn("values", result)
        self.assertEqual(len(result["categories"]), 4)
        self.assertAlmostEqual(result["values"][0], 602315000000, places=-6)

    def test_bar_line_from_real_financials(self):
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
        result = self.agent._compose_bar_line(fetched, [], [])
        self.assertIn("years", result)
        self.assertEqual(len(result["years"]), 3)
        self.assertEqual(result["line"][0], None)
        self.assertEqual(result["years"][0], "2023-12-31")
        self.assertAlmostEqual(result["line"][1], 29.0, places=0)

    def test_line_normalize_pct_two_series(self):
        chart_raw = {"chart_type": "line", "data_strategy": "normalize_pct"}
        fetched = {
            "stock_price:002594": {
                "id": "req1",
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪",
                "data": {
                    "dates": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"],
                    "closes": [280, 310, 295, 320, 350],
                },
            },
            "index_price:000300": {
                "id": "req2",
                "source": "index_price",
                "params": {"symbol": "000300"},
                "purpose": "沪深300",
                "data": {
                    "dates": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"],
                    "closes": [3800, 3950, 3900, 4050, 4100],
                },
            },
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "normalize_pct")
        self.assertIn("scenarios", result)
        self.assertEqual(result["unit"], "%")
        byd_vals = result["scenarios"]["比亚迪"]
        self.assertEqual(byd_vals[0], 100)
        hs_vals = result["scenarios"]["沪深300"]
        self.assertEqual(hs_vals[0], 100)

    def test_radar_from_metrics(self):
        chart_raw = {"chart_type": "radar", "data_strategy": "raw"}
        fetched = {
            "stock_metrics:002594": {
                "source": "stock_metrics",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪",
                "data": [
                    {
                        "股票代码": "002594",
                        "股票简称": "比亚迪",
                        "毛利率": 20.5,
                        "净利率": 5.8,
                        "ROE": 18.2,
                        "资产负债率": 65.3,
                        "营收增速": 29.0,
                    }
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertIn("values", result)
        self.assertGreaterEqual(len(result["categories"]), 4)
        self.assertTrue(all(v <= 100 for v in result["values"]))


class TestValidateWithRealData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_bar_line_with_real_revenue_passes_validation(self):
        plan = ChartPlan(
            chart_type=ChartType.BAR_LINE,
            title="比亚迪营收增速放缓，净利润同比腰斩",
            subtitle="数据来源：比亚迪财报",
            data={
                "years": ["2023", "2024", "2025"],
                "bar": [6023, 7771, 8039],
                "line": [None, 29.0, 3.4],
                "bar_label": "营业收入(亿元)",
                "line_label": "同比增速(%)",
            },
            caption="营收规模持续扩大但增速显著放缓",
            xlabel="年度",
            ylabel="营业收入(亿元)",
            confidence=0.85,
            reason="营收趋势+增速双轴图",
            insertion_anchor="营收规模持续扩大",
            anchor_type="after_paragraph",
            unit="亿元",
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))
        self.assertTrue(self.agent._check_value_range(plan))
        self.assertTrue(self.agent._check_unit_consistency(plan))

    def test_pie_with_real_market_share(self):
        plan = ChartPlan(
            chart_type=ChartType.PIE,
            title="2025年新能源汽车市场份额：比亚迪领跑",
            subtitle="数据来源：中汽协",
            data={
                "labels": ["比亚迪", "特斯拉中国", "吉利", "广汽埃安", "其他"],
                "values": [35, 12, 8, 6, 39],
            },
            caption="比亚迪占据1/3市场份额",
            xlabel="",
            ylabel="",
            confidence=0.8,
            reason="市场份额分布",
            insertion_anchor="市场份额",
            anchor_type="after_paragraph",
            unit="%",
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))
        self.assertTrue(self.agent._check_value_range(plan))

    def test_waterfall_profit_change(self):
        plan = ChartPlan(
            chart_type=ChartType.WATERFALL,
            title="比亚迪Q1净利润同比减少50.7亿元的因素拆解",
            subtitle="数据来源：比亚迪财报",
            data={
                "factors": [
                    {"label": "去年同期净利润", "value": 91.5, "is_total": True},
                    {"label": "营收下滑", "value": -17.8},
                    {"label": "汇兑亏损", "value": -21.0},
                    {"label": "价格战毛利压缩", "value": -15.0},
                    {"label": "费用率上升", "value": -3.2},
                    {"label": "本期净利润", "value": 40.85, "is_total": True},
                ]
            },
            caption="汇兑亏损和价格战是利润下滑主因",
            xlabel="",
            ylabel="亿元",
            confidence=0.75,
            reason="利润变动因素拆解",
            insertion_anchor="利润下滑",
            anchor_type="after_paragraph",
            unit="亿元",
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))
        self.assertTrue(self.agent._check_value_range(plan))
        self.assertTrue(self.agent._check_unit_consistency(plan))


class TestChartGeneratorRenderingWithRealData(unittest.TestCase):
    def setUp(self):
        self.gen = ChartGenerator(output_dir="output/test_real_charts")
        os.makedirs("output/test_real_charts", exist_ok=True)

    def _assert_chart_ok(self, result):
        self.assertTrue(result.success, f"Chart generation failed: {result.error}")
        self.assertIsNotNone(result.image_path)
        self.assertTrue(os.path.exists(result.image_path), f"File not found: {result.image_path}")
        size = os.path.getsize(result.image_path)
        self.assertGreater(size, 5000, f"Chart file too small: {size}B")

    def test_bar_line_real_byd_data(self):
        config = ChartConfig(
            chart_type=ChartType.BAR_LINE,
            title="比亚迪营收增速放缓，净利润同比腰斩",
            data={
                "years": ["2023", "2024", "2025"],
                "bar": [6023, 7771, 8039],
                "line": [None, 29.0, 3.4],
                "bar_label": "营业收入(亿元)",
                "line_label": "同比增速(%)",
            },
            ylabel="营业收入(亿元)",
            caption="营收规模持续扩大但增速显著放缓",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_bar_real_byd_revenue(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="比亚迪季度营收对比（亿元）",
            data={
                "categories": ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1"],
                "values": [1502, 1762, 2011, 2422, 1700],
            },
            ylabel="亿元",
            caption="2024Q4为全年最高",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_pie_market_share(self):
        config = ChartConfig(
            chart_type=ChartType.PIE,
            title="2025年新能源汽车市场份额",
            data={
                "labels": ["比亚迪", "特斯拉中国", "吉利", "广汽埃安", "其他"],
                "values": [35, 12, 8, 6, 39],
            },
            caption="比亚迪占据1/3市场份额",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_waterfall_profit_change(self):
        config = ChartConfig(
            chart_type=ChartType.WATERFALL,
            title="比亚迪Q1净利润变动因素拆解",
            data={
                "factors": [
                    {"label": "去年同期利润", "value": 91.5, "is_total": True},
                    {"label": "营收下滑", "value": -17.8},
                    {"label": "汇兑亏损", "value": -21.0},
                    {"label": "毛利压缩", "value": -15.0},
                    {"label": "本期利润", "value": 40.85, "is_total": True},
                ]
            },
            ylabel="亿元",
            caption="汇兑亏损+价格战是主因",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_line_stock_vs_index(self):
        config = ChartConfig(
            chart_type=ChartType.LINE,
            title="比亚迪股价跑输沪深300达25个百分点",
            data={
                "years": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"],
                "scenarios": {
                    "比亚迪": [100, 110.7, 105.4, 114.3, 125.0],
                    "沪深300": [100, 103.9, 102.6, 106.6, 107.9],
                },
            },
            ylabel="归一化指数(首日=100)",
            caption="比亚迪5个月超额收益约17个百分点",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_radar_metrics(self):
        config = ChartConfig(
            chart_type=ChartType.RADAR,
            title="比亚迪vs行业均值：五维能力评估",
            data={
                "categories": ["毛利率", "净利率", "ROE", "营收增速", "资产周转率"],
                "scenarios": {
                    "比亚迪": [20.5, 5.8, 18.2, 29.0, 55.0],
                    "行业均值": [15.0, 4.0, 10.0, 12.0, 40.0],
                },
            },
            caption="比亚迪在增速和ROE上显著领先",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_grouped_bar_comparison(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="比亚迪vs特斯拉：核心财务指标对比",
            data={
                "categories": ["2023", "2024", "2025"],
                "series": [
                    {"name": "比亚迪营收(亿)", "values": [6023, 7771, 8039]},
                    {"name": "特斯拉营收(亿)", "values": [5800, 6200, 6500]},
                ],
            },
            ylabel="亿元",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_hbar_ranking(self):
        config = ChartConfig(
            chart_type=ChartType.HBAR,
            title="2025年新能源车企净利润排名（亿元）",
            data={
                "categories": ["比亚迪", "特斯拉", "宁德时代", "理想汽车", "蔚来"],
                "values": [445, 380, 420, 80, -50],
            },
            xlabel="亿元",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_scatter_valuation(self):
        config = ChartConfig(
            chart_type=ChartType.SCATTER,
            title="新能源车企：PE vs 营收增速",
            data={
                "x": [25, 60, 30, 80, 120],
                "y": [29, 10, 35, 50, -5],
                "labels": ["比亚迪", "特斯拉", "宁德时代", "理想", "蔚来"],
            },
            xlabel="PE(倍)",
            ylabel="营收增速(%)",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_bubble_sector(self):
        config = ChartConfig(
            chart_type=ChartType.BUBBLE,
            title="新能源汽车产业链：增速vs盈利能力",
            data={
                "sectors": [
                    {"name": "整车", "x": 5, "y": 8, "size": 3},
                    {"name": "电池", "x": 7, "y": 6, "size": 2.5},
                    {"name": "芯片", "x": 8, "y": 9, "size": 1.5},
                    {"name": "充电桩", "x": 6, "y": 4, "size": 1},
                ],
            },
            xlabel="行业增速(%)",
            ylabel="盈利能力评分",
        )
        self._assert_chart_ok(self.gen.generate(config))

    def test_quadrant_competition(self):
        config = ChartConfig(
            chart_type=ChartType.QUADRANT,
            title="新能源汽车竞争格局四象限",
            data={
                "players": [
                    {"name": "比亚迪", "x": 8, "y": 9, "size": 5},
                    {"name": "特斯拉", "x": 7, "y": 7, "size": 4},
                    {"name": "理想", "x": 6, "y": 5, "size": 2},
                    {"name": "蔚来", "x": 4, "y": 3, "size": 1.5},
                    {"name": "小鹏", "x": 3, "y": 4, "size": 1},
                ],
            },
            xlabel="市场规模",
            ylabel="盈利能力",
        )
        self._assert_chart_ok(self.gen.generate(config))


class TestComposeChartFromRealTableData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.report = _load_report()

    def test_table_data_to_bar(self):
        section = self.report["sections"][0]
        tables = self.agent._extract_tables(section["content"])
        self.assertGreaterEqual(len(tables), 1)
        t = tables[0]
        cat_col = 0
        for col_idx in t.numeric_columns:
            vals = self.agent._extract_numeric_values(t, col_idx)
            if any(v != 0 for v in vals):
                data = {
                    "categories": [r[cat_col] if cat_col < len(r) else f"R{i}" for i, r in enumerate(t.rows)],
                    "values": vals,
                }
                self.assertFalse(self.agent._has_empty_chart_data(data, ChartType.BAR))
                break


class TestComposeChartWithNoneInSeries(unittest.TestCase):
    def setUp(self):
        self.gen = ChartGenerator(output_dir="output/test_real_charts")
        os.makedirs("output/test_real_charts", exist_ok=True)

    def test_grouped_bar_with_none_renders(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="比亚迪vs宁德时代：季度营收对比",
            data={
                "categories": ["2023Q3", "2023Q4", "2024Q1", "2024Q2"],
                "series": [
                    {"name": "比亚迪", "values": [1800, 2100, 1502, 1762]},
                    {"name": "宁德时代", "values": [None, 1100, 900, 1050]},
                ],
            },
            ylabel="亿元",
        )
        result = self.gen.generate(config)
        self.assertTrue(result.success, f"None in series should render: {result.error}")
        self.assertIsNotNone(result.image_path)


class TestValueRangeWithRealData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_large_revenue_values_pass(self):
        plan = ChartPlan(
            chart_type=ChartType.BAR,
            title="营收对比",
            subtitle="",
            data={"categories": ["2023", "2024"], "values": [602315000000, 777102000000]},
            caption="",
            xlabel="",
            ylabel="",
            confidence=0.8,
            reason="",
            insertion_anchor="",
            anchor_type="section_end",
            unit="元",
        )
        self.assertTrue(self.agent._check_value_range(plan))

    def test_mixed_revenue_profit_ratio_under_1000_passes(self):
        plan = ChartPlan(
            chart_type=ChartType.BAR,
            title="营收vs净利润",
            subtitle="",
            data={"categories": ["2023"], "values": [602315000000, 31244000000]},
            caption="",
            xlabel="",
            ylabel="",
            confidence=0.8,
            reason="",
            insertion_anchor="",
            anchor_type="section_end",
            unit="元",
        )
        self.assertTrue(self.agent._check_value_range(plan))

    def test_extreme_ratio_over_1000_fails(self):
        plan = ChartPlan(
            chart_type=ChartType.BAR,
            title="营收vs微小值",
            subtitle="",
            data={"categories": ["2023"], "values": [602315000000, 1000]},
            caption="",
            xlabel="",
            ylabel="",
            confidence=0.8,
            reason="",
            insertion_anchor="",
            anchor_type="section_end",
            unit="元",
        )
        self.assertFalse(self.agent._check_value_range(plan))


if __name__ == "__main__":
    unittest.main()
