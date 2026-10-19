# -*- coding: utf-8 -*-
"""StockDataSkill 修订回归（2026-10 实测后）。

实证背景：EastMoney push2 域在本网络被服务端断连；akshare THS 摘要
schema 漂移（长表→宽表）；stock_zh_a_hist head(120) 取到最旧数据。
修订：腾讯/同花顺/东财指标兜底 + schema 适配 + tail 修正 + format_data
list 形状归一。
"""
import asyncio
import unittest
from unittest.mock import patch, MagicMock

from src.skills.analysis.stock_data import StockDataSkill


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _CacheIsolated(unittest.TestCase):
    """StockDataSkill._memory_cache 是类级共享——每个用例必须隔离。"""

    def setUp(self):
        StockDataSkill._memory_cache.clear()


class TestKeyMetricsWideSchema(_CacheIsolated):
    """THS 摘要 schema 漂移：宽表（行=报告期，列=中文指标名）。"""

    def test_wide_format_parsed_into_periods(self):
        import pandas as pd
        df = pd.DataFrame([
            {"报告期": "2024-09-30", "净利润": "608.28亿", "净利润同比增长率": "15.04%",
             "扣非净利润": False, "营业总收入": "990.5亿"},
            {"报告期": "2024-06-30", "净利润": "406.6亿", "净利润同比增长率": "14.31%",
             "扣非净利润": False, "营业总收入": "819.3亿"},
        ])
        skill = StockDataSkill()
        with patch("akshare.stock_financial_abstract_ths", return_value=df):
            r = _run(skill.execute(action="key_metrics", symbol="600519"))
        self.assertTrue(r["success"])
        periods = r["data"]["periods"]
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0]["报告期"], "2024-09-30")
        self.assertEqual(periods[0]["净利润"], "608.28亿")

    def test_legacy_long_format_still_supported(self):
        import pandas as pd
        df = pd.DataFrame([{"指标名称": "营业总收入", "指标值": "990.5亿"}])
        skill = StockDataSkill()
        with patch("akshare.stock_financial_abstract_ths", return_value=df):
            r = _run(skill.execute(action="key_metrics", symbol="600519"))
        self.assertTrue(r["success"])
        self.assertEqual(r["data"].get("营业总收入"), "990.5亿")


class TestPriceHistoryFixes(_CacheIsolated):
    def test_recency_tail_not_head(self):
        """head(120) 取到最旧一段的缺陷：升序 df 必须取 tail(120)。"""
        import pandas as pd
        dates = [f"2020-{m:02d}-01" for m in range(1, 13)] * 12  # 144 行升序
        df = pd.DataFrame({"日期": dates, "收盘": range(144)})
        skill = StockDataSkill()
        with patch("akshare.stock_zh_a_hist", return_value=df):
            r = _run(skill.execute(action="price_history", symbol="600519"))
        self.assertTrue(r["success"])
        records = r["data"]
        self.assertEqual(len(records), 120)
        self.assertEqual(records[-1]["日期"], dates[-1], "必须包含最近日期")
        self.assertEqual(records[0]["日期"], dates[24], "应剔除最旧 24 行")

    def test_format_data_accepts_list_shape(self):
        skill = StockDataSkill()
        records = [{"日期": "2026-10-19", "开盘": 1322.5, "收盘": 1324.97,
                    "最高": 1348.6, "最低": 1321.0, "成交量": 3972894}]
        out = skill.format_data(records, "price_history", "600519")
        self.assertIn("股价数据", out)
        self.assertIn("2026-10-19", out)


class TestCompanyInfoFallback(_CacheIsolated):
    def test_tencent_fallback_when_push2_dead(self):
        skill = StockDataSkill()
        quote = {"股票简称": "贵州茅台", "股票代码": "600519", "最新价": 1324.97,
                 "市盈率": 20.34, "总市值": 16563.21}
        with patch.object(skill, "_tencent_quote", return_value=quote):
            with patch("akshare.stock_individual_info_em",
                       side_effect=ConnectionError("RemoteDisconnected")):
                r = _run(skill.execute(action="company_info", symbol="600519"))
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["股票简称"], "贵州茅台")
        self.assertIn("tencent", r["source"])

    def test_industry_fallback_renders_quote(self):
        skill = StockDataSkill()
        data = {"industry": "", "symbol": "600519",
                "quote": {"股票简称": "贵州茅台", "最新价": 1324.97}}
        out = skill.format_data(data, "industry_comparison", "600519")
        self.assertIn("行情概览", out)
        self.assertIn("贵州茅台", out)


class TestFinancialsFallback(_CacheIsolated):
    def test_em_failure_falls_back_to_ths_and_indicators(self):
        import pandas as pd
        skill = StockDataSkill()

        def _fail(*a, **k):
            raise TypeError("'NoneType' object is not subscriptable")

        ths_df = pd.DataFrame([
            {"报告期": "2024-09-30", "净利润": "608.28亿", "营业总收入": "990.5亿"},
            {"报告期": "2024-06-30", "净利润": "406.6亿", "营业总收入": "819.3亿"},
        ])
        ind_df = pd.DataFrame([
            {"日期": "2024-09-30", "摊薄每股收益(元)": "48.3", "净资产收益率(%)": "25.1"},
        ])
        with patch("akshare.stock_profit_sheet_by_report_em", side_effect=_fail), \
             patch("akshare.stock_balance_sheet_by_report_em", side_effect=_fail), \
             patch("akshare.stock_cash_flow_sheet_by_report_em", side_effect=_fail), \
             patch("akshare.stock_financial_abstract_ths", return_value=ths_df), \
             patch("akshare.stock_financial_analysis_indicator", return_value=ind_df):
            r = _run(skill.execute(action="financials", symbol="600519"))
        self.assertTrue(r["success"], f"兜底必须成功: {r.get('error')}")
        self.assertIn("ths_abstract", r["data"])
        self.assertIn("analysis_indicators", r["data"])
        fmt = skill.format_data(r["data"], "financials", "600519")
        self.assertIn("核心财务指标-同花顺", fmt)
        self.assertIn("608.28亿", fmt)


if __name__ == "__main__":
    unittest.main()
