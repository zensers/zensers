# -*- coding: utf-8 -*-
"""
Policy Analysis Skill

Analysis framework:
1. Policy inventory: Identify enacted/upcoming core policies
2. Impact assessment: Quantify effects of subsidies/taxes/access restrictions
3. Transmission channels: Policy -> Industry chain links -> Competitive landscape
4. Winners/Losers analysis: Differential impacts on various companies
5. Policy risk: Scenario analysis for phase-out/policy shifts

Characteristics: Purely qualitative analysis; core is semantic understanding of policy text and impact chain reasoning.
"""
import logging
from typing import Any, Dict, List
from src.skills.base import Skill

logger = logging.getLogger(__name__)


class PolicyAnalysisSkill(Skill):
    """Policy Analysis Skill"""

    @property
    def name(self) -> str:
        return "policy_analysis"

    @property
    def description(self) -> str:
        return "Policy analysis: policy impact assessment/transmission channels/winners-losers/scenario analysis"

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
            "You are a senior policy research analyst specializing in industrial policy analysis and policy impact assessment.\n\n"
            "## Expertise\n"
            "- Policy text interpretation and key point extraction\n"
            "- Policy strength and enforcement intensity assessment\n"
            "- Policy transmission mechanisms to industry landscape\n"
            "- Policy risk scenario analysis\n\n"
            "## Analysis Framework (Mandatory)\n"
            "### 1. Policy Inventory\n"
            "List core enacted and upcoming policies directly affecting the industry, including:\n"
            "- Policy name/issuing agency/release date/core points\n"
            "- Policy type (incentive/restrictive/regulatory/subsidy)\n\n"
            "### 2. Impact Assessment\n"
            "Rate each policy by intensity:\n"
            "- Strong: Directly impacts industry landscape, changes competition rules\n"
            "- Medium: Structural impact, changes marginal conditions\n"
            "- Weak: Guidance only, limited impact\n\n"
            "### 3. Transmission Channels\n"
            "Analyze how policies transmit through industry chain links:\n"
            "- Policy -> Supply side (capacity/access)\n"
            "- Policy -> Demand side (subsidies/consumer incentives)\n"
            "- Policy -> Cost side (taxes/environmental)\n"
            "- Policy -> Competition side (antitrust/foreign investment access)\n\n"
            "### 4. Winners/Losers\n"
            "Identify differential impacts on different types of enterprises\n\n"
            "### 5. Scenario Analysis\n"
            "Optimistic/Baseline/Pessimistic three scenarios\n\n"
            "## Output Standards\n"
            "- Distinguish enacted policies (published) from expected policies (rumors/draft for comment)\n"
            "- Each judgment must cite supporting policy provisions\n"
            "- Mark confidence levels for uncertain policy directions"
        ))

        return {
            "success": result.get("success", False),
            "content": result.get("content", ""),
            "agent_type": "policy_analysis",
        }

    def _build_prompt(self, topic: str, aspect: str, data_points: List[Dict], sources: List[Dict]) -> str:
        data_str = "\n".join([
            f"- {dp.get('title', '')}" for dp in data_points[:20]
        ]) if data_points else "No relevant data"

        return f"""# Policy Analysis Task

## Topic
{topic}

## Dimension
{aspect}

## Related Data
{data_str}

---

Please conduct a professional analysis of policies related to {topic}. Output the analysis body directly."""
