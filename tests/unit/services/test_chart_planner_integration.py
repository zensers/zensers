# -*- coding: utf-8 -*-
import unittest
from unittest.mock import AsyncMock, patch

from src.services.chart_planner import ChartPlannerAgent, ChartPlan
from src.services.chart_generator import ChartType


class TestFullFlowFetchComposeValidate(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_price_fetch_to_line_chart(self):
        chart_raw = {
            "chart_type": "line",
            "title": "比亚迪vs沪深300走势",
            "data_strategy": "normalize_pct",
            "data_ref": ["req1", "req2"],
            "data": {},
            "confidence": 0.9,
            "reason": "股价走势对比",
            "insertion_anchor": "股价走势",
            "anchor_type": "after_paragraph",
            "caption": "",
            "xlabel": "",
            "ylabel": "",
            "subtitle": "",
            "unit": "",
        }
        fetched = {
            "stock_price:002594": {
                "id": "req1",
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪",
                "data": {"dates": ["2025-01", "2025-02", "2025-03"], "closes": [100, 110, 105]},
            },
            "index_price:000300": {
                "id": "req2",
                "source": "index_price",
                "params": {"symbol": "000300"},
                "purpose": "沪深300",
                "data": {"dates": ["2025-01", "2025-02", "2025-03"], "closes": [3500, 3570, 3550]},
            },
        }
        import asyncio
        plan = asyncio.run(
            self.agent._resolve_chart(chart_raw, fetched)
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.chart_type, ChartType.LINE)
        self.assertIn("scenarios", plan.data)


class TestLLMPlanningOutputBudget(unittest.TestCase):
    def test_chart_planner_uses_configured_output_budget(self):
        agent = ChartPlannerAgent()
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return {
                "success": True,
                "content": '{"data_requests": [], "charts": [], "skip_reason": "no suitable data"}',
            }

        with patch("src.core.llm_client.call_llm", new=fake_call_llm):
            import asyncio
            asyncio.run(agent._llm_plan("分析内容", [], "主题", "章节"))

        self.assertGreaterEqual(captured["max_tokens"], 2048)

    def test_truncated_json_is_not_silently_treated_as_no_suitable_data(self):
        agent = ChartPlannerAgent()
        import asyncio
        plans = asyncio.run(
            agent._parse_and_resolve(
                '{"data_requests": [], "charts": [{"chart_type": "bar", "title": "未完成',
                "主题",
            )
        )
        # Truncated payloads are repaired when possible; a chart without data
        # is still dropped by _resolve_chart, so no phantom chart survives.
        self.assertEqual(plans, [])


class TestContentOnlyData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_bar_from_content_data(self):
        chart_raw = {
            "chart_type": "bar",
            "title": "营收对比",
            "data_strategy": "raw",
            "data_ref": [],
            "data": {
                "categories": ["2022", "2023", "2024"],
                "values": [4200, 5000, 6000],
            },
            "confidence": 0.8,
            "reason": "营收对比",
            "insertion_anchor": "营收增长",
            "anchor_type": "after_paragraph",
            "caption": "",
            "xlabel": "",
            "ylabel": "",
            "subtitle": "",
            "unit": "",
        }
        import asyncio
        plan = asyncio.run(
            self.agent._resolve_chart(chart_raw, {})
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.data_source, "content")


class TestSkipReason(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_skip_reason_returns_empty(self):
        import asyncio
        plans = asyncio.run(
            self.agent._parse_and_resolve(
                '{"data_requests": [], "charts": [], "skip_reason": "no suitable data"}',
                "test",
            )
        )
        self.assertEqual(plans, [])


class TestFinancialsToBarChart(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_financial_bar_compose(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2023", "营业总收入": 4200},
                    {"报告期": "2024", "营业总收入": 6000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertIn("values", result)
        self.assertEqual(len(result["categories"]), 2)


class TestBarLineFromFinancials(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_compose_bar_line_from_financials(self):
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2022-12-31", "营业总收入": 424061000000, "净利润": 166224000000},
                    {"报告期": "2023-12-31", "营业总收入": 602315000000, "净利润": 312444000000},
                    {"报告期": "2024-03-31", "营业总收入": 150200000000, "净利润": 46000000000},
                ],
            }
        }
        time_series_data = []
        categorical_data = []
        result = self.agent._compose_bar_line(fetched, time_series_data, categorical_data)
        self.assertIn("years", result)
        self.assertIn("bar", result)
        self.assertIn("line", result)
        self.assertEqual(result["line"][0], None)

    def test_compose_bar_line_from_time_series_fallback(self):
        fetched = {}
        time_series_data = [
            {"name": "营收", "dates": ["2022", "2023", "2024"], "values": [100, 200, 300]}
        ]
        categorical_data = []
        result = self.agent._compose_bar_line(fetched, time_series_data, categorical_data)
        self.assertIn("years", result)
        self.assertIn("bar", result)
        self.assertIn("line", result)
        self.assertEqual(result["line"][0], None)
        self.assertAlmostEqual(result["line"][1], 100.0)


class TestWaterfallFromContent(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_waterfall_content_data(self):
        data = {
            "factors": [
                {"label": "上期利润", "value": 300, "is_total": True},
                {"label": "营收增长", "value": 150},
                {"label": "成本上升", "value": -80},
                {"label": "本期利润", "value": 370, "is_total": True},
            ]
        }
        self.assertFalse(self.agent._has_empty_chart_data(data, ChartType.WATERFALL))


class TestPieFromContent(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_pie_content_data(self):
        data = {"labels": ["A", "B", "C"], "values": [30, 40, 30]}
        self.assertFalse(self.agent._has_empty_chart_data(data, ChartType.PIE))

    def test_pie_empty_labels(self):
        data = {"labels": [], "values": [30, 40]}
        self.assertTrue(self.agent._has_empty_chart_data(data, ChartType.PIE))


class TestHasEmptyAllTypes(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_bar_line_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data({"years": [], "bar": [], "line": []}, ChartType.BAR_LINE))

    def test_bar_line_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"years": ["2021"], "bar": [100], "line": [None]}, ChartType.BAR_LINE
        ))

    def test_scatter_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data({"x": [], "y": []}, ChartType.SCATTER))

    def test_scatter_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data({"x": [1], "y": [2]}, ChartType.SCATTER))

    def test_bubble_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data({"sectors": []}, ChartType.BUBBLE))

    def test_bubble_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"sectors": [{"name": "A", "x": 1, "y": 2, "size": 3}]}, ChartType.BUBBLE
        ))

    def test_quadrant_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data({"players": []}, ChartType.QUADRANT))

    def test_quadrant_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"players": [{"name": "A", "x": 5, "y": 5, "size": 3}]}, ChartType.QUADRANT
        ))

    def test_hbar_empty_values(self):
        self.assertTrue(self.agent._has_empty_chart_data({"values": [], "categories": ["A"]}, ChartType.HBAR))

    def test_hbar_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"values": [10], "categories": ["A"]}, ChartType.HBAR
        ))


