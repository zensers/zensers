"""Cross-Synthesis Agent - combines desk research + survey into integrated insights."""
import json, logging, re
from typing import Any, Dict, Optional
from src.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class CrossSynthesisAgent:
    """Cross-Synthesis Agent - combines desk research + survey into integrated insights."""

    def __init__(self, agent_id: str, llm_skill=None):
        self.agent_id = agent_id
        self._llm_skill = llm_skill
        self._prompt_manager = PromptManager.get_instance()

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cross-synthesis of desk research and survey data."""
        topic = params.get("topic", "")
        desk_content = params.get("desk_research_content", "")
        survey_content = params.get("survey_content", "")
        responses_count = params.get("responses_count", 0)

        if not desk_content or not survey_content:
            logger.warning(f"[{self.agent_id}] Missing data for cross-synthesis")
            return self._empty_result("insufficient data")

        try:
            system_prompt = self._prompt_manager.load("agents", "survey_cross_synthesis")
            user_prompt = self._prompt_manager.render(
                "agents", "survey_cross_synthesis",
                topic=topic, desk_research_content=desk_content[:3000],
                survey_content=survey_content[:3000], responses_count=str(responses_count))
        except FileNotFoundError:
            logger.warning(f"[{self.agent_id}] Prompt file not found")
            return self._fallback(topic, desk_content, survey_content, responses_count)

        if not self._llm_skill:
            return self._fallback(topic, desk_content, survey_content, responses_count)

        try:
            import asyncio
            result = await asyncio.wait_for(
                self._llm_skill.execute(
                    prompt=user_prompt, system_prompt=system_prompt,
                    temperature=0.5, max_tokens=1500), timeout=60)
            if result.get("success"):
                return self._parse_output(result["content"])
        except Exception as e:
            logger.error(f"[{self.agent_id}] LLM call failed: {e}")

        return self._fallback(topic, desk_content, survey_content, responses_count)

    def _parse_output(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return {"success": True, "combined_summary": data.get("combined_summary", ""),
                        "combined_conclusion": data.get("combined_conclusion", ""),
                        "cross_validations": data.get("cross_validations", []),
                        "contradictions": data.get("contradictions", []), "error": None}
            except json.JSONDecodeError:
                pass
        return self._empty_result("failed to parse LLM response")

    def _fallback(self, topic, desk, survey, count):
        return {"success": True,
                "combined_summary": f"Combined Research Summary\nDesk Research:\n{desk[:500]}\n\nSurvey (n={count}):\n{survey[:500]}",
                "combined_conclusion": f"Research Conclusion\nIntegrated analysis of '{topic}' from desk research and survey data (n={count}).",
                "cross_validations": [], "contradictions": [], "error": None}

    def _empty_result(self, reason):
        return {"success": False, "combined_summary": "", "combined_conclusion": "",
                "cross_validations": [], "contradictions": [], "error": reason}
