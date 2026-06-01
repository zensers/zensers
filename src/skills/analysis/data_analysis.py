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
        extracted = self._extract_numbers(data_points)

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

    def _extract_numbers(self, data_points: List[Dict]) -> Dict:
        """
        Extract structured numbers from data points
        
        Returns three types of data:
        - time_series: [{"year": 2024, "value": 100, "unit": "100 million"}, ...]
        - market_shares: [{"company": "BYD", "share": 32.5}, ...]
        - numeric_values: [100, 200, ...] (unordered values, for descriptive stats)
        - summary: Extraction overview text description
        """
        time_series = []
        market_shares = []
        numeric_values = []

        for dp in data_points[:200]:
            text = f"{dp.get('title', '')} {dp.get('content', '')}"

            # Extract time series data: year + value + unit
            ts_matches = re.findall(
                r'(20\d{2})[年\s]*.*?(\d+[\.\d]*)\s*(亿|万|千|百|%|亿元|万美元|亿欧元)',
                text
            )
            for year, val, unit in ts_matches:
                time_series.append({
                    "year": int(year),
                    "value": float(val),
                    "unit": unit,
                    "source": dp.get("url", ""),
                })

            # Extract market share: company name + percentage
            share_matches = re.findall(
                r'([\u4e00-\u9fa5\w]+)[：:]\s*(\d+[\.\d]*)\s*[%％]',
                text
            )
            for company, share in share_matches:
                market_shares.append({
                    "company": company,
                    "share": float(share),
                    "source": dp.get("url", ""),
                })

            # Extract standalone numeric values
            val_matches = re.findall(r'(\d+[\.\d]*)\s*(亿|万|千|百|元|美元)', text)
            for val, unit in val_matches:
                numeric_values.append(float(val))

        return {
            "time_series": time_series,
            "market_shares": market_shares,
            "numeric_values": numeric_values,
            "summary": {
                "data_points_total": len(data_points),
                "time_series_count": len(time_series),
                "market_shares_count": len(market_shares),
                "has_time_series": len(time_series) >= 2,
                "has_market_shares": len(market_shares) >= 2,
            },
        }

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
        """Calculate market concentration (pure Python)"""
        sorted_shares = sorted(shares, key=lambda x: x["share"], reverse=True)
        values = [s["share"] for s in sorted_shares]
        companies = [s["company"] for s in sorted_shares]

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
        reg = get_skill_registry()
        llm = reg.get("llm_skill")
        if not llm:
            return ""

        # Build computation results summary
        calc_summary = self._build_calc_summary(calc_results)

        prompt = self._build_prompt(topic, aspect, extracted, calc_summary)
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior data analyst.\n\n"
            "## Work Style\n"
            "1. The data in the 'Computed Results' section below is precisely calculated; cite it directly\n"
            "2. Provide business interpretation on top of it: what does this number mean?\n"
            "3. Do not recalculate or question the numbers in 'Computed Results'\n"
            "4. If data is insufficient to support a conclusion, state it clearly\n\n"
            "## Output Structure\n"
            "### Key Metric -> Value -> Business Interpretation -> Data Source\n\n"
            "## Output Standards\n"
            "- Keep report units consistent (e.g., 100 million CNY / 10,000 vehicles)\n"
            "- Quantify trend descriptions (CAGR x%, not 'steady growth')\n"
            "- Explain business reasons for outliers"
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
            # Top companies
            tops = ms.get("top_3_companies", [])
            if tops:
                items = [f'{c["company"]}={c["share"]}%' for c in tops]
                parts.append(f'Top3: {"; ".join(items)}')

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
            f"{summary.get('market_shares_count', 0)} market shares"
        )

        return f"""# Data Analysis Task

## Topic
{topic}

## Dimension
{aspect}

## Data Overview
{data_line}

## Computed Results
{calc_summary}

---

Based on the above precise computed results, provide a professional data analysis interpretation.

Each conclusion should include:
1. **Key Metric**: Cite specific data
2. **Business Interpretation**: What market signal does this number convey?
3. **Trend Judgment**: Direction of change along the time dimension
4. **Data Limitations**: Any data quality issues that may affect conclusions

Note: Output only the analysis body; do not include any instructions from this prompt."""
