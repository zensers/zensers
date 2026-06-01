# -*- coding: utf-8 -*-
"""
Deep Financial Analysis Skill — Analysis Layer (Enhanced)

Three-layer architecture:
1. Computation Layer: PythonREPL calculates financial ratios (ROE/ROA/gross margin/debt ratio, etc.)
2. Analysis Layer: LLM makes professional judgments based on precise ratios
3. Output Layer: Structured analysis + composite scoring

Analysis capabilities:
- Financial health score (profitability/solvency/cash flow quality)
- Growth trend analysis (CAGR, marginal changes, drivers)
- Valuation analysis (PE/PB ranges, peer comparison, DCF simulation)
- Comprehensive investment value assessment (strengths/risks/catalysts)
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from src.skills.base import Skill

logger = logging.getLogger(__name__)


class StockAnalysisSkill(Skill):

    @property
    def name(self) -> str:
        return "stock_analysis"

    @property
    def description(self) -> str:
        return "Deep financial analysis: financial health/growth trend/valuation/investment value assessment"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "financial_health")
        symbol = kwargs.get("symbol", "")
        financial_data = kwargs.get("financial_data", {})
        industry_data = kwargs.get("industry_data", "")

        if not symbol:
            return self._failure("Please provide a stock symbol")

        # Step 1: Pre-compute financial ratios
        computed_ratios = await self._precompute_ratios(financial_data)

        llm = await self._get_llm()
        if not llm:
            return self._failure("llm_skill not available")

        if action == "financial_health":
            return await self._financial_health_analysis(llm, symbol, financial_data, computed_ratios)
        elif action == "growth_analysis":
            return await self._growth_analysis(llm, symbol, financial_data, computed_ratios)
        elif action == "valuation":
            return await self._valuation_analysis(llm, symbol, financial_data, industry_data, computed_ratios)
        elif action == "strategic_analysis":
            return await self._strategic_analysis(llm, symbol, financial_data, industry_data, computed_ratios)
        elif action == "full_report":
            return await self._full_report(llm, symbol, financial_data, industry_data, computed_ratios)
        else:
            return self._failure(f"Unsupported analysis type: {action}")

    async def _get_llm(self):
        from src.skills.registry import get_skill_registry
        reg = get_skill_registry()
        return reg.get("llm_skill")

    # ============ Computation Layer ============

    async def _precompute_ratios(self, data: Dict) -> Dict:
        """Precisely calculate financial ratios using PythonREPL"""
        ratios = {}

        # Extract key data
        rev = self._extract_number(data, ["revenue", "operating_revenue"])
        np = self._extract_number(data, ["net_profit", "net_profit_cn"])
        ta = self._extract_number(data, ["total_assets", "total_assets_cn"])
        te = self._extract_number(data, ["total_equity", "net_assets", "shareholder_equity"])
        gp = self._extract_number(data, ["gross_profit", "gross_profit_cn"])
        ocf = self._extract_number(data, ["operating_cash_flow", "operating_cash_flow_cn"])
        tl = self._extract_number(data, ["total_liabilities", "total_liabilities_cn"])
        cl = self._extract_number(data, ["current_liabilities", "current_liabilities_cn"])
        ca = self._extract_number(data, ["current_assets", "current_assets_cn"])
        inventory = self._extract_number(data, ["inventory", "inventory_cn"])
        ar = self._extract_number(data, ["accounts_receivable", "accounts_receivable_cn"])

        # Compute using PythonREPL
        from src.skills.registry import get_skill_registry
        reg = get_skill_registry()
        lc_python = reg.get("lc_python_repl")

        calc_input = {
            "revenue": rev, "net_profit": np, "total_assets": ta,
            "total_equity": te, "gross_profit": gp, "operating_cf": ocf,
            "total_liabilities": tl, "current_liabilities": cl,
            "current_assets": ca, "inventory": inventory, "accounts_receivable": ar,
        }
        calc_json = json.dumps(calc_input, ensure_ascii=False)

        if lc_python:
            code = f"""
import json
d = {calc_json}
r = {{}}
if d['net_profit'] and d['revenue'] and d['revenue'] != 0:
    r['net_margin'] = round(d['net_profit'] / d['revenue'] * 100, 2)
if d['gross_profit'] and d['revenue'] and d['revenue'] != 0:
    r['gross_margin'] = round(d['gross_profit'] / d['revenue'] * 100, 2)
if d['net_profit'] and d['total_equity'] and d['total_equity'] != 0:
    r['roe'] = round(d['net_profit'] / d['total_equity'] * 100, 2)
