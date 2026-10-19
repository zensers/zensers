# -*- coding: utf-8 -*-
"""
Technology Trend Analysis Skill

Analysis framework:
1. Technology readiness assessment: TRL level evaluation
2. Technology roadmap: mainstream route comparison
3. Industrialization barriers: cost/yield/ecosystem analysis
4. Disruption risk: impact of non-continuous innovation

Characteristics: purely qualitative analysis, focused on technology path judgment and competitive landscape understanding.
"""
import logging
from typing import Any, Dict, List
from src.skills.base import Skill
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


class TechTrendSkill(Skill):
    """Technology Trend Analysis Skill"""

    @property
    def name(self) -> str:
        return "tech_trend"

    @property
    def description(self) -> str:
        return "Technology trend analysis: TRL assessment/roadmap comparison/industrialization barriers/disruption risks"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        topic = kwargs.get("topic", "")
        aspect = kwargs.get("aspect", "")
        data_points = kwargs.get("data_points", [])
        sources = kwargs.get("sources", [])

        if not topic:
            return self._failure("topic is required")

        prompt = self._build_prompt(topic, aspect, data_points, sources)
        result = await call_llm(prompt=prompt, system_prompt=(
            "You are a senior technology industry analyst, specializing in technology development trends and industrialization path analysis.\n\n"
            "## Expertise\n"
            "- Technology roadmap comparative analysis\n"
            "- Technology readiness assessment (TRL levels)\n"
            "- Patent analysis and technology innovation direction\n"
            "- Technology industrialization path and timeline\n\n"
            "## Analysis Framework (must follow)\n"
            "### 1. Technology Status Assessment\n"
            "Identify current mainstream technology routes, evaluate key performance indicators:\n"
            "- Technology principle differences\n"
            "- Performance indicator comparison (efficiency/cost/reliability, etc.)\n"
            "- TRL level (1-9): Proof of concept → Lab → Pilot → Demonstration → Commercialization\n\n"
            "### 2. Technology Evolution Direction\n"
            "Next-generation technology development path and timeline expectations:\n"
            "- Short-term (1-2 years): Incremental improvement\n"
            "- Medium-term (3-5 years): Generational upgrade\n"
            "- Long-term (5+ years): Disruptive replacement\n\n"
            "### 3. Competitive Landscape\n"
            "Each major player's positioning on technology routes:\n"
            "- Technology path selection and rationale\n"
            "- Patent barriers and core IP\n"
            "- R&D investment intensity comparison\n\n"
            "### 4. Industrialization Barriers\n"
            "Core bottlenecks from lab to mass production:\n"
            "- Cost barriers: current cost vs acceptable cost\n"
            "- Process barriers: yield/consistency/scaling\n"
            "- Ecosystem barriers: upstream/downstream support/standards/compatibility\n\n"
            "### 5. Disruption Risk\n"
            "Potential impact of non-continuous innovation on existing landscape:\n"
            "- Technology substitution possibility\n"
            "- Cross-industry competitive threat\n"
            "- Regulatory/ethical risks\n\n"
            "## Output Specification\n"
            "- Distinguish between proven technologies and laboratory technologies\n"
            "- Annotate time expectations with confidence level (High/Medium/Low)\n"
            "- Industrialization timeline should provide specific year estimates"
        ))

        return {
            "success": result.get("success", False),
            "content": result.get("content", ""),
            "agent_type": "tech_trend",
        }

    def _build_prompt(self, topic: str, aspect: str, data_points: List[Dict], sources: List[Dict]) -> str:
        data_str = "\n".join([
            f"- {dp.get('title', '')}" for dp in data_points[:20]
        ]) if data_points else "No relevant data"

        return f"""# Technology Trend Analysis Task

## Topic
{topic}

## Dimension
{aspect}

## Related Data
{data_str}

---

Please perform a professional analysis of the technology development trend for {topic}. Output the analysis directly."""
