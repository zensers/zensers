# -*- coding: utf-8 -*-
import unittest
from unittest.mock import AsyncMock, patch

from src.services.chart_planner import ChartPlannerAgent
from src.services.chart_generator import ChartType


class TestNormalizePriceRecords(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_sorts_by_date_ascending(self):
        records = [
            {"日期": "2025-06-01", "收盘": 200},
            {"日期": "2025-06-03", "收盘": 210},
            {"日期": "2025-06-02", "收盘": 205},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(result["dates"], ["2025-06-01", "2025-06-02", "2025-06-03"])
        self.assertEqual(result["closes"], [200, 205, 210])

    def test_deduplicates_same_date(self):
        records = [
            {"日期": "2025-06-01", "收盘": 200},
            {"日期": "2025-06-01", "收盘": 210},
            {"日期": "2025-06-02", "收盘": 205},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(len(result["dates"]), 2)
        self.assertEqual(result["closes"][0], 210)

    def test_uses_close_key_for_index(self):
        records = [
            {"date": "2025-06-01", "close": 3000},
            {"date": "2025-06-02", "close": 3050},
        ]
        result = self.agent._normalize_price_records(records, is_index=True)
        self.assertEqual(result["dates"], ["2025-06-01", "2025-06-02"])
        self.assertEqual(result["closes"], [3000, 3050])

    def test_skips_invalid_close(self):
        records = [
            {"日期": "2025-06-01", "收盘": "N/A"},
            {"日期": "2025-06-02", "收盘": 205},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(len(result["dates"]), 1)
        self.assertEqual(result["closes"], [205])

    def test_empty_records(self):
        result = self.agent._normalize_price_records([])
        self.assertEqual(result["dates"], [])
        self.assertEqual(result["closes"], [])


class TestFormatIndexSymbol(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_sh_prefix_kept(self):
        self.assertEqual(self.agent._format_index_symbol("sh000300"), "sh000300")

    def test_sz_prefix_kept(self):
        self.assertEqual(self.agent._format_index_symbol("sz399006"), "sz399006")

    def test_399_gets_sz_prefix(self):
        self.assertEqual(self.agent._format_index_symbol("399006"), "sz399006")

    def test_other_gets_sh_prefix(self):
        self.assertEqual(self.agent._format_index_symbol("000300"), "sh000300")

    def test_strips_whitespace(self):
        self.assertEqual(self.agent._format_index_symbol("  000300  "), "sh000300")


class TestSanitizeParams(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_clamps_days_max(self):
        result = self.agent._sanitize_params("stock_price", {"symbol": "002594", "days": 9999})
        self.assertLessEqual(result["days"], 365)

    def test_clamps_days_min(self):
        result = self.agent._sanitize_params("stock_price", {"symbol": "002594", "days": -5})
        self.assertEqual(result["days"], 1)

    def test_clamps_periods_max(self):
        result = self.agent._sanitize_params("stock_financials", {"symbol": "002594", "periods": 20})
        self.assertLessEqual(result["periods"], 8)

    def test_clamps_periods_min(self):
        result = self.agent._sanitize_params("stock_financials", {"symbol": "002594", "periods": 0})
        self.assertEqual(result["periods"], 1)

    def test_invalid_days_defaults(self):
        result = self.agent._sanitize_params("stock_price", {"symbol": "002594", "days": "abc"})
        self.assertEqual(result["days"], 120)

    def test_invalid_periods_defaults(self):
        result = self.agent._sanitize_params("stock_financials", {"symbol": "002594", "periods": "abc"})
        self.assertEqual(result["periods"], 4)

    def test_strips_symbol(self):
        result = self.agent._sanitize_params("stock_price", {"symbol": "  002594  ", "days": 120})
        self.assertEqual(result["symbol"], "002594")


class TestIsAShareSymbol(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_valid_6_digit(self):
        self.assertTrue(self.agent._is_a_share_symbol("002594"))

    def test_valid_6_digit_shanghai(self):
        self.assertTrue(self.agent._is_a_share_symbol("600519"))

    def test_us_stock_ticker(self):
        self.assertFalse(self.agent._is_a_share_symbol("TSLA"))

    def test_short_digit(self):
        self.assertFalse(self.agent._is_a_share_symbol("12345"))

    def test_long_digit(self):
        self.assertFalse(self.agent._is_a_share_symbol("1234567"))

    def test_empty(self):
        self.assertFalse(self.agent._is_a_share_symbol(""))

    def test_whitespace_only(self):
        self.assertFalse(self.agent._is_a_share_symbol("   "))

    def test_strips_whitespace(self):
        self.assertTrue(self.agent._is_a_share_symbol("  002594  "))


class TestStockSymbolCanonicalization(unittest.IsolatedAsyncioTestCase):
    async def test_company_alias_is_resolved_before_akshare_fetch(self):
        agent = ChartPlannerAgent()
        resolver = AsyncMock()
        resolver.resolve.return_value = [
            type("Entity", (), {"resolved_code": "002594"})()
        ]
        impl = AsyncMock(return_value={"dates": ["2026-01-01"], "closes": [100]})

        with patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver), \
             patch.object(agent, "_fetch_stock_data_impl", impl):
            result = await agent._fetch_stock_data(
                "stock_price", {"symbol": "比亚迪股份有限公司", "days": 1}
            )

        self.assertEqual(result["closes"], [100])
        self.assertEqual(impl.await_args.args[2], "002594")
        resolver.resolve.assert_awaited_once_with("比亚迪股份有限公司")


class TestSearchBackedChartData(unittest.IsolatedAsyncioTestCase):
    async def test_search_source_retrieves_evidence_before_llm_extraction(self):
        agent = ChartPlannerAgent()
        search = AsyncMock()
        search.execute.return_value = {
            "success": True,
            "results": [{"title": "比亚迪销量", "snippet": "销量为 100 万辆", "url": "https://example.test"}],
        }
        llm = AsyncMock(return_value={
            "success": True,
            "content": '{"dates": ["2025"], "values": [100], "unit": "万辆"}',
        })

        with patch("src.skills.search_skill.MultiSearchSkill", return_value=search), \
             patch("src.core.llm_client.call_llm", new=llm):
            result = await agent._fetch_search_data({"query": "比亚迪销量"}, "新能源汽车")

        self.assertEqual(result["values"], [100])
        search.execute.assert_awaited_once()
        self.assertIn("比亚迪销量", llm.await_args.kwargs["prompt"])
        self.assertIn("销量为 100 万辆", llm.await_args.kwargs["prompt"])

    async def test_search_source_prefers_task_search_gateway_over_legacy_engines(self):
        gateway = AsyncMock()
        gateway.search.return_value = type("Response", (), {
            "success": True,
            "results": [type("Result", (), {
                "title": "AnySearch证据",
                "snippet": "销量为 120 万辆",
                "excerpt": "",
                "url": "https://example.test/anysearch",
                "source": "anysearch",
                "evidence_id": "ev_1",
                "provenance_id": "prov_1",
            })()],
        })()
        agent = ChartPlannerAgent(search_gateway=gateway)
        llm = AsyncMock(return_value={
            "success": True,
            "content": '{"dates": ["2025"], "values": [120], "unit": "万辆"}',
        })

        with patch("src.core.llm_client.call_llm", new=llm), \
             patch("src.skills.search_skill.MultiSearchSkill.execute", new_callable=AsyncMock) as legacy:
            result = await agent._fetch_search_data({"query": "比亚迪销量"}, "新能源汽车")

        self.assertEqual(result["values"], [120])
        gateway.search.assert_awaited_once()
        legacy.assert_not_awaited()


class TestPrepareLlmInput(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_short_content_preserved(self):
        content = "短内容"
        summary, _ = self.agent._prepare_llm_input(content, [])
        self.assertIn("短内容", summary)

    def test_long_content_tail_preserved(self):
        tail_marker = "TAIL_END_MARKER_XYZ"
        content = "A" * 2500 + tail_marker
        summary, _ = self.agent._prepare_llm_input(content, [])
        self.assertIn(tail_marker, summary)

    def test_long_content_head_preserved(self):
        head_marker = "HEAD_START_MARKER_XYZ"
        content = head_marker + "B" * 2500
        summary, _ = self.agent._prepare_llm_input(content, [])
        self.assertIn(head_marker, summary)

    def test_2000_char_content_no_truncation(self):
        content = "X" * 2000
        summary, _ = self.agent._prepare_llm_input(content, [])
        self.assertNotIn("中间省略", summary)

    def test_2001_char_content_has_omission(self):
        content = "X" * 2001
        summary, _ = self.agent._prepare_llm_input(content, [])
        self.assertIn("中间省略", summary)


class TestFilterFetchedByRef(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()
        self.fetched_data = {
            "stock_price:002594": {
                "id": "req1",
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪股价",
                "data": {"dates": ["2025-01"], "closes": [100]},
            },
            "index_price:000300": {
                "id": "req2",
                "source": "index_price",
                "params": {"symbol": "000300"},
                "purpose": "沪深300",
                "data": {"dates": ["2025-01"], "closes": [3500]},
            },
            "stock_price:600519": {
                "id": "req3",
                "source": "stock_price",
                "params": {"symbol": "600519"},
                "purpose": "贵州茅台",
                "data": {"dates": ["2025-01"], "closes": [1800]},
            },
        }

    def test_filters_by_ref_id(self):
        result = self.agent._filter_fetched_by_ref(self.fetched_data, ["req1", "req2"])
        self.assertEqual(len(result), 2)
        self.assertIn("stock_price:002594", result)
        self.assertIn("index_price:000300", result)

    def test_empty_ref_returns_all(self):
        result = self.agent._filter_fetched_by_ref(self.fetched_data, [])
        self.assertEqual(len(result), 3)

    def test_fallback_matches_by_key(self):
        no_id_data = {
            "stock_price:002594": {
                "source": "stock_price",
                "params": {"symbol": "002594"},
                "purpose": "比亚迪股价",
                "data": {"dates": ["2025-01"], "closes": [100]},
            }
        }
        result = self.agent._filter_fetched_by_ref(no_id_data, ["002594"])
        self.assertEqual(len(result), 1)

    def test_no_match_returns_all_fetched(self):
        result = self.agent._filter_fetched_by_ref(self.fetched_data, ["nonexistent_id"])
        self.assertEqual(len(result), 3)

    def test_nonexistent_ref_id_with_ids_present(self):
        result = self.agent._filter_fetched_by_ref(self.fetched_data, ["req99"])
        self.assertEqual(len(result), 3)


class TestNormalizePriceRecordsEdgeCases(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_empty_date_val_skipped(self):
        records = [
            {"日期": "", "收盘": 100},
            {"日期": "2025-06-02", "收盘": 200},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(len(result["dates"]), 1)
        self.assertEqual(result["closes"], [200])

    def test_mixed_date_key_formats(self):
        records = [
            {"日期": "2025-06-01", "收盘": 100},
            {"date": "2025-06-02", "close": 200},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(len(result["dates"]), 2)

    def test_date_with_timestamp_keeps_last_10(self):
        records = [
            {"日期": "2025-06-01 10:30:00", "收盘": 100},
            {"日期": "2025-06-02 14:00:00", "收盘": 200},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(len(result["dates"]), 2)

    def test_all_invalid_closes_returns_empty(self):
        records = [
            {"日期": "2025-06-01", "收盘": "N/A"},
            {"日期": "2025-06-02", "收盘": None},
        ]
        result = self.agent._normalize_price_records(records)
        self.assertEqual(result["dates"], [])
        self.assertEqual(result["closes"], [])


class TestFinancialsColumnNameFallback(unittest.TestCase):
    def setUp(self):
        self.agent = ChartPlannerAgent()

    def test_REPORT_DATE_fallback(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "营收",
                "data": [
                    {"REPORT_DATE": "2023-12-31", "TOTAL_OPERATE_INCOME": 4200},
                    {"REPORT_DATE": "2024-12-31", "TOTAL_OPERATE_INCOME": 6000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertEqual(len(result["categories"]), 2)
        self.assertIn("values", result)
        self.assertEqual(result["values"], [4200, 6000])

    def test_截止日期_fallback(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "营收",
                "data": [
                    {"截止日期": "2023", "营业收入": 4200},
                    {"截止日期": "2024", "营业收入": 6000},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertIn("categories", result)
        self.assertEqual(len(result["categories"]), 2)

    def test_no_period_key_skips_record(self):
        chart_raw = {"chart_type": "bar", "data_strategy": "raw"}
        fetched = {
            "stock_financials:002594": {
                "source": "stock_financials",
                "params": {"symbol": "002594"},
                "purpose": "营收",
                "data": [
                    {"unknown_col": "2023", "营业总收入": 4200},
                ],
            }
        }
        result = self.agent._compose_chart_data(chart_raw, fetched, "raw")
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