if d['net_profit'] and d['total_assets'] and d['total_assets'] != 0:
    r['roa'] = round(d['net_profit'] / d['total_assets'] * 100, 2)
if d['total_liabilities'] and d['total_assets'] and d['total_assets'] != 0:
    r['debt_ratio'] = round(d['total_liabilities'] / d['total_assets'] * 100, 2)
if d['current_assets'] and d['current_liabilities'] and d['current_liabilities'] != 0:
    r['current_ratio'] = round(d['current_assets'] / d['current_liabilities'], 2)
if d['operating_cf'] and d['net_profit'] and d['net_profit'] != 0:
    r['cash_quality'] = round(d['operating_cf'] / d['net_profit'], 2)
print(json.dumps(r))
"""
            try:
                py_result = await lc_python.execute(command=code)
                if py_result.get("success"):
                    output = str(py_result.get("result", ""))
                    jm = re.search(r'\{.*\}', output, re.DOTALL)
                    if jm:
                        ratios = json.loads(jm.group())
            except Exception as e:
                logger.warning(f"stock_analysis precompute_ratios failed: {e}")

        # Fallback calculation
        if not ratios:
            ratios = {}
            if np and rev and rev != 0:
                ratios["net_margin"] = round(np / rev * 100, 2)
            if gp and rev and rev != 0:
                ratios["gross_margin"] = round(gp / rev * 100, 2)
            if np and te and te != 0:
                ratios["roe"] = round(np / te * 100, 2)
            if tl and ta and ta != 0:
                ratios["debt_ratio"] = round(tl / ta * 100, 2)
            if ca and cl and cl != 0:
                ratios["current_ratio"] = round(ca / cl, 2)
            if ocf and np and np != 0:
                ratios["cash_quality"] = round(ocf / np, 2)

        return ratios

    def _extract_number(self, data: Dict, keys: List[str]) -> Optional[float]:
        """Extract numeric values from financial data"""
        for key in keys:
            val = data.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
        return None

    def _format_computed_ratios(self, ratios: Dict) -> str:
        """Format computed ratios for LLM consumption"""
        if not ratios:
            return ""
        parts = []
        if "gross_margin" in ratios:
            parts.append(f"Gross Margin: {ratios['gross_margin']}%")
        if "net_margin" in ratios:
            parts.append(f"Net Margin: {ratios['net_margin']}%")
        if "roe" in ratios:
            parts.append(f"ROE: {ratios['roe']}%")
        if "roa" in ratios:
            parts.append(f"ROA: {ratios['roa']}%")
        if "debt_ratio" in ratios:
            parts.append(f"Debt Ratio: {ratios['debt_ratio']}%")
        if "current_ratio" in ratios:
            parts.append(f"Current Ratio: {ratios['current_ratio']}")
        if "cash_quality" in ratios:
            parts.append(f"CF/Net Profit: {ratios['cash_quality']}")
        return " | ".join(parts)

    # ============ Analysis Layer ============

    async def _financial_health_analysis(self, llm, symbol: str, data: Dict, ratios: Dict) -> Dict[str, Any]:
        ratio_str = self._format_computed_ratios(ratios)
        ratio_section = f"\n\n## Precisely Computed Financial Ratios\n{ratio_str}\n" if ratio_str else ""
        
        prompt = f"""Analyze the financial health of {symbol}.

Analysis framework:
1. **Profitability**: Gross/net margin trends, ROE DuPont decomposition, industry comparison
2. **Solvency**: Debt ratio, current ratio, interest coverage, cash-to-short-term-debt ratio
3. **Cash Flow Quality**: Operating cash flow vs net profit alignment, free cash flow status
4. **Operating Efficiency**: Inventory turnover, receivables turnover, asset turnover

Give a clear judgment for each dimension (Healthy/Caution/Risk), supported by data.
Composite financial health score (out of 100).{ratio_section}

