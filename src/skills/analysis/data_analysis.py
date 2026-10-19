# -*- coding: utf-8 -*-
"""
Data Analysis Skill - Enhanced

Three-layer architecture:
1. Computation layer: pandas_agent / PythonREPL for precise calculations (CAGR/CR3/HHI/descriptive stats)
2. Analysis layer: LLM interprets computed results, provides analyst judgment
3. Output layer: Structured JSON + natural language

Supported computations:
- Descriptive statistics (mean/median/std_dev/quantiles)
- Time series calculations (CAGR, YoY growth, MoM growth)
- Market concentration (CR3/CR5/HHI)
- Trend analysis (moving average, growth rate decomposition)
- Data visualization suggestions
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from src.skills.base import Skill, SkillConfig
from src.skills.registry import get_skill_registry
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


class DataAnalysisSkill(Skill):
    """
    Data Analysis Skill - Enhanced
    
    Uses pandas_agent for precise calculations, LLM for analysis interpretation.
    """

    @property
    def name(self) -> str:
        return "data_analysis"

    @property
    def description(self) -> str:
        return "Quantitative data analysis: CAGR/CR3/HHI/descriptive stats/trend analysis"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        topic = kwargs.get("topic", "")
        aspect = kwargs.get("aspect", "")
        data_points = kwargs.get("data_points", [])

        if not topic:
            return self._failure("topic is required")

        # Step 1: Extract structured numbers from data points
        extracted = self._extract_numbers(data_points, topic=topic)

        # Step 2: Perform actual computation with pandas_agent
        calc_results = {}
        if extracted["time_series"]:
            calc_results["time_series"] = await self._calc_time_series(extracted["time_series"])
        if extracted["market_shares"]:
            calc_results["market_shares"] = self._calc_concentration(extracted["market_shares"])
        if extracted["numeric_values"]:
            calc_results["descriptive"] = self._calc_descriptive(extracted["numeric_values"])

        # Step 3: LLM interprets computed results
        content = await self._interpret_results(
            topic=topic,
            aspect=aspect,
            extracted=extracted,
            calc_results=calc_results,
            data_points=data_points,
        )

        return {
            "success": True,
            "content": content,
            "stats": calc_results,
            "extracted_numbers": extracted["summary"],
            "agent_type": "data_analysis",
        }

    # ============ Computation Layer ============

    _BRANDS = (
        "华为", "苹果", "Apple", "vivo", "OPPO", "小米", "荣耀", "三星",
        "Samsung", "传音", "一加", "realme", "iQOO", "红米",
    )
    _BRAND_ALT = "|".join(sorted((re.escape(b) for b in _BRANDS), key=len, reverse=True))
    _PRICE_BAND_RE = re.compile(
        r"美元以上|美元以下|\d+\s*[-~至到]\s*\d+\s*美元|价位段|价格段"
    )
    _POLICY_RE = re.compile(r"积分比例|购置税|免税额|新能源积分|配额")
    _OFF_TOPIC_NEV_RE = re.compile(r"新能源|积分比例|购置税|乘用车")
    _BRAND_SHARE_RE = re.compile(
        rf"(?:({_BRAND_ALT})(?:(?!{_BRAND_ALT}).){{0,60}}?(?:市场份额|份额)\s*[：:]?\s*(\d+(?:\.\d+)?)\s*[%％])"
        rf"|(?:({_BRAND_ALT})(?:(?!{_BRAND_ALT}).){{0,60}}?(\d+(?:\.\d+)?)\s*[%％](?:的)?(?:市场份额|份额))"
    )

    def _extract_numbers(self, data_points: List[Dict], topic: str = "") -> Dict:
        """Extract numbers; keep price-band shares for analysis, but exclude them from concentration."""
        time_series = []
        market_shares = []
        price_band_shares = []
        numeric_values = []
        rejected = []
        seen_shares = set()
        seen_price_bands = set()
        points = data_points if isinstance(data_points, list) else []

        for dp in points[:200]:
            if not isinstance(dp, dict):
                continue
            data = dp.get("data") if isinstance(dp.get("data"), dict) else {}
            title = str(dp.get("title") or "")
            content = str(dp.get("content") or "")
            metric = str(data.get("metric") or title)
            text = f"{title} {content}"
            source = dp.get("url", "")

            if self._is_off_topic(metric, title, content, topic):
                rejected.append({"reason": "off_topic", "metric": metric})
                continue
            if self._is_policy_quota(metric, title):
                rejected.append({"reason": "policy_quota", "metric": metric})
                continue

            if self._is_price_band(metric, title):
                value = self._parse_percent(data.get("value"))
                if value is not None:
                    key = (metric, round(value, 4))
                    if key not in seen_price_bands:
                        seen_price_bands.add(key)
                        period = str(data.get("period") or "")
                        geographic_scope = str(data.get("geographic_scope") or "")
                        price_band_shares.append({
                            "metric": metric,
                            "share": value,
                            "period": period,
                            "geographic_scope": geographic_scope,
                            "source": source,
                        })
            else:
                for company, share in self._iter_company_shares(metric, data, text):
                    key = (company, round(share, 4))
                    if key in seen_shares:
                        continue
                    seen_shares.add(key)
                    market_shares.append({
                        "company": company,
                        "share": share,
                        "source": source,
                    })

            ts_matches = re.findall(
                r"(20\d{2})[年\s]*.*?(\d+[\.\d]*)\s*(亿|万|千|百|%|亿元|万美元|亿欧元)",
                text,
            )
            for year, val, unit in ts_matches:
                time_series.append({
                    "year": int(year),
                    "value": float(val),
                    "unit": unit,
                    "source": source,
                })

            val_matches = re.findall(r"(\d+[\.\d]*)\s*(亿|万|千|百|元|美元)", text)
            for val, unit in val_matches:
                numeric_values.append(float(val))

        return {
            "time_series": time_series,
            "market_shares": market_shares,
            "price_band_shares": price_band_shares,
            "numeric_values": numeric_values,
            "summary": {
                "data_points_total": len(points),
                "time_series_count": len(time_series),
                "market_shares_count": len(market_shares),
                "price_band_shares_count": len(price_band_shares),
                "has_time_series": len(time_series) >= 2,
                "has_market_shares": len(market_shares) >= 2,
                "rejected": rejected,
            },
        }

    def _is_price_band(self, metric: str, title: str) -> bool:
        return bool(self._PRICE_BAND_RE.search(f"{metric} {title}"))

    def _is_policy_quota(self, metric: str, title: str) -> bool:
        return bool(self._POLICY_RE.search(f"{metric} {title}"))

    def _is_off_topic(self, metric: str, title: str, content: str, topic: str) -> bool:
        if not topic:
            return False
        if "手机" not in topic and "smartphone" not in topic.lower():
            return False
        blob = f"{metric} {title} {content[:120]}"
        return bool(self._OFF_TOPIC_NEV_RE.search(blob))

    def _iter_company_shares(self, metric: str, data: Dict, text: str):
        value = self._parse_percent(data.get("value"))
        if value is not None:
            for brand in self._BRANDS:
                if brand in metric:
                    yield brand, value
                    break
        for match in self._BRAND_SHARE_RE.finditer(text):
            company = match.group(1) or match.group(3)
            raw = match.group(2) or match.group(4)
            if company and raw:
                yield company, float(raw)

    @staticmethod
    def _parse_percent(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"(\d+(?:\.\d+)?)\s*[%％]?", str(value))
        if not match:
            return None
        if "%" not in str(value) and "％" not in str(value):
            return None
        return float(match.group(1))

    async def _calc_time_series(self, data: List[Dict]) -> Dict:
        """Calculate time series metrics with pandas"""
        if len(data) < 2:
            return {"note": "Insufficient data (less than 2 periods), cannot compute trend"}
        
        try:
            reg = get_skill_registry()
            lc_python = reg.get("lc_python_repl")
            if not lc_python:
                return await self._calc_time_series_fallback(data)

            # Prepare data
            years_str = str([d["year"] for d in data])
            values_str = str([d["value"] for d in data])
            units = data[0].get("unit", "")

            code = f"""
