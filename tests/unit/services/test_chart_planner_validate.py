# -*- coding: utf-8 -*-
import unittest

from src.services.chart_planner import ChartPlannerAgent, ChartPlan
from src.services.chart_generator import ChartType


class TestCleanJsonString(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_removes_single_line_comments(self):
        result = self.agent._clean_json_string('{\n  // comment\n  "a": 1\n}')
        self.assertNotIn("// comment", result)
        self.assertIn('"a": 1', result)

    def test_removes_trailing_comma_before_closing_brace(self):
        result = self.agent._clean_json_string('{"a": 1,}')
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed, {"a": 1})

    def test_removes_trailing_comma_before_closing_bracket(self):
        result = self.agent._clean_json_string('{"a": [1, 2,]}')
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed, {"a": [1, 2]})

    def test_preserves_normal_json(self):
        original = '{"a": 1, "b": [2, 3]}'
        result = self.agent._clean_json_string(original)
        self.assertEqual(result, original)

    def test_combined_comment_and_trailing_comma(self):
        result = self.agent._clean_json_string('{\n  // comment\n  "a": [1,],\n}')
        parsed = __import__("json").loads(result)
        self.assertEqual(parsed, {"a": [1]})


class TestCheckValueRange(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def _make_plan(self, chart_type=ChartType.LINE, unit="", data=None):
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
            unit=unit,
        )

    def test_waterfall_always_passes(self):
        plan = self._make_plan(chart_type=ChartType.WATERFALL, data={"factors": []})
        self.assertTrue(self.agent._check_value_range(plan))

    def test_pct_unit_scenarios_under_500(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            unit="%",
            data={"scenarios": {"A": [100, 120, 95]}},
        )
        self.assertTrue(self.agent._check_value_range(plan))

    def test_pct_unit_scenarios_over_500_still_passes_general_check(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            unit="%",
            data={"scenarios": {"A": [100, 600]}},
        )
        self.assertTrue(self.agent._check_value_range(plan))

    def test_pct_unit_scenarios_extreme_rejected(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            unit="%",
            data={"scenarios": {"A": [100, 2e11]}},
        )
        self.assertFalse(self.agent._check_value_range(plan))

    def test_huge_value_rejected(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR,
            data={"values": [1, 1e11], "categories": ["A", "B"]},
        )
        self.assertFalse(self.agent._check_value_range(plan))

    def test_ratio_over_1000_rejected(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR,
            data={"values": [1, 2000], "categories": ["A", "B"]},
        )
        self.assertFalse(self.agent._check_value_range(plan))

    def test_empty_data_returns_false(self):
        plan = self._make_plan(data={})
        self.assertFalse(self.agent._check_value_range(plan))

    def test_no_numeric_values_returns_true(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR,
            data={"categories": ["A", "B"]},
        )
        self.assertTrue(self.agent._check_value_range(plan))

    def test_normal_values_pass(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR,
            data={"values": [10, 20, 30], "categories": ["A", "B", "C"]},
        )
        self.assertTrue(self.agent._check_value_range(plan))


class TestHasEmptyChartData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_line_empty_scenarios(self):
        self.assertTrue(self.agent._has_empty_chart_data({"scenarios": {}}, ChartType.LINE))

    def test_line_nonempty_scenarios(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"scenarios": {"A": [1, 2, 3]}}, ChartType.LINE
        ))

    def test_bar_empty_values(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"values": [], "categories": ["A"]}, ChartType.BAR
        ))

    def test_bar_nonempty_values(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"values": [10], "categories": ["A"]}, ChartType.BAR
        ))

    def test_bar_empty_categories(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"values": [10], "categories": []}, ChartType.BAR
        ))

    def test_bar_with_series(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"series": [{"values": []}]}, ChartType.BAR
        ))
        self.assertFalse(self.agent._has_empty_chart_data(
            {"series": [{"values": [10]}]}, ChartType.BAR
        ))

    def test_radar_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"values": [], "categories": ["A"]}, ChartType.RADAR
        ))

    def test_waterfall_empty(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"factors": []}, ChartType.WATERFALL
        ))

    def test_waterfall_nonempty(self):
        self.assertFalse(self.agent._has_empty_chart_data(
            {"factors": [{"label": "A", "value": 10}]}, ChartType.WATERFALL
        ))

    def test_none_data(self):
        self.assertTrue(self.agent._has_empty_chart_data(None, ChartType.LINE))

    def test_pie_with_labels_key(self):
        self.assertTrue(self.agent._has_empty_chart_data(
            {"values": [], "labels": ["A"]}, ChartType.PIE
        ))


class TestCheckChartTypeMatch(unittest.TestCase):
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

    def test_line_needs_at_least_2_years(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            data={"years": ["2025-01"], "scenarios": {"A": [100]}},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_line_passes_with_2_years(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            data={"years": ["2025-01", "2025-02"], "scenarios": {"A": [100, 110]}},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))

    def test_line_mismatched_scenario_length(self):
        plan = self._make_plan(
            chart_type=ChartType.LINE,
            data={"years": ["2025-01", "2025-02"], "scenarios": {"A": [100]}},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_pie_rejects_negative(self):
        plan = self._make_plan(
            chart_type=ChartType.PIE,
            data={"values": [10, -5], "categories": ["A", "B"]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_pie_rejects_over_6(self):
        plan = self._make_plan(
            chart_type=ChartType.PIE,
            data={"values": list(range(7)), "categories": [str(i) for i in range(7)]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_bar_rejects_over_12_categories(self):
        plan = self._make_plan(
            chart_type=ChartType.BAR,
            data={"values": list(range(13)), "categories": [str(i) for i in range(13)]},
        )
        self.assertFalse(self.agent._check_chart_type_match(plan))

    def test_radar_valid(self):
        plan = self._make_plan(
            chart_type=ChartType.RADAR,
            data={"categories": ["A", "B", "C"], "values": [50, 60, 70]},
        )
        self.assertTrue(self.agent._check_chart_type_match(plan))


if __name__ == "__main__":
    unittest.main()
