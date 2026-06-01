# -*- coding: utf-8 -*-
"""
Stock Data Skill — Pure Data Retrieval Layer

Uses akshare (free open-source data source) to obtain real A-share financial data.
No analysis performed, only raw data returned for the Analysis Agent.

Data source: East Money (wrapped by akshare), no API Key required.
"""
import logging
from typing import Any, Dict
from src.skills.base import Skill

logger = logging.getLogger(__name__)


class StockDataSkill(Skill):
    """
    Stock Data Retrieval Skill
    
    Provides real financial data for A-share listed companies:
    1. Company basic information
    2. Three financial statements (income statement/balance sheet/cash flow statement)
    3. Key financial metrics (akshare raw data)
    4. Stock price data
    """
    
    @property
    def name(self) -> str:
        return "stock_data"
    
    @property
    def description(self) -> str:
        return "A-share listed company financial data (akshare real data): financial statements, stock prices, company info"
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "company_info")
        symbol = kwargs.get("symbol", "")
        
        if not symbol:
            return self._failure("Please provide a stock symbol, e.g. 600519 (Kweichow Moutai)")
        
        try:
            import akshare as ak
            
            if action == "company_info":
                return await self._company_info(ak, symbol)
            elif action == "financials":
                return await self._financials(ak, symbol)
            elif action == "key_metrics":
                return await self._key_metrics(ak, symbol)
            elif action == "price_history":
                return await self._price_history(ak, symbol)
            elif action == "industry_comparison":
                return await self._industry_comparison(ak, symbol)
            else:
                return self._failure(f"Unsupported operation: {action}")
        
        except ImportError:
            return self._failure("akshare not installed: pip install akshare")
        except Exception as e:
            return self._failure(f"Data retrieval failed: {e}")
    
    async def _price_history(self, ak, symbol: str) -> Dict[str, Any]:
        """Retrieve stock price history data (for chart generation)"""
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            if df is not None and not df.empty:
                price_data = df.head(120).to_dict(orient="records")
                return {
                    "success": True,
                    "data": price_data,
                    "symbol": symbol,
                    "source": "akshare/A-share historical prices",
                    "content": f"Retrieved price data for {symbol} (last 120 trading days)",
                }
            return self._failure("No price data retrieved")
        except Exception as e:
            return self._failure(f"Price data retrieval failed: {e}")
    
    async def _industry_comparison(self, ak, symbol: str) -> Dict[str, Any]:
        """Retrieve peer company list in the same industry"""
        try:
            info = ak.stock_individual_info_em(symbol=symbol)
            industry = ""
            for _, row in info.iterrows():
                if row["item"] == "行业":
                    industry = row["value"]
                    break
            return {
                "success": True,
                "data": {"industry": industry, "symbol": symbol},
                "symbol": symbol,
                "source": "akshare/industry classification",
                "content": f"Industry: {industry}",
            }
        except Exception as e:
            return self._failure(f"Industry info retrieval failed: {e}")
    
    async def _company_info(self, ak, symbol: str) -> Dict[str, Any]:
        df = ak.stock_individual_info_em(symbol=symbol)
        info = dict(zip(df["item"], df["value"]))
        return {
            "success": True,
            "data": info,
            "symbol": symbol,
            "source": "akshare/East Money",
            "content": f"Stock Name: {info.get('股票简称','')}\n"
                       f"Industry: {info.get('行业','')}\n"
                       f"Total Shares: {info.get('总股本','')}\n"
                       f"Tradable Shares: {info.get('流通股','')}\n"
                       f"Main Business: {info.get('主营业务','')}\n"
        }
    
    async def _financials(self, ak, symbol: str) -> Dict[str, Any]:
        income = ak.stock_profit_sheet_by_report_em(symbol=symbol)
        bs = ak.stock_balance_sheet_by_report_em(symbol=symbol)
        cf = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
        
        data = {}
        if income is not None and not income.empty:
            data["income_statement"] = income.head(15).to_dict(orient="records")
        if bs is not None and not bs.empty:
            data["balance_sheet"] = bs.head(15).to_dict(orient="records")
        if cf is not None and not cf.empty:
            data["cash_flow"] = cf.head(15).to_dict(orient="records")
        
        return {
            "success": True,
            "data": data,
            "symbol": symbol,
            "source": "akshare/East Money",
            "content": f"Retrieved three financial statements for {symbol}",
        }
    
    async def _key_metrics(self, ak, symbol: str) -> Dict[str, Any]:
        try:
            df = ak.stock_financial_abstract_ths(symbol=symbol)
            metrics = {}
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    metrics[row["指标名称"]] = row["指标值"]
            return {
                "success": True,
                "data": metrics,
                "symbol": symbol,
                "source": "akshare/Tonghuashun",
                "content": "\n".join(f"{k}: {v}" for k, v in list(metrics.items())[:15])
            }
        except Exception as e:
            return self._failure(f"Metric retrieval failed: {e}")