import json
years = {years_str}
values = {values_str}
n = len(values)

result = {{}}

# Basic
result["start_year"] = years[0]
result["end_year"] = years[-1]
result["start_value"] = values[0]
result["end_value"] = values[-1]
result["period_years"] = years[-1] - years[0]

# CAGR
if years[-1] != years[0] and values[0] > 0:
    cagr = ((values[-1] / values[0]) ** (1 / (years[-1] - years[0]))) - 1
    result["cagr"] = round(cagr * 100, 2)
    result["cagr_label"] = f"{{cagr*100:.1f}}%"

# Year-over-year growth rates
growth_rates = []
for i in range(1, n):
    if values[i-1] > 0:
        g = (values[i] - values[i-1]) / values[i-1]
        growth_rates.append(round(g * 100, 2))
    else:
        growth_rates.append(None)
result["year_over_year"] = {{str(years[i]): growth_rates[i-1] for i in range(1, n)}}

# Average growth rate
valid_growth = [g for g in growth_rates if g is not None]
if valid_growth:
    result["avg_growth_rate"] = round(sum(valid_growth) / len(valid_growth), 2)

# Volatility (std dev of growth rates)
if len(valid_growth) > 1:
    import statistics
    result["growth_volatility"] = round(statistics.stdev(valid_growth), 2)

