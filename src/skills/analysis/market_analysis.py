# -*- coding: utf-8 -*-
"""
Market Analysis Skill - Enhanced

Three-layer architecture:
1. Computation layer: PythonREPLTool extracts numerical data, calculates market metrics
2. Analysis layer: LLM uses SWOT/PEST/Porter's Five Forces frameworks for analysis
3. Output layer: Structured Markdown

Supported analysis frameworks:
- SWOT (Strengths/Weaknesses/Opportunities/Threats)
- PEST (Political/Economic/Social/Technological)
- Porter's Five Forces (Suppliers/Buyers/New Entrants/Substitutes/Competition)
- Market Structure (Concentration/Barriers to Entry)
"""
import logging
from typing import Any, Dict, List, Optional
from src.skills.base import Skill, SkillConfig

logger = logging.getLogger(__name__)


class MarketAnalysisSkill(Skill):

    @property
    def name(self) -> str:
        return "market_analysis"

    @property
    def description(self) -> str:
        return "Professional market analysis: SWOT/PEST/Porter's Five Forces + data computation"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        topic = kwargs.get("topic", "")
        aspect = kwargs.get("aspect", "")
        data_points = kwargs.get("data_points", [])
        sources = kwargs.get("sources", [])
        previous_content = kwargs.get("previous_content", [])
        framework = kwargs.get("framework", "all")

        if not topic:
            return self._failure("topic is required")

        # Select analysis framework
        frameworks = self._select_frameworks(framework)

        # Step 1: Pre-compute market metrics with PythonREPL
        calc_summary = await self._precompute_metrics(data_points)

        # Step 2: LLM framework analysis
        from src.skills.registry import get_skill_registry
        reg = get_skill_registry()
        llm = reg.get("llm_skill")
        if not llm:
            return self._failure("llm_skill not available")

        prompt = self._build_analysis_prompt(
            topic, aspect, frameworks, data_points, sources, previous_content, calc_summary
        )
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a world-class investment bank chief analyst, writing professional research reports for global investors.\n\n"
            "## Expertise\n"
            "- Deep analysis of industry structure and competitive dynamics\n"
            "- Quantification of market size and growth drivers\n"
            "- Industry chain value distribution and profit pool analysis\n"
            "- Technology trends and disruptive innovation identification\n\n"
            "## Analysis Standards (McKinsey / Goldman Sachs research report quality)\n"
            "1. Use appropriate analysis frameworks (e.g., PEST macro, Porter's Five Forces meso, SWOT micro)\n"
            "2. Every argument must be supported by data; cite specific values rather than vague descriptions\n"
            "3. Data and analysis should naturally integrate into a coherent narrative, not disjointed fact+opinion paragraphs\n"
            "4. Cross-validate with multiple data sources; explain reasoning for conflicting data\n"
            "5. Provide probability judgments or scenario analysis for uncertain conclusions\n\n"
            "## Output Standards\n"
            "1. Output analysis body directly; no conversational prefixes\n"
            "2. Organize content using Markdown format\n"
            "3. Bold key data points\n"
            "4. Each paragraph starts with a clear judgment statement, followed by logical reasoning and data support\n"
            "5. Paragraphs should have logical progression, forming a complete analysis chain\n"
            "6. Avoid template-style 'Fact: ... Analyst View: ...' segmented structure; let analysis flow naturally"
        ))

        if not result.get("success"):
            return result

        return {
            "success": True,
            "content": result.get("content", ""),
            "framework": frameworks,
            "calc_summary": calc_summary,
            "data_points": data_points,
            "sources": sources,
            "agent_type": "market_analysis",
        }

    async def _precompute_metrics(self, data_points: List[Dict]) -> str:
        """
        Extract numeric values from data points and compute market metrics using PythonREPL
        """
        import re
        
        # Extract time series data
        time_data = []
        share_data = []
        
        for dp in data_points[:100]:
            text = f"{dp.get('title', '')} {dp.get('content', '')}"
            
            # Year + value
            matches = re.findall(r'(20\d{2})[年\s].*?(\d+[\.\d]*)\s*(亿|万|千|百|%|亿元)', text)
            for year, val, unit in matches:
                time_data.append({"year": int(year), "value": float(val), "unit": unit})
            
            # Market share
            share_m = re.findall(r'([\u4e00-\u9fa5]{2,8})[：:]\s*(\d+[\.\d]*)\s*[%％]', text)
            for company, share in share_m:
                share_data.append({"company": company, "share": float(share)})

        if not time_data and not share_data:
            return "No computable numeric data extracted"

        # Compute with PythonREPL
        from src.skills.registry import get_skill_registry
        reg = get_skill_registry()
        lc_python = reg.get("lc_python_repl")

        if not lc_python:
            return self._compute_fallback(time_data, share_data)

        code_lines = ["import json, statistics"]
        code_lines.append("result = {}")

        if time_data:
            years_str = str([d["year"] for d in time_data])
            values_str = str([d["value"] for d in time_data])
            code_lines.append(f"years = {years_str}")
            code_lines.append(f"values = {values_str}")
            code_lines.append("n = len(values)")
            code_lines.append("if n >= 2 and years[-1] != years[0] and values[0] > 0:")
            code_lines.append("    cagr = ((values[-1] / values[0]) ** (1 / (years[-1] - years[0]))) - 1")
            code_lines.append("    result['cagr'] = round(cagr * 100, 2)")
            code_lines.append("    result['cagr_period'] = f'{years[0]}-{years[-1]}'")
            code_lines.append("    result['start_value'] = values[0]")
            code_lines.append("    result['end_value'] = values[-1]")

        if share_data:
            companies_str = str([s["company"] for s in share_data])
            shares_str = str([s["share"] for s in share_data])
            code_lines.append(f"companies = {companies_str}")
            code_lines.append(f"shares = {shares_str}")
            code_lines.append("sorted_shares = sorted(shares, reverse=True)")
            code_lines.append("result['cr3'] = round(sum(sorted_shares[:3]), 2) if len(sorted_shares) >= 3 else None")
            code_lines.append("result['cr5'] = round(sum(sorted_shares[:5]), 2) if len(sorted_shares) >= 5 else None")
            code_lines.append("result['hhi'] = round(sum(v**2 for v in sorted_shares), 0)")
            code_lines.append("hhi = result['hhi']")
            code_lines.append("if hhi >= 2500: result['market_structure'] = 'Highly concentrated (Monopolistic)'")
            code_lines.append("elif hhi >= 1500: result['market_structure'] = 'Moderately concentrated (Oligopolistic)'")
            code_lines.append("elif hhi >= 1000: result['market_structure'] = 'Low concentration (Competitive)'")
            code_lines.append("else: result['market_structure'] = 'Fragmented (Perfectly competitive)'")

        code_lines.append("print(json.dumps(result, ensure_ascii=False))")
        code = "\n".join(code_lines)

        try:
            py_result = await lc_python.execute(command=code)
            if py_result.get("success"):
                output = str(py_result.get("result", ""))
                json_match = re.search(r'\{.*\}', output, re.DOTALL)
                if json_match:
                    import json as _json
                    calc = _json.loads(json_match.group())
                    return self._format_calc_result(calc, time_data, share_data)
        except Exception as e:
            logger.warning(f"market_analysis precompute_metrics failed: {e}")

        return self._compute_fallback(time_data, share_data)

    def _compute_fallback(self, time_data: List[Dict], share_data: List[Dict]) -> str:
        """Pure Python fallback computation"""
        parts = []
        if time_data and len(time_data) >= 2:
            values = [d["value"] for d in time_data]
            years = [d["year"] for d in time_data]
            unit = time_data[0].get("unit", "")
            if years[-1] != years[0] and values[0] > 0:
                cagr = ((values[-1] / values[0]) ** (1 / (years[-1] - years[0]))) - 1
                parts.append(f"Scale: {values[0]}{unit}→{values[-1]}{unit} ({years[0]}-{years[-1]}), CAGR={cagr*100:.1f}%")
        if share_data and len(share_data) >= 3:
            sv = sorted([s["share"] for s in share_data], reverse=True)
            cr3 = sum(sv[:3])
            hhi = sum(v**2 for v in sv)
            parts.append(f"Concentration: CR3={cr3:.1f}%, HHI={hhi:.0f}")
        return " | ".join(parts) if parts else ""

    def _format_calc_result(self, calc: Dict, time_data: List, share_data: List) -> str:
        parts = []
        if "cagr" in calc:
            parts.append(
                f"Market size: {calc.get('start_value')}→{calc.get('end_value')} "
                f"({calc.get('cagr_period')}), CAGR={calc['cagr']}%"
            )
        if "cr3" in calc and calc["cr3"]:
            parts.append(f"CR3={calc['cr3']}%, CR5={calc.get('cr5', 'N/A')}%, HHI={calc.get('hhi', 0):.0f}")
        if "market_structure" in calc:
            parts.append(f"Structure: {calc['market_structure']}")
        if time_data and not parts:
            parts.append(f"Extracted {len(time_data)} time series data points")
        if share_data and not parts:
            parts.append(f"Extracted {len(share_data)} market share data points")
        return " | ".join(parts)

    def _select_frameworks(self, framework: str) -> list:
        all_frameworks = {
            "swot": "SWOT Analysis (Strengths/Weaknesses/Opportunities/Threats)",
            "pest": "PEST Analysis (Political/Economic/Social/Technological)",
            "porter": "Porter's Five Forces (Supplier Power/Buyer Power/Threat of New Entrants/Threat of Substitutes/Industry Rivalry)",
            "market_structure": "Market Structure Analysis (CRn Concentration/Barriers to Entry/Economies of Scale)",
        }
        if framework == "all":
            return list(all_frameworks.values())
        elif framework in all_frameworks:
            return [all_frameworks[framework]]
        else:
            return [all_frameworks.get("swot", "SWOT Analysis")]

    def _build_analysis_prompt(self, topic, aspect, frameworks, data_points, sources, previous_content, calc_summary):
        data_summary = f"\nCollected {len(data_points)} data points from {len(sources)} sources." if data_points else ""
        content_summary = ""
        if previous_content:
            total_chars = sum(len(c.get("content", "")) for c in previous_content)
            content_summary = f"\nPrevious analysis: {len(previous_content)} articles, approx. {total_chars} characters."
        frameworks_str = "\n".join(f"- {f}" for f in frameworks)
        calc_section = f"\n## Pre-computed Metrics\n{calc_summary}\n" if calc_summary else ""

        return (
            f"Please conduct a professional market analysis on the following topic.\n\n"
            f"## Research Topic\n{topic}\n\n"
            f"## Analysis Dimension\n{aspect}\n\n"
            f"## Required Analysis Frameworks\n{frameworks_str}\n\n"
            f"## Available Data\n{data_summary}{content_summary}"
            f"{calc_section}\n"
            f"## Analysis Requirements\n"
            f"1. Provide clear judgments for each framework dimension (not vague descriptions)\n"
            f"2. Judgments must be supported by data\n"
            f"3. Data in 'Pre-computed Metrics' is precisely calculated; cite it directly\n"
            f"4. Identify key assumptions and uncertainties\n"
            f"5. Prioritize analysis depth over length\n\n"
            f"## Output Format\n"
            f"Organize by analysis framework sections, each containing: Core Judgment -> Evidence -> Reasoning -> Uncertainty Notes"
        )
