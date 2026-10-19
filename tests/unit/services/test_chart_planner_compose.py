# -*- coding: utf-8 -*-
import unittest

from src.services.chart_planner import ChartPlannerAgent
from src.services.chart_generator import ChartType


class TestComposePriceData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_single_price_series(self):
        chart_raw = {"chart_type": "line", "data_strategy": "raw"}
        fetched = {
            "stock_price:002594": {
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪股价走势",
                "data": {"dates": ["2025-01", "2025-02"], "closes": [100, 110]},
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("scenarios", result)
        self.assertIn("years", result)

    def test_normalize_pct_strategy(self):
        chart_raw = {"chart_type": "line", "data_strategy": "normalize_pct"}
        fetched = {
            "stock_price:002594": {
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪",
                "data": {"dates": ["2025-01", "2025-02", "2025-03"], "closes": [100, 110, 105]},
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "normalize_pct")
        self.assertEqual(result["unit"], "%")
        vals = list(result["scenarios"].values())[0]
        self.assertEqual(vals[0], 100)

    def test_multiple_price_series(self):
        chart_raw = {"chart_type": "line", "data_strategy": "normalize_pct"}
        fetched = {
            "stock_price:002594": {
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪",
                "data": {"dates": ["2025-01", "2025-02"], "closes": [100, 110]},
            },
            "index_price:000300": {
                "source": "index_price",
                "params": {"symbol": "000300"},
                "purpose": "沪深300",
                "data": {"dates": ["2025-01", "2025-02"], "closes": [3500, 3570]},
            },
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "normalize_pct")
        self.assertEqual(len(result["scenarios"]), 2)


class TestComposeFinancialData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_financial_bar_chart(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2024Q1", "营业总收入": 150000000000},
                    {"报告期": "2024Q2", "营业总收入": 170000000000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertIn("values", result)

    def test_financial_line_chart(self):
        chart_raw = {"chart_type": "line", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪营收",
                "data": [
                    {"报告期": "2024Q1", "营业总收入": 150000000000},
                    {"报告期": "2024Q2", "营业总收入": 170000000000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("scenarios", result)
        self.assertIn("years", result)


class TestComposeSearchData(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_search_few_categories_bar(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "search:query1": {
                "source": "search",
                "params": {"query": "test"},
                "purpose": "销量数据",
                "data": {"dates": ["1月", "2月", "3月"], "values": [100, 120, 130]},
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)

    def test_search_many_dates_line(self):
        chart_raw = {"chart_type": "line", "data_strategy": "raw"}
        fetched = {
            "search:query1": {
                "source": "search",
                "params": {"query": "test"},
                "purpose": "月度数据",
                "data": {"dates": [f"m{i}" for i in range(15)], "values": list(range(15))},
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("scenarios", result)


class TestAlignTimeSeries(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_aligns_overlapping_dates(self):
        series = [
            {"name": "A", "dates": ["2025-01", "2025-03"], "values": [100, 120]},
            {"name": "B", "dates": ["2025-01", "2025-02"], "values": [200, 210]},
        ]
        result = self.agent._align_time_series(series)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["dates"], ["2025-01", "2025-02", "2025-03"])
        self.assertEqual(result[0]["values"], [100, 100, 120])
        self.assertEqual(result[1]["values"], [200, 210, 210])

    def test_empty_input(self):
        result = self.agent._align_time_series([])
        self.assertEqual(result, [])

    def test_single_series(self):
        series = [
            {"name": "A", "dates": ["2025-01", "2025-02"], "values": [100, 110]},
        ]
        result = self.agent._align_time_series(series)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["values"], [100, 110])


class TestComposeCategoricalMultiSeries(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_overlapping_categories(self):
        cat_data = [
            {"name": "比亚迪", "categories": ["2022", "2023", "2024"], "values": [100, 120, 130]},
            {"name": "宁德时代", "categories": ["2023", "2024"], "values": [200, 210]},
        ]
        result = self.agent._compose_categorical(cat_data, ChartType.BAR)
        self.assertEqual(result["categories"], ["2022", "2023", "2024"])
        self.assertEqual(len(result["series"]), 2)
        self.assertEqual(result["series"][0]["values"], [100, 120, 130])
        self.assertEqual(result["series"][1]["values"][0], None)
        self.assertEqual(result["series"][1]["values"][1], 200)

    def test_single_series(self):
        cat_data = [
            {"name": "比亚迪", "categories": ["A", "B"], "values": [10, 20]},
        ]
        result = self.agent._compose_categorical(cat_data, ChartType.BAR)
        self.assertNotIn("series", result)
        self.assertEqual(result["values"], [10, 20])


if __name__ == "__main__":
    unittest.main()