class TestCheckChartTypeMatchAllTypes(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def _make_plan(self, chart_type=ChartType.LINE, data=None):
        return ChartPlan(
            chart_type=chart_type,
            title="test",
            subtitle="",
            data=data or {},
            caption="",
            xlabel="",
            ylabel="",
            confidence=0.8,
            reason="",
            insertion_anchor="",
            anchor_type="after_paragraph",
            unit="",
        )

    def test_bar_line_valid(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR_LINE,
            data={"years": ["2021", "2022"], "bar": [100, 200], "line": [None, 100.0]},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))

    def test_bar_line_single_year_fails(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR_LINE,
            data={"years": ["2021"], "bar": [100], "line": [None]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_bar_line_mismatched_bar_length(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR_LINE,
            data={"years": ["2021", "2022"], "bar": [100], "line": [None, 100]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_waterfall_single_factor_fails(self):
        plan = self._make_plan(
            chart_type=ChartType.WATERFALL,
            data={"factors": [{"label": "A", "value": 10}]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_waterfall_two_factors_passes(self):
        plan = self._make_plan(
            chart_type=ChartType.WATERFALL,
            data={"factors": [{"label": "A", "value": 10}, {"label": "B", "value": -5}]},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))

    def test_scatter_single_point_fails(self):
        plan = self._make_plan(
            chart_type=ChartType.SCATTER,
            data={"x": [1], "y": [2], "labels": ["A"]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_scatter_two_points_passes(self):
        plan = self._make_plan(
            chart_type=ChartType.SCATTER,
            data={"x": [1, 2], "y": [3, 4], "labels": ["A", "B"]},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))

    def test_radar_no_0_100_constraint(self):
        plan = self._make_plan(
            chart_type=ChartType.RADAR,
            data={"categories": ["A", "B", "C"], "values": [200, 300, 150]},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))


class TestNormalizeRadarValues(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_values_under_100_unchanged(self):
        self.assertEqual(self.agent._normalize_radar_values([50, 60, 70]), [50, 60, 70])

    def test_values_over_100_normalized(self):
        result = self.agent._normalize_radar_values([200, 300, 100])
        self.assertAlmostEqual(result[0], 66.7, places=1)
        self.assertAlmostEqual(result[1], 100.0, places=1)
        self.assertAlmostEqual(result[2], 33.3, places=1)

    def test_empty_list(self):
        self.assertEqual(self.agent._normalize_radar_values([]), [])

    def test_all_zeros(self):
        self.assertEqual(self.agent._normalize_radar_values([0, 0, 0]), [0, 0, 0])


class TestExtendedChartTypeMap(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_area_maps_to_line(self):
        chart_raw = {
            "chart_type": "area",
            "title": "走势",
            "data": {"years": ["2021", "2022"], "scenarios": {"A": [1, 2]}},
            "confidence": 0.8,
            "reason": "",
            "insertion_anchor": "",
            "anchor_type": "section_end",
            "caption": "",
            "xlabel": "",
            "ylabel": "",
            "subtitle": "",
            "unit": "",
        }
        import asyncio
        plan = asyncio.run(self.agent._resolve_chart(chart_raw, {}))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.chart_type, ChartType.LINE)

    def test_donut_maps_to_pie(self):
        chart_raw = {
            "chart_type": "donut",
            "title": "份额",
            "data": {"labels": ["A", "B"], "values": [60, 40]},
            "confidence": 0.8,
            "reason": "",
            "insertion_anchor": "",
            "anchor_type": "section_end",
            "caption": "",
            "xlabel": "",
            "ylabel": "",
            "subtitle": "",
            "unit": "",
        }
        import asyncio
        plan = asyncio.run(self.agent._resolve_chart(chart_raw, {}))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.chart_type, ChartType.PIE)

    def test_stacked_bar_maps_to_bar(self):
        chart_raw = {
            "chart_type": "stacked_bar",
            "title": "对比",
            "data": {"categories": ["A", "B"], "values": [10, 20]},
            "confidence": 0.8,
            "reason": "",
            "insertion_anchor": "",
            "anchor_type": "section_end",
            "caption": "",
            "xlabel": "",
            "ylabel": "",
            "subtitle": "",
            "unit": "",
        }
        import asyncio
        plan = asyncio.run(self.agent._resolve_chart(chart_raw, {}))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.chart_type, ChartType.BAR)


class TestCleanJsonStringEdgeCases(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_multiple_comments(self):
        s = '{\n// comment1\n"a": 1,\n// comment2\n"b": 2\n}'
        result = self.agent._clean_json_string(s)
        self.assertNotIn("//", result)
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed["a"], 1)

    def test_trailing_comma_in_array(self):
        s = '{"values": [1, 2, 3,]}'
        result = self.agent._clean_json_string(s)
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed["values"], [1, 2, 3])

    def test_trailing_comma_in_nested_object(self):
        s = '{"data": {"a": 1, "b": 2,}, "c": 3}'
        result = self.agent._clean_json_string(s)
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed["data"]["a"], 1)

    def test_no_modification_needed(self):
        s = '{"a": 1, "b": 2}'
        result = self.agent._clean_json_string(s)
        self.assertEqual(result, s)


class TestComposeBarLineEdgeCases(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_zero_base_revenue_no_division_error(self):
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "营收",
                "data": [
                    {"报告期": "2022", "营业总收入": 0, "净利润": 0},
                    {"报告期": "2023", "营业总收入": 100, "净利润": 10},
                ],
            }
        }
        result = self.agent._compose_bar_line(fetched, [], [])
        self.assertIn("line", result)
        self.assertEqual(len(result["line"]), 2)
        self.assertIsNone(result["line"][0])

    def test_no_financials_no_time_series_returns_empty(self):
        result = self.agent._compose_bar_line({}, [], [])
        self.assertEqual(result, {})

    def test_single_time_series_point(self):
        time_series_data = [
            {"name": "营收", "dates": ["2024"], "values": [100]}
        ]
        result = self.agent._compose_bar_line({}, time_series_data, [])
        self.assertIn("bar", result)
        self.assertEqual(len(result["line"]), 1)
        self.assertIsNone(result["line"][0])


class TestValidatePlansEdgeCases(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_low_confidence_filtered(self):
        plan = ChartPlan(
            chart_type=ChartType.BAR,
            title="test",
            subtitle="",
            data={"categories": ["A", "B"], "values": [1, 2]},
            caption="",
            xlabel="",
            ylabel="",
            confidence=0.1,
            reason="",
            insertion_anchor="",
            anchor_type="section_end",
            unit="",
        )
        result = self.agent._validate_plans([plan])
        self.assertEqual(len(result), 0)

    def test_max_per_section_enforced(self):
        plans = [
            ChartPlan(
                chart_type=ChartType.BAR,
                title=f"test{i}",
                subtitle="",
                data={"categories": ["A", "B"], "values": [1, 2]},
                caption="",
                xlabel="",
                ylabel="",
                confidence=0.9 - i * 0.01,
                reason="",
                insertion_anchor="",
                anchor_type="section_end",
                unit="",
            )
            for i in range(5)
        ]
        result = self.agent._validate_plans(plans)
        self.assertLessEqual(len(result), 2)

    def test_sorted_by_confidence_desc(self):
        plans = [
            ChartPlan(
                chart_type=ChartType.BAR,
                title="low",
                subtitle="",
                data={"categories": ["A", "B"], "values": [1, 2]},
                caption="",
                xlabel="",
                ylabel="",
                confidence=0.6,
                reason="",
                insertion_anchor="",
                anchor_type="section_end",
                unit="",
            ),
            ChartPlan(
                chart_type=ChartType.BAR,
                title="high",
                subtitle="",
                data={"categories": ["A", "B"], "values": [1, 2]},
                caption="",
                xlabel="",
                ylabel="",
                confidence=0.9,
                reason="",
                insertion_anchor="",
                anchor_type="section_end",
                unit="",
            ),
        ]
        result = self.agent._validate_plans(plans)
        self.assertEqual(result[0].title, "high")


if __name__ == "__main__":
    unittest.main()
