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
    
    Memory cache: (symbol, action) → result, avoids duplicate API calls
    from parallel agents requesting the same data.
    """
    
    _memory_cache: Dict[tuple, Dict[str, Any]] = {}

    _FINANCIALS_KEY_COLUMNS = {
        "income_statement": {
            "date": ["REPORT_DATE", "报告期", "日期"],
            "key_cols": ["OPERATE_INCOME", "营业总收入", "TOTAL_OPERATE_INCOME",
                         "NET_PROFIT", "净利润", "PARENT_NETPROFIT", "归属净利润",
                         "BASIC_EPS", "基本每股收益"],
        },
        "balance_sheet": {
            "date": ["REPORT_DATE", "报告期", "日期"],
            "key_cols": ["TOTAL_ASSETS", "总资产", "TOTAL_LIABILITIES", "总负债",
                         "TOTAL_EQUITY", "所有者权益", "PARENT_EQUITY", "归属母公司权益"],
        },
        "cash_flow": {
            "date": ["REPORT_DATE", "报告期", "日期"],
            "key_cols": ["OPERATE_CASH_FLOW", "经营活动现金流量", "NET_CASH_OPERATE",
                         "投资活动现金流量"],
        },
    }

    _THS_METRIC_CN = {
        "operating_income_total": "营业总收入",
        "parent_holder_net_profit": "归属净利润",
        "index_deduct_holder_net_profit": "扣非净利润",
        "calculate_operating_income_total_yoy_growth_ratio": "营收同比增长",
        "calculate_parent_holder_net_profit_yoy_growth_ratio": "净利润同比增长",
        "deduct_net_profit_yoy_growth_ratio": "扣非净利润同比增长",
        "basic_eps": "基本每股收益",
        "calc_per_net_assets": "每股净资产",
        "per_capital_reserve": "每股资本公积金",
        "per_undistributed_profits": "每股未分配利润",
        "index_per_operating_cash_flow_net": "每股经营现金流",
        "sale_net_interest_ratio": "销售净利率",
        "sale_gross_margin": "销售毛利率",
        "index_weighted_avg_roe": "加权ROE",
        "index_full_diluted_roe": "摊薄ROE",
        "business_cycle": "营业周期",
        "inventory_turnover_ratio": "存货周转率",
        "inventory_turnover_days": "存货周转天数",
        "receive_accounts_turnover_days": "应收账款周转天数",
        "current_ratio": "流动比率",
        "quick_ratio": "速动比率",
        "conservative_quick_ratio": "保守速动比率",
        "equity_ratio": "产权比率",
        "assets_debt_ratio": "资产负债率",
    }
    
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

        # The Skill is also called directly by report/data-collection flows,
        # so it cannot assume the orchestrator already canonicalized the
        # identifier. AkShare endpoints require a code, while users and LLM
        # plans commonly provide a company short/full name.
        symbol = await self._canonicalize_symbol(str(symbol).strip())
        if not symbol:
            return self._failure(
                "Unable to resolve company name to an A-share code; "
                "provide a six-digit stock code"
            )
        
        cache_key = (symbol, action)
        if cache_key in self._memory_cache:
            logger.info(f"StockDataSkill: cache hit for {cache_key}")
            return self._memory_cache[cache_key]
        
        try:
            import akshare as ak
            
            if action == "company_info":
                result = await self._company_info(ak, symbol)
            elif action == "financials":
                result = await self._financials(ak, symbol)
            elif action == "key_metrics":
                result = await self._key_metrics(ak, symbol)
            elif action == "price_history":
                result = await self._price_history(ak, symbol)
            elif action == "industry_comparison":
                result = await self._industry_comparison(ak, symbol)
            else:
                return self._failure(f"Unsupported operation: {action}")
            
            if result.get("success"):
                self._memory_cache[cache_key] = result
            return result
        
        except ImportError:
            return self._failure("akshare not installed: pip install akshare")
        except Exception as e:
            return self._failure(f"Data retrieval failed: {e}")

    async def _canonicalize_symbol(self, symbol: str) -> str:
        if symbol.isdigit() and len(symbol) == 6:
            return symbol
        try:
            from src.core.entity_resolver import get_entity_resolver

            entities = await get_entity_resolver().resolve(symbol)
            for entity in entities:
                code = getattr(entity, "resolved_code", None)
                if isinstance(code, str) and code.isdigit() and len(code) == 6:
                    logger.info("StockDataSkill: resolved '%s' -> '%s'", symbol, code)
                    return code
        except Exception as exc:
            logger.debug("StockDataSkill: symbol resolution failed for '%s': %s", symbol, exc)
        return ""
    
    async def _price_history(self, ak, symbol: str) -> Dict[str, Any]:
        """Retrieve stock price history data (for chart generation).

        2026-10 实测修订：EastMoney push2 域在本网络被服务端断连，
        akshare stock_zh_a_hist（requests）随之失败——主路径保留但补充
        腾讯 fqkline 兜底（实测可用）。数据取最近 120 个交易日（akshare
        升序返回，旧实现 head(120) 取到的是最旧一段——修正为 tail）。
        """
        records: list = []
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            if df is not None and not df.empty:
                records = df.tail(120).to_dict(orient="records")
        except Exception as e:
            logger.warning("StockDataSkill: akshare price history failed for %s: %s", symbol, e)
        if not records:
            records = self._tencent_kline(symbol)
        if records:
            return {
                "success": True,
                "data": records,
                "records": records,
                "symbol": symbol,
                "source": "akshare/A-share historical prices" if records and "日期" in records[0] else "tencent/fqkline",
                "content": f"Retrieved price data for {symbol} (last {len(records)} trading days)",
            }
        return self._failure("No price data retrieved")

    def _tencent_kline(self, symbol: str, days: int = 120) -> list:
        """腾讯日 K 兜底（qfq）。返回升序 records：日期/开盘/收盘/最高/最低/成交量。"""
        import requests
        try:
            url = (
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                f"?param=sh{symbol},day,,,{days},qfq"
            )
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            node = (resp.json().get("data") or {}).get(f"sh{symbol}") or {}
            rows = node.get("qfqday") or node.get("day") or []
            out = []
            for r in rows:
                if len(r) < 6:
                    continue
                out.append({
                    "日期": r[0], "开盘": float(r[1]), "收盘": float(r[2]),
                    "最高": float(r[3]), "最低": float(r[4]),
                    "成交量": r[5],
                })
            return out
        except Exception as e:
            logger.warning("StockDataSkill: tencent kline failed for %s: %s", symbol, e)
            return []

    def _tencent_quote(self, symbol: str) -> Dict[str, Any]:
        """腾讯实时行情兜底：名称/最新价/总市值/市盈率（company_info 备源）。"""
        import requests
        try:
            url = f"https://qt.gtimg.cn/q=sh{symbol}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.encoding = "gbk"
            fields = resp.text.split("~")
            if len(fields) < 46:
                return {}
            def _f(idx):
                try:
                    return float(fields[idx])
                except Exception:
                    return ""
            return {
                "股票简称": fields[1],
                "股票代码": fields[2],
                "最新价": _f(3),
                "市盈率": _f(39),
                "总市值": _f(45),
                "note": "来源: 腾讯行情（push2 东财实时接口在本网络不可用）",
            }
        except Exception as e:
            logger.warning("StockDataSkill: tencent quote failed for %s: %s", symbol, e)
            return {}

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
            quote = self._tencent_quote(symbol)
            if quote:
                return {
                    "success": True,
                    "data": {"industry": "", "symbol": symbol, "quote": quote},
                    "symbol": symbol,
                    "source": "tencent/quote fallback",
                    "content": f"Industry unavailable; quote fallback: {quote.get('股票简称','')}",
                }
            return self._failure(f"Industry info retrieval failed: {e}")
    
    async def _company_info(self, ak, symbol: str) -> Dict[str, Any]:
        try:
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
        except Exception as e:
            # push2 东财实时接口在本网络不可用（2026-10 实测）——腾讯行情兜底
            quote = self._tencent_quote(symbol)
            if quote:
                return {
                    "success": True,
                    "data": quote,
                    "symbol": symbol,
                    "source": "tencent/quote fallback",
                    "content": f"Stock Name: {quote.get('股票简称','')}\n"
                               f"Code: {quote.get('股票代码','')}\n"
                               f"Latest Price: {quote.get('最新价','')}\n"
                               f"Total Market Cap: {quote.get('总市值','')}\n"
                               f"PE: {quote.get('市盈率','')}\n",
                }
            return self._failure(f"Company info retrieval failed: {e}")
    
    async def _financials(self, ak, symbol: str) -> Dict[str, Any]:
        """三大报表（东财 datacenter）。

        2026-10 实测：datacenter 报表接口当前返回空（akshare 内部
        'NoneType' not subscriptable）——失败时兜底同花顺摘要（营收/净利/
        EPS 等按报告期）+ 东财财务分析指标（stock_financial_analysis_indicator
        实测可用），保证结构化财务数据始终有产出。
        """
        try:
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

            if not data:
                return await self._financials_fallback(ak, symbol)

            return {
                "success": True,
                "data": data,
                "symbol": symbol,
                "source": "akshare/East Money",
                "content": f"Retrieved three financial statements for {symbol}",
            }
        except Exception as e:
            logger.warning("StockDataSkill: EM statements failed for %s: %s", symbol, e)
            try:
                return await self._financials_fallback(ak, symbol)
            except Exception as fe:
                return self._failure(
                    f"Financial statements retrieval failed: {e}; fallback failed: {fe}")

    async def _financials_fallback(self, ak, symbol: str) -> Dict[str, Any]:
        """财报兜底：同花顺摘要（按报告期的核心指标）+ 东财分析指标。"""
        data: Dict[str, Any] = {}
        try:
            df = ak.stock_financial_abstract_ths(symbol=symbol)
            if df is not None and not df.empty and "报告期" in df.columns:
                data["ths_abstract"] = df.tail(8).to_dict(orient="records")
        except Exception as e:
            logger.warning("StockDataSkill: THS abstract fallback failed: %s", e)
        try:
            df2 = ak.stock_financial_analysis_indicator(symbol=symbol, start_year="2023")
            if df2 is not None and not df2.empty:
                data["analysis_indicators"] = df2.head(10).to_dict(orient="records")
        except Exception as e:
            logger.warning("StockDataSkill: analysis indicator fallback failed: %s", e)
        if not data:
            return self._failure("All financial data sources unavailable")
        return {
            "success": True,
            "data": data,
            "symbol": symbol,
            "source": "akshare fallback (THS abstract + EM analysis indicators)",
            "content": f"Retrieved financial data (fallback sources) for {symbol}",
        }
    
    async def _key_metrics(self, ak, symbol: str) -> Dict[str, Any]:
        """关键财务指标（同花顺摘要）。

        2026-10 schema 漂移修复：当前 akshare 返回宽表（每行=一个报告期，
        列=中文指标名，首列"报告期"），旧实现按长表（指标名称/指标值列）
        解析 → KeyError。宽表取最近 8 个报告期逐期输出。
        """
        try:
            df = ak.stock_financial_abstract_ths(symbol=symbol)
            if df is None or df.empty:
                return self._failure("No metric data retrieved")
            if "报告期" in df.columns:
                periods = []
                df_recent = df.tail(8)
                for _, row in df_recent.iterrows():
                    rec = {str(k): v for k, v in row.items()}
                    periods.append(rec)
                return {
                    "success": True,
                    "data": {"periods": periods},
                    "symbol": symbol,
                    "source": "akshare/Tonghuashun",
                    "content": "\n".join(
                        f"{rec.get('报告期', '')}: " + " | ".join(
                            f"{k}={v}" for k, v in list(rec.items())[1:6]
                            if v is not None and v is not False
                        )
                        for rec in periods[:3]
                    ),
                }
            # 旧长表格式兼容（指标名称/指标值）
            metrics = {}
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

    def format_data(self, data: dict, action: str, identifier: str) -> str:
        # 2026-10 修订：price_history 等新实现把 records 列表直接放在 data
        # 字段——入参可能是 list，做形状归一后再分发。
        if isinstance(data, list):
            data = {"records": data}
        if action == "financials":
            return self._format_financials(data, identifier)
        elif action == "price_history":
            return self._format_price_history(data, identifier)
        elif action == "key_metrics":
            return self._format_key_metrics(data, identifier)
        elif action == "company_info":
            return self._format_company_info(data, identifier)
        elif action == "industry_comparison":
            return self._format_industry_comparison(data, identifier)
        return ""

    def _format_financials(self, data: dict, symbol: str) -> str:
        lines = []
        for section_key, config in self._FINANCIALS_KEY_COLUMNS.items():
            records = data.get(section_key, [])
            if not records or not isinstance(records, list):
                continue
            section_names = {
                "income_statement": "利润表",
                "balance_sheet": "资产负债表",
                "cash_flow": "现金流量表",
            }
            lines.append(f"=== {section_names.get(section_key, section_key)} (最近{min(len(records), 4)}期) ===")
            date_cols = config["date"]
            key_cols = config["key_cols"]
            for rec in records[:4]:
                date_val = ""
                for dc in date_cols:
                    if dc in rec:
                        date_val = str(rec[dc])[:10]
                        break
                parts = []
                for kc in key_cols:
                    if kc in rec and rec[kc] is not None:
                        val = rec[kc]
                        if isinstance(val, float):
                            if abs(val) >= 1e8:
                                parts.append(f"{kc} {val/1e8:.2f}亿")
                            elif abs(val) >= 1e4:
                                parts.append(f"{kc} {val/1e4:.2f}万")
                            else:
                                parts.append(f"{kc} {val:.2f}")
                        else:
                            parts.append(f"{kc} {val}")
                if date_val or parts:
                    if parts:
                        line = f"{date_val}: " + " | ".join(parts[:5]) if date_val else " | ".join(parts[:5])
                    else:
                        line = str(date_val)
                    lines.append(line)
        # 兜底数据形状（EM 报表接口不可用时）：同花顺摘要 + 分析指标
        ths = data.get("ths_abstract") or []
        if ths and isinstance(ths, list):
            lines.append(f"=== 核心财务指标-同花顺 (最近{min(len(ths), 4)}期) ===")
            for rec in ths[:4]:
                period = str(rec.get("报告期", ""))[:10]
                parts = [
                    f"{k}={v}" for k, v in rec.items()
                    if k != "报告期" and v is not None and v is not False
                ]
                if period:
                    lines.append(f"{period}: " + " | ".join(parts[:6]))
        indicators = data.get("analysis_indicators") or []
        if indicators and isinstance(indicators, list):
            date_key = next(
                (k for k in ("日期", "报告期", "date") if indicators[0].get(k)),
                None,
            )
            lines.append(f"=== 财务分析指标 (最近{min(len(indicators), 4)}期) ===")
            for rec in indicators[:4]:
                period = str(rec.get(date_key, ""))[:10] if date_key else ""
                parts = [
                    f"{k}={v}" for k, v in list(rec.items())[:6]
                    if k != date_key and v is not None and str(v).strip() not in ("", "--", "False")
                ]
                if period:
                    lines.append(f"{period}: " + " | ".join(parts))
        return "\n".join(lines) if lines else ""

    def _format_price_history(self, data: dict, symbol: str) -> str:
        records = data.get("records", [])
        if not records:
            return ""
        lines = [f"=== {symbol} 股价数据 ==="]
        recent = records[:30]
        closes = []
        highs = []
        lows = []
        for r in recent:
            c = r.get("收盘", r.get("close"))
            h = r.get("最高", r.get("high"))
            l = r.get("最低", r.get("low"))
            if isinstance(c, (int, float)):
                closes.append(c)
            if isinstance(h, (int, float)):
                highs.append(h)
            if isinstance(l, (int, float)):
                lows.append(l)
        if closes and highs and lows:
            lines.append(f"最近{len(recent)}日: 最高{max(highs):.2f} | 最低{min(lows):.2f} | 最新{closes[-1]:.2f}")
        for rec in recent[:10]:
            date_val = rec.get("日期", rec.get("date", ""))
            close = rec.get("收盘", rec.get("close", ""))
            open_val = rec.get("开盘", rec.get("open", ""))
            change = rec.get("涨跌幅", rec.get("change_pct", ""))
            line_parts = [str(date_val)[:10]]
            if open_val:
                line_parts.append(f"开{open_val}")
            if close:
                line_parts.append(f"收{close}")
            if change:
                line_parts.append(f"涨幅{change}")
            lines.append(" ".join(str(p) for p in line_parts))
        return "\n".join(lines)

    def _format_key_metrics(self, data: dict, symbol: str) -> str:
        periods = data.get("periods", [])
        if not periods:
            if isinstance(data, dict) and not data.get("periods"):
                lines = [f"=== {symbol} 关键财务指标 ==="]
                for k, v in list(data.items())[:15]:
                    if v is not None and v is not False:
                        cn = self._THS_METRIC_CN.get(k, k)
                        lines.append(f"{cn}: {v}")
                return "\n".join(lines)
            return ""
        lines = [f"=== {symbol} 关键财务指标 (最近{min(len(periods), 4)}期) ==="]
        for rec in periods[:4]:
            period = rec.get("报告期", rec.get("report_date", rec.get("REPORT_DATE", "")))
            parts = [str(period)[:10]]
            for k, v in rec.items():
                if k in ("报告期", "report_date", "REPORT_DATE"):
                    continue
                if v is not None and v is not False:
                    if isinstance(v, float) and v != v:
                        continue
                    cn = self._THS_METRIC_CN.get(k, k)
                    parts.append(f"{cn}:{v}")
            lines.append(" | ".join(parts[:8]))
        return "\n".join(lines)

    def _format_company_info(self, data: dict, symbol: str) -> str:
        if not data:
            return ""
        lines = [f"=== {symbol} 公司信息 ==="]
        key_fields = ["股票简称", "行业", "总股本", "流通股", "主营业务",
                       "上市时间", "注册资本", "所属申万行业"]
        found = set()
        for k in key_fields:
            if k in data:
                lines.append(f"{k}: {data[k]}")
                found.add(k)
        for k, v in data.items():
            if k not in found:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def _format_industry_comparison(self, data: dict, symbol: str) -> str:
        if not data:
            return ""
        industry = data.get("industry", "")
        if industry:
            return f"=== {symbol} 行业对比 ===\n行业: {industry}"
        # 兜底行情（push2 不可用时）：渲染可用行情字段
        quote = data.get("quote") or {}
        if isinstance(quote, dict) and quote:
            lines = [f"=== {symbol} 行情概览（行业分类暂不可用） ==="]
            for k in ("股票简称", "股票代码", "最新价", "市盈率", "总市值"):
                if quote.get(k) not in (None, ""):
                    lines.append(f"{k}: {quote[k]}")
            return "\n".join(lines)
        return ""