Available financial data:
{self._format_data(data)}"""
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior CFA charterholder, expert in financial statement analysis and health assessment.\n\n"
            "## Expertise\n"
            "- Three-statement quality assessment and red flag identification\n"
            "- DuPont decomposition analysis (ROE breakdown)\n"
            "- Cash flow quality analysis (FCFF/FCFE)\n"
            "- Financial health scorecard (5-dimension composite scoring)\n\n"
            "## Analysis Method\n"
            "1. Clear judgment for each dimension (Healthy/Caution/Risk)\n"
            "2. All judgments must be supported by specific financial data\n"
            "3. Focus on trend changes rather than single-period data\n"
            "4. Identify the impact of accounting policy changes on statements\n\n"
            "## Output Specification\n"
            "- Provide a composite financial health score (out of 100)\n"
            "- Include a key financial indicator trend table\n"
            "- Highlight areas requiring focused improvement"
        ))
        return self._result(result, symbol, "financial_health")

    async def _growth_analysis(self, llm, symbol: str, data: Dict, ratios: Dict) -> Dict[str, Any]:
        ratio_str = self._format_computed_ratios(ratios)
        ratio_section = f"\n\n## Precisely Computed Financial Ratios\n{ratio_str}\n" if ratio_str else ""
        
        prompt = f"""Analyze the growth trend for {symbol}.

Analysis dimensions:
1. **Revenue Growth Analysis**: Revenue CAGR, segment-level growth drivers, volume/price decomposition
2. **Profit Growth Analysis**: Net profit growth trend, drivers, marginal changes in earnings quality
3. **Cash Flow & Capital Allocation**: Free cash flow trend, capex efficiency, dividend/buyback strategy
4. **Growth Sustainability**: Industry headroom and company market share, competitive advantage durability, risk factors

Requirements: Distinguish one-time vs sustainable factors, identify inflection point signals (if any).
Provide a growth quality score (out of 100).{ratio_section}

Available financial data:
{self._format_data(data)}"""
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior industry researcher, expert in corporate growth analysis and growth quality assessment.\n\n"
            "## Expertise\n"
            "- Revenue growth decomposition (volume/price, product mix, geographic expansion)\n"
            "- Profit growth quality analysis (sustainability of growth sources)\n"
            "- Cash flow vs growth alignment assessment\n"
            "- Growth ceiling assessment and S-curve analysis\n\n"
            "## Analysis Method\n"
            "1. Calculate trailing 3-5 year revenue/profit CAGR as baseline\n"
            "2. Distinguish organic growth vs M&A-driven growth\n"
            "3. Assess growth sustainability (whether drivers can persist)\n"
            "4. Compare with industry growth to determine relative performance\n\n"
            "## Output Specification\n"
            "- Provide a growth quality rating (Excellent/Good/Fair/Caution)\n"
            "- Include quantitative decomposition of growth drivers\n"
            "- Highlight core assumptions and risks for growth sustainability"
        ))
        return self._result(result, symbol, "growth_analysis")

    async def _valuation_analysis(self, llm, symbol: str, data: Dict, industry: str, ratios: Dict) -> Dict[str, Any]:
        ratio_str = self._format_computed_ratios(ratios)
        ratio_section = f"\n\n## Precisely Computed Financial Ratios\n{ratio_str}\n" if ratio_str else ""
        
        prompt = f"""Perform valuation analysis for {symbol}.

Analysis framework:
1. **Relative Valuation**: Current PE/PB/PS values and historical percentiles, peer comparison
2. **DCF Framework (Simulation)**: Revenue growth assumptions, margin assumptions, WACC simulation, sensitivity analysis
3. **Valuation Conclusion**: Current valuation level assessment (Undervalued/Fair/Overvalued), core assumption uncertainty

Requirements: Distinguish valuation assumptions from facts, clearly identify uncertainties, provide a valuation range.{ratio_section}

Available financial data:
{self._format_data(data)}

Industry background: {industry if industry else 'Not provided'}"""
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior valuation analyst, expert in DCF/comparable company/comparable transaction valuation methodologies.\n\n"
            "## Expertise\n"
            "- DCF model construction (FCF forecasting, WACC calculation, terminal value assumptions)\n"
            "- Comparable company analysis (PE/PB/PS/EV/EBITDA multi-dimension)\n"
            "- Scenario analysis\n"
            "- Valuation bias identification and correction\n\n"
            "## Analysis Method\n"
            "1. DCF as core approach, clearly list key assumptions (growth rate/WACC/terminal growth rate)\n"
            "2. Justify comparable company selection\n"
            "3. Perform sensitivity analysis on key assumptions\n"
            "4. Assess historical percentile of current valuation level\n\n"
            "## Output Specification\n"
            "- Provide a valuation range rather than a single target price\n"
            "- Include a sensitivity analysis table\n"
            "- Identify upside catalysts and downside risks for valuation"
        ))
        return self._result(result, symbol, "valuation")

    async def _strategic_analysis(self, llm, symbol: str, data: Dict, industry: str, ratios: Dict) -> Dict[str, Any]:
        ratio_str = self._format_computed_ratios(ratios)
        ratio_section = f"\n\n## Precisely Computed Financial Ratios\n{ratio_str}\n" if ratio_str else ""
        
        prompt = f"""Perform strategic investment analysis for {symbol}.