print(json.dumps(result, ensure_ascii=False))
"""
            py_result = await lc_python.execute(command=code)
            if py_result.get("success"):
                output = py_result.get("result", "")
                # Extract JSON from output
                json_match = re.search(r'\{.*\}', str(output), re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            
            return await self._calc_time_series_fallback(data)
        except Exception as e:
            logger.warning(f"pandas time_series calc failed: {e}")
            return await self._calc_time_series_fallback(data)

    async def _calc_time_series_fallback(self, data: List[Dict]) -> Dict:
        """Manual time series calculation (native Python, no pandas needed)"""
        values = [d["value"] for d in data]
        years = [d["year"] for d in data]
        n = len(values)
        result = {
            "start_year": years[0],
            "end_year": years[-1],
            "start_value": values[0],
            "end_value": values[-1],
            "period_years": years[-1] - years[0],
        }
        if years[-1] != years[0] and values[0] > 0:
            cagr = ((values[-1] / values[0]) ** (1 / (years[-1] - years[0]))) - 1
            result["cagr"] = round(cagr * 100, 2)
        growth_rates = {}
        for i in range(1, n):
            if values[i - 1] > 0:
                g = (values[i] - values[i - 1]) / values[i - 1]
                growth_rates[str(years[i])] = round(g * 100, 2)
        result["year_over_year"] = growth_rates
        if growth_rates:
            vals = [v for v in growth_rates.values() if v is not None]
            if vals:
                result["avg_growth_rate"] = round(sum(vals) / len(vals), 2)
        return result

    def _calc_concentration(self, shares: List[Dict]) -> Dict:
        """Calculate market concentration; refuse if shares are not a valid market."""
        if not shares:
            return {"rejected": "no comparable company shares", "cr3": None, "cr5": None, "hhi": None}
        sorted_shares = sorted(shares, key=lambda x: x["share"], reverse=True)
        values = [s["share"] for s in sorted_shares]
        companies = [s["company"] for s in sorted_shares]
        share_sum = round(sum(values), 2)
        if share_sum > 105:
            return {
                "rejected": "share_sum_exceeds_100",
                "share_sum": share_sum,
                "total_companies": len(shares),
                "cr3": None,
                "cr5": None,
                "hhi": None,
            }

        result = {
            "total_companies": len(shares),
            "top_3_companies": [{"company": companies[i], "share": values[i]} for i in range(min(3, len(values)))],
            "top_5_companies": [{"company": companies[i], "share": values[i]} for i in range(min(5, len(values)))],
            "cr3": round(sum(values[:3]), 2) if len(values) >= 3 else None,
            "cr5": round(sum(values[:5]), 2) if len(values) >= 5 else None,
        }
        # HHI = sum of squared market shares
        if values:
            result["hhi"] = round(sum(v ** 2 for v in values), 0)
        # 市场结构判断
        hhi = result.get("hhi", 0)
        if hhi >= 2500:
            result["market_structure"] = "Highly concentrated (Monopolistic)"
        elif hhi >= 1500:
            result["market_structure"] = "Moderately concentrated (Oligopolistic)"
        elif hhi >= 1000:
            result["market_structure"] = "Low concentration (Competitive)"
        else:
            result["market_structure"] = "Fragmented (Perfectly competitive)"
        return result

    def _calc_descriptive(self, values: List[float]) -> Dict:
        """Descriptive statistics"""
        if not values:
            return {}
        n = len(values)
        sorted_vals = sorted(values)
        total = sum(sorted_vals)
        mean = total / n

        result = {
            "count": n,
            "sum": round(total, 2),
            "mean": round(mean, 2),
            "min": round(min(sorted_vals), 2),
            "max": round(max(sorted_vals), 2),
            "range": round(max(sorted_vals) - min(sorted_vals), 2),
        }
        if n >= 2:
            variance = sum((v - mean) ** 2 for v in sorted_vals) / (n - 1)
            result["std_dev"] = round(variance ** 0.5, 2)
            # Quantiles
            result["median"] = round(sorted_vals[n // 2], 2) if n % 2 == 1 else round(
                (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2, 2
            )
            result["q1"] = round(sorted_vals[n // 4], 2)
            result["q3"] = round(sorted_vals[3 * n // 4], 2)
        return result

    # ============ Analysis Layer (LLM) ============

    async def _interpret_results(
        self,
        topic: str,
        aspect: str,
        extracted: Dict,
        calc_results: Dict,
        data_points: List[Dict],
    ) -> str:
        """LLM interprets computed results and generates analysis content"""
        calc_summary = self._build_calc_summary(calc_results)

        prompt = self._build_prompt(topic, aspect, extracted, calc_summary)
        result = await call_llm(prompt=prompt, system_prompt=(
            "You are a senior data analyst performing hypothesis-driven interpretation.\n\n"
            "## Work Style\n"
            "1. Computed Results are machine output, not ground truth. Audit them before citing.\n"
            "2. Reject a computed metric if CR>100, shares are not the same market/period/unit, years are unsorted or future-dated as facts, series mix industries, or CAGR uses start_year==end_year.\n"
            "3. Do not interpret descriptive stats that mix incompatible units or populations.\n"
            "4. If data is insufficient, say so; do not salvage a broken CR/HHI/CAGR with a story.\n\n"
            "## Required moves\n"
            "- 数据处置: accepted / rejected / needs_research / conditional for each computed metric\n"
            "- 竞争假设: at least two explanations of the same facts\n"
            "- 主因 / 次因: rank drivers; state when the ranking reverses\n"
            "- 替代解释: at least one alternative that would change conclusion strength\n"
            "- 结论校准: label 事实 / 推断 / 预测; state 失效条件\n"
            "- 决策价值: advice only from surviving metrics, with a boundary. Use `因此建议` and phrase advice as `对厂商` or `对投资者`.\n\n"
            "## Output Standards\n"
            "- Keep units and geographic口径 explicit\n"
            "- Quantify only after口径 check (CAGR x%, not 'steady growth')\n"
            "- Name institution/source when known; otherwise mark needs_research"
        ))

        return result.get("content", "") if result and result.get("success") else ""

    def _build_calc_summary(self, calc_results: Dict) -> str:
        """Format computation results as text"""
        parts = []
        if calc_results.get("time_series"):
            ts = calc_results["time_series"]
            line = f"Time series ({ts.get('start_year')}-{ts.get('end_year')}): "
            if "cagr" in ts:
                line += f"CAGR={ts['cagr']}%, "
            if "avg_growth_rate" in ts:
                line += f"Avg growth={ts['avg_growth_rate']}%, "
            if "year_over_year" in ts:
                yoy = ts["year_over_year"]
                periods = ", ".join([f"{k}:{v}%" for k, v in list(yoy.items())[:5]])
                line += f"YoY: [{periods}]"
            parts.append(line)

        if calc_results.get("market_shares"):
            ms = calc_results["market_shares"]
            line = f"Concentration: CR3={ms.get('cr3', 'N/A')}%, CR5={ms.get('cr5', 'N/A')}%, "
            line += f"HHI={ms.get('hhi', 'N/A')}"
            if ms.get("market_structure"):
                line += f", Structure={ms['market_structure']}"
            parts.append(line)
            tops = ms.get("top_3_companies", [])
            if tops:
                items = [f'{c["company"]}={c["share"]}%' for c in tops]
                parts.append(f'Top3: {"; ".join(items)}')

        if calc_results.get("price_band_shares"):
            pb = calc_results["price_band_shares"]
            items = [f'{p["metric"]}={p["share"]}%' for p in pb[:8]]
            parts.append(f"Price-band shares (not used for concentration): {'; '.join(items)}")

        if calc_results.get("descriptive"):
            ds = calc_results["descriptive"]
            parts.append(
                f"Descriptive stats: N={ds.get('count')}, "
                f"Mean={ds.get('mean')}, "
                f"Median={ds.get('median', 'N/A')}, "
                f"StdDev={ds.get('std_dev', 'N/A')}"
            )

        return "\n".join(parts) if parts else "Insufficient data extracted for computation"

    def _build_prompt(self, topic: str, aspect: str, extracted: Dict, calc_summary: str) -> str:
        """Build LLM analysis prompt"""
        summary = extracted.get("summary", {})
        data_line = (
            f"Total {summary.get('data_points_total', 0)} data points, "
            f"including {summary.get('time_series_count', 0)} time series, "
            f"{summary.get('market_shares_count', 0)} company shares, "
            f"{summary.get('price_band_shares_count', 0)} price-band shares"
        )

        return f"""# Data Analysis Task

## Topic
{topic}

## Dimension
{aspect}

## Data Overview
{data_line}

## Computed Results (audit before use; do not treat as precise)
{calc_summary}

---

Interpret the surviving numbers only. First dispose each computed metric (accepted / rejected / needs_research / conditional). Then write:

1. **竞争假设**: at least two competing hypotheses, with what would confirm or refute each
2. **主因 / 次因**: ranked drivers, not a co-equal list
3. **替代解释**: an alternative that would change conclusion strength if true
4. **结论校准**: 事实 vs 推断 vs 预测, plus 失效条件
5. **决策价值**: recommendation and the boundary where it is void

If CR/HHI/CAGR is口径-inconsistent or >100% share, reject it and do not build a market-structure story on it.
Output only the analysis body."""
