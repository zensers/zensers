# -*- coding: utf-8 -*-
"""Risk Analysis Skill"""
import logging
from typing import Any, Dict, List
from src.skills.base import Skill, SkillConfig

logger = logging.getLogger(__name__)


class RiskAnalysisSkill(Skill):

    @property
    def name(self) -> str:
        return "risk_analysis"

    @property
    def description(self) -> str:
        return "Risk analysis: risk identification/probability x impact matrix/scenario analysis/mitigation measures"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        topic = kwargs.get("topic", "")
        aspect = kwargs.get("aspect", "")
        data_points = kwargs.get("data_points", [])
        sources = kwargs.get("sources", [])
        if not topic:
            return self._failure("topic is required")

        from src.skills.registry import get_skill_registry
        reg = get_skill_registry()
        llm = reg.get("llm_skill")
        if not llm:
            return self._failure("llm_skill not available")

        prompt = self._build_prompt(topic, aspect, data_points, sources)
        result = await llm.execute(prompt=prompt, system_prompt=(
            "You are a senior risk management analyst.\n\n"
            "## Expertise\n"
            "- Risk matrix construction (Probability x Impact)\n"
            "- Tail risk and black swan event identification\n"
            "- Risk transmission channels and cascade effects\n"
            "- Stress testing and scenario analysis\n\n"
            "## Analysis Framework\n"
            "### 1. Risk Register\n"
            "List core risks by category; each risk includes:\n"
            "- Risk name + brief description\n"
            "- Risk type: Policy/Technology/Competition/Operational/Macro\n"
            "- Time horizon: Short-term/Mid-term/Long-term\n\n"
            "### 2. Risk Assessment Matrix\n"
            "- Probability: High (>60%) / Medium (20-60%) / Low (<20%)\n"
            "- Impact: Severe/Significant/Minor\n"
            "- Composite rating: Critical/Important/Moderate/Minor\n\n"
            "### 3. Risk Transmission Path\n"
            "- Direct consequence + Secondary impact + Potential beneficiaries\n\n"
            "### 4. Scenario Analysis\n"
            "- Optimistic: Major risks do not materialize\n"
            "- Baseline: Most likely outcome\n"
            "- Pessimistic: Multiple risks materialize simultaneously\n\n"
            "### 5. Mitigation Measures\n"
            "- Existing hedges + Recommended actions + Monitoring indicators"
        ))
        return {
            "success": result.get("success", False),
            "content": result.get("content", ""),
            "agent_type": "risk_analysis",
        }

    def _build_prompt(self, topic: str, aspect: str, data_points: List[Dict], sources: List[Dict]) -> str:
        data_str = "\n".join([
            f"- {dp.get('title', '')}" for dp in data_points[:20]
        ]) if data_points else "No relevant data"
        return f"""# Risk Analysis Task

## Topic
{topic}

## Dimension
{aspect}

## Related Data
{data_str}

---

Please conduct a professional analysis of core risks related to {topic}. Output the analysis body directly."""