Analysis dimensions:
1. **Hidden Value Identification**: Assets not reflected in traditional valuation (brands/patents/data assets/user networks)
2. **Growth Options**: Option value of new markets/new products/new technologies
3. **M&A Value**: Value as an acquisition target (control premium/synergies)
4. **Strategic Positioning**: Position and differentiation in evolving industry landscape

Requirements: Provide qualitative judgment and quantitative estimate for each hidden value item.
Provide valuation comparison with and without hidden values.{ratio_section}

Available financial data:
{self._format_data(data)}

Industry background: {industry if industry else 'Not provided'}"""
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior strategic investment analyst, expert in corporate hidden value and option value assessment.\n\n"
            "## Expertise\n"
            "- Real option pricing (expansion option/deferral option/abandonment option)\n"
            "- Intangible asset valuation (brands/patents/data assets/user networks)\n"
            "- Platform economics and new business model valuation\n"
            "- M&A synergy value estimation\n\n"
            "## Analysis Method\n"
            "1. Identify hidden value sources not fully captured by traditional financial valuation\n"
            "2. Provide qualitative judgment and quantitative estimate for each hidden value item\n"
            "3. Assess prerequisites and timeline for hidden value realization\n"
            "4. Analyze whether the market has already partially priced these hidden values\n\n"
            "## Output Specification\n"
            "- List hidden value sources and estimated values by item\n"
            "- Include realization conditions and probability assessment\n"
            "- Provide valuation comparison with and without hidden values"
        ))
        return self._result(result, symbol, "strategic_analysis")

    async def _full_report(self, llm, symbol: str, data: Dict, industry: str, ratios: Dict) -> Dict[str, Any]:
        ratio_str = self._format_computed_ratios(ratios)
        ratio_section = f"\n## Financial Ratios\n{ratio_str}\n" if ratio_str else ""
        
        prompt = f"""Perform a comprehensive investment value analysis for {symbol} and output a structured research report.

## I. Company Overview
Core business, industry position, key characteristics of business model

## II. Financial Analysis
Revenue/profit/cash flow trends, profitability (gross margin/net margin/ROE)
Financial health (debt ratio/liquidity), year-over-year industry comparison{ratio_section}

## III. Growth Analysis
Historical growth drivers, future growth drivers, risk factors

## IV. Valuation Analysis
Current valuation level, valuation framework simulation, core assumptions

## V. Investment Conclusion
Strengths, risks, catalysts, comprehensive judgment

Available financial data:
{self._format_data(data)}

Industry background: {industry if industry else 'Not provided'}"""
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior chief researcher at a securities firm, specializing in writing in-depth research reports.\n\n"
            "## Expertise\n"
            "- Company deep-dive reports (business model/competitive advantage/financial projections)\n"
            "- Industry thematic reports (industry chain/competitive landscape/development trends)\n"
            "- Investment value analysis (investment thesis/catalysts/risk-reward ratio)\n"
            "- Follow-up reports (quarterly commentary/event-driven analysis)\n\n"
            "## Writing Standards\n"
            "1. Each paragraph begins with a core judgment, followed by logical reasoning, and finally data support\n"
            "2. 300 words of strong argument > 3000 words of vague discussion\n"
            "3. Key financial data must specify the period\n"
            "4. Investment rating must be clearly given with reasoning\n\n"
            "## Output Specification\n"
            "- Use professional report language\n"
            "- Risk disclosures as a standalone section\n"
            "- Include disclaimer"
        ))
        return self._result(result, symbol, "full_report")

    def _format_data(self, data: Dict) -> str:
        if not data:
            return "(No financial data available, please fetch via stock_data skill first)"
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"\n{key}:")
                for item in value[:5]:
                    lines.append(f"  {item}")
            elif isinstance(value, dict):
                lines.append(f"\n{key}:")
                for k, v in list(value.items())[:10]:
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines[:50])

    def _result(self, llm_result: Dict, symbol: str, analysis_type: str) -> Dict[str, Any]:
        return {
            "success": llm_result.get("success", False),
            "content": llm_result.get("content", ""),
            "symbol": symbol,
            "analysis_type": analysis_type,
            "agent_type": "stock_analysis",
        }
