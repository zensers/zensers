# -*- coding: utf-8 -*-
"""
Stock Charting Service

Converts stock data (akshare) to ChartGenerator-compatible chart configurations.
Supports: price trend charts, financial indicator trend charts, valuation band charts.
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType

logger = logging.getLogger(__name__)


class StockChartService:
    """
    Stock Charting Service
    
    Usage:
        1. StockDataSkill fetches data
        2. StockChartService converts to ChartConfig
        3. ChartGenerator generates images
    """
    
    def __init__(self, output_dir: str = "output/charts"):
        self.generator = ChartGenerator(output_dir=output_dir)
    
    def _extract_field(self, row: Dict, *keys) -> Any:
        for k in keys:
            if k in row and row[k] is not None:
                return row[k]
        return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Parse provider values without converting valid zeroes to missing data."""
        if value is None or isinstance(value, bool):
            return None
        try:
            text = str(value).strip().replace(',', '')
            if not text or text in {'-', '--', '—', 'N/A', 'NA', 'None'}:
                return None
            if text.startswith('(') and text.endswith(')'):
                text = '-' + text[1:-1]
            parsed = float(text.replace('%', ''))
            return parsed if math.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    def _prepare_price_rows(self, price_data: List[Dict], limit: int) -> List[Tuple[str, float]]:
        """Normalize, de-duplicate, and sort provider price rows chronologically."""
        by_date: Dict[str, float] = {}
        for row in price_data:
            date_val = self._extract_field(row, "date", "日期", "trade_date")
            close = self._extract_field(row, "close", "收盘", "close_price")
            if date_val is None:
                continue
            price = self._to_float(close)
            if price is None:
                continue
            date_text = str(date_val).strip()
            if date_text:
                # Keep the last provider row for a duplicated date.
                by_date[date_text] = price
        return sorted(by_date.items(), key=lambda item: item[0])[-limit:]
    async def price_chart(self, symbol: str, price_data: List[Dict]) -> Dict[str, Any]:
        """Generate price trend chart"""
        if not price_data:
            return {"success": False, "error": "No price data"}
        
        try:
            rows = self._prepare_price_rows(price_data, limit=60)
            dates = [date[:10] for date, _ in rows]
            prices = [price for _, price in rows]

            if not prices:
                return {"success": False, "error": "No valid price data"}
            
            config = ChartConfig(
                chart_type=ChartType.LINE,
                title=f"{symbol} Price Trend",
                data={
                    "years": dates,
                    "scenarios": {symbol: prices},
                },
                xlabel="Date",
                ylabel="Close Price",
                source="akshare/Stock Quotes",
            )
            result = self.generator.generate(config)
            return {"success": True, "chart_path": result.image_path, "chart_type": "line"}
        except Exception as e:
            logger.error(f"Price chart generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def financial_trend_chart(self, symbol: str, financial_data: Dict) -> Dict[str, Any]:
        """Generate financial trend chart (revenue/net profit trend)"""
        income = financial_data.get("income_statement", [])
        if not income or not isinstance(income, list):
            return {"success": False, "error": "No financial data"}
        
        try:
            periods = []
            revenue = []
            net_profit = []
            
            normalized = []
            for row in income:
                period = self._extract_field(row, "period", "报告期", "REPORT_DATE", "截止日期", "")
                if period is not None:
                    normalized.append((str(period), row))
            for period_text, row in sorted(normalized, key=lambda item: item[0])[-8:]:
                rev = self._extract_field(row, "revenue", "营业总收入", "营业收入", "TOTAL_OPERATE_INCOME")
                np_ = self._extract_field(row, "net_profit", "净利润", "归属净利润", "NET_PROFIT", "PARENT_NETPROFIT")
                revenue_value = self._to_float(rev)
                profit_value = self._to_float(np_)
                if revenue_value is None or profit_value is None:
                    continue
                periods.append(period_text[:10])
                revenue.append(revenue_value)
                net_profit.append(profit_value)
            
            if len(revenue) < 2:
                return {"success": False, "error": "Insufficient data"}
            
            config = ChartConfig(
                chart_type=ChartType.BAR_LINE,
                title=f"{symbol} Revenue & Net Profit Trend",
                data={
                    "years": periods,
                    "bar": revenue,
                    "line": net_profit,
                    "bar_label": "Revenue",
                    "line_label": "Net Profit",
                },
                xlabel="Period",
                ylabel="Amount (CNY)",
                source="akshare/Financial Statements",
            )
            result = self.generator.generate(config)
            return {"success": True, "chart_path": result.image_path, "chart_type": "bar_line"}
        except Exception as e:
            logger.error(f"Financial trend chart generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def valuation_band_chart(self, symbol: str, price_data: List[Dict]) -> Dict[str, Any]:
        """Generate valuation band chart"""
        if not price_data or len(price_data) < 20:
            return {"success": False, "error": "Insufficient data"}
        
        try:
            rows = self._prepare_price_rows(price_data, limit=120)
            dates = [date[:10] for date, _ in rows]
            prices = [price for _, price in rows]
            
            if len(prices) < 20:
                return {"success": False, "error": "Insufficient valid price data"}
            
            ordered = sorted(prices)
            lower = ordered[max(0, int(len(ordered) * 0.2) - 1)]
            upper = ordered[min(len(ordered) - 1, int(len(ordered) * 0.8))]
            
            config = ChartConfig(
                chart_type=ChartType.LINE,
                title=f"{symbol} Price & Historical Range",
                data={
                    "years": dates,
                    "scenarios": {
                        "Close Price": prices,
                        "P80 Historical Range": [upper] * len(prices),
                        "P20 Historical Range": [lower] * len(prices),
                    },
                },
                xlabel="Date",
                ylabel="Price",
                source="akshare/Stock Quotes",
            )
            result = self.generator.generate(config)
            return {
                "success": True,
                "chart_path": result.image_path,
                "chart_type": "historical_price_range",
                "band_basis": "historical P20-P80 price range",
            }
        except Exception as e:
            logger.error(f"Valuation band chart generation failed: {e}")
            return {"success": False, "error": str(e)}
