"""
MetricExtractor — two-stage data extraction (G1-FIX-1)

Stage 1: regex matching (high precision, medium recall)
Stage 2: LLM refinement (medium precision, high recall, optional)

Priority: JSON-LD blocks > regex fallback
"""

import re
import json
from typing import Dict, List, Optional, Iterator
from datetime import datetime


class MetricExtractor:
    """Two-stage metric data extractor from unstructured text."""

    # Unit patterns: currency-specific units must appear BEFORE generic "亿" to match first
    _UNIT_CURRENCY = r'亿元|亿港元|亿港币|亿人民币|亿美元|亿欧元|亿英镑|亿日元|亿|万元|万|元'
    _UNIT_CURRENCY_EN = r'billion\s+(?:CNY|USD|EUR|HKD|GBP|JPY)|million\s+(?:CNY|USD|EUR|HKD|GBP|JPY)|billion|million'
    _UNIT_VOLUME_EN = r'million\s+(?:units|vehicles|cars)|thousand\s+(?:units|vehicles)|million|thousand'
    
    METRIC_PATTERNS = [
        # --- Chinese patterns ---
        (r'(?:净利润|归母净利润|扣非净利润)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "净利润"),
        (r'(?:(?:营业)?收入|营收)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "营收"),
        (r'(?:总)?销量[^\d]*?(\d+\.?\d*)\s*(万辆|万台|万部|万吨|辆|台|部|吨)', "销量"),
        (r'(?:海外|出口)销量[^\d]*?(\d+\.?\d*)\s*(万辆|万台|辆|台)', "海外销量"),
        (r'(?:研发|R&D)(?:投入|费用)?[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "研发投入"),
        (r'毛利率[^\d]*?(\d+\.?\d*)\s*%', "毛利率"),
        (r'(?:市场)?份额[^\d]*?(\d+\.?\d*)\s*%', "市占率"),
        (r'增长率[^\d]*?(\d+\.?\d*)\s*%', "增长率"),
        (r'单车利润[^\d]*?(\d+\.?\d*)\s*(万元|万|元)', "单车利润"),
        (r'财务费用[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "财务费用"),
        (r'现金流[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "现金流"),
        (r'负债[率]?[^\d]*?(\d+\.?\d*)\s*%', "负债率"),
        # --- English patterns (specific BEFORE general to avoid overlap) ---
        (r'(?:overseas\s+sales|export\s+sales|overseas\s+deliver(?:ies|ed))[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_VOLUME_EN + r')', "海外销量"),
        (r'(?:net\s+profit|net\s+income)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY_EN + r')', "净利润"),
        (r'(?:revenue|total\s+revenue|operating\s+revenue|turnover)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY_EN + r')', "营收"),
        (r'(?<!overseas\s)(?:sales|deliver(?:ies|ed))(?:\s+of)?[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_VOLUME_EN + r')', "销量"),
        (r'(?:R&D\s+(?:expense|investment|spending)|research\s+(?:and\s+)?development\s+(?:expense|investment|spending)?)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY_EN + r')', "研发投入"),
        (r'(?:gross\s+margin|gross\s+profit\s+margin)[^\d]*?(\d+\.?\d*)\s*%', "毛利率"),
        (r'market\s+share[^\d]*?(\d+\.?\d*)\s*%', "市占率"),
        (r'growth\s+rate[^\d]*?(\d+\.?\d*)\s*%', "增长率"),
        (r'profit\s+per\s+(?:vehicle|unit|car)[^\d]*?(\d+\.?\d*)\s*(?:CNY\s+)?(?:thousand|yuan)', "单车利润"),
        (r'(?:financial\s+expense|finance\s+costs)[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY_EN + r')', "财务费用"),
        (r'cash\s+flow[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY_EN + r')', "现金流"),
        (r'(?:debt\s+ratio|debt-to-asset\s+ratio|liability\s+ratio)[^\d]*?(\d+\.?\d*)\s*%', "负债率"),
    ]

    ENGLISH_ALIASES = {
        "净利润": ["net profit", "net income", "net earnings"],
        "营收": ["revenue", "total revenue", "operating revenue", "turnover"],
        "销量": ["sales", "deliveries", "sales volume", "shipments"],
        "海外销量": ["overseas sales", "export sales", "overseas deliveries"],
        "研发投入": ["R&D expense", "R&D investment", "R&D spending", "research and development expense"],
        "毛利率": ["gross margin", "gross profit margin"],
        "市占率": ["market share"],
        "增长率": ["growth rate"],
        "单车利润": ["profit per vehicle", "profit per unit"],
        "财务费用": ["financial expense", "finance costs"],
        "现金流": ["cash flow"],
        "负债率": ["debt ratio", "debt-to-asset ratio", "liability ratio"],
    }

    CALIBER_KEYWORDS = {
        "A股": ["A股", "深交所", "上交所", "深圳", "上海", "国内口径"],
        "港股": ["港股", "港交所", "香港", "H股"],
        "含少数": ["含少数股东", "合并报表", "集团口径"],
        "不含少数": ["归母", "不含少数股东", "母公司"],
    }

    JSONLD_RE = re.compile(r'<!-- DATA -->(.*?)<!-- /DATA -->', re.DOTALL)

    def extract(self, data_points: List[Dict]) -> List[Dict]:
        """Stage 1: regex extraction with JSON-LD priority."""
        results = []
        for dp in data_points:
            content = dp.get("content", "")
            source = dp.get("url", "")
            jsonld_results = list(self._extract_jsonld(content))
            if jsonld_results:
                results.extend(jsonld_results)
                continue
            for pattern, metric_name in self.METRIC_PATTERNS:
                for match in re.finditer(pattern, content):
                    value = float(match.group(1))
                    unit = self._normalize_unit(match.group(2) if len(match.groups()) > 1 else "")
                    results.append({
                        "metric": metric_name, "value": value, "unit": unit,
                        "currency": self._infer_currency(unit),
                        "caliber": self._infer_caliber(content, match.start()),
                        "year": self._infer_year(content, match.start()),
                        "source": source, "confidence": self._calc_confidence(source),
                    })
        return results

    def _extract_jsonld(self, content: str) -> Iterator[Dict]:
        """Extract metrics from JSON-LD blocks (<!-- DATA -->...<!-- /DATA -->)."""
        for match in self.JSONLD_RE.finditer(content):
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, dict) and "name" in data and "value" in data:
                    _unit = data.get("unit", "")
                    _currency = data.get("currency", "")
                    if not _currency and _unit:
                        _unit_cur_map = {"亿港元": "HKD", "亿港币": "HKD", "亿美元": "USD",
                                         "亿欧元": "EUR", "亿英镑": "GBP", "亿日元": "JPY"}
                        _currency = _unit_cur_map.get(_unit, "")
                    yield {"metric": data["name"], "value": float(data["value"]),
                           "unit": _unit, "currency": _currency,
                           "caliber": data.get("caliber", ""),
                           "year": data.get("year", 0), "source": data.get("source", ""),
                           "confidence": 0.95}
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

    def _normalize_unit(self, raw: str) -> str:
        m = {"亿元": "亿元", "亿港元": "亿港元", "亿港币": "亿港元", "亿人民币": "亿人民币",
             "亿美元": "亿美元", "亿欧元": "亿欧元", "亿英镑": "亿英镑", "亿日元": "亿日元",
             "万辆": "万辆", "万台": "万台",
             "万元": "万元", "元": "元", "辆": "辆", "台": "台", "吨": "吨", "亿": "亿"}
        return m.get(raw, raw)
    
    def _infer_currency(self, unit: str) -> str:
        """Infer currency code from normalized unit."""
        mapping = {"亿元": "CNY", "亿港元": "HKD", "亿港币": "HKD", "亿人民币": "CNY",
                   "亿美元": "USD", "亿欧元": "EUR", "亿英镑": "GBP", "亿日元": "JPY"}
        if unit in mapping:
            return mapping[unit]
        for kw, code in [("CNY", "CNY"), ("USD", "USD"), ("EUR", "EUR"), ("HKD", "HKD"), ("GBP", "GBP"), ("JPY", "JPY")]:
            if kw in unit:
                return code
        return ""

    def _infer_caliber(self, text: str, pos: int) -> str:
        window = text[max(0, pos - 100):pos + 100]
        for cal, kws in self.CALIBER_KEYWORDS.items():
            for kw in kws:
                if kw in window:
                    return f"{cal}口径"
        return ""

    def _infer_year(self, text: str, pos: int) -> int:
        window = text[max(0, pos - 50):pos + 50]
        years = re.findall(r'(20\d{2})', window)
        return int(years[-1]) if years else datetime.now().year - 1

    def _calc_confidence(self, source: str) -> float:
        s = 0.5
        if ".gov" in source or ".cn" in source:
            s += 0.2
        if "report" in source or "年报" in source:
            s += 0.2
        return min(s, 1.0)
