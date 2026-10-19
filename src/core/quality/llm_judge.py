"""
LLMJudgeChecker — LLM-as-judge semantic quality checker (G3-FIX-1)

Serves as a supplement to rule-based checkers (30% weight).
Uses call_llm_sync(routing_hint=...) for unified LLM routing.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from .checkers import BaseQualityChecker, QualityResult

logger = logging.getLogger(__name__)


class LLMJudgeChecker(BaseQualityChecker):
    """LLM-as-judge semantic quality checker (30% weight, rule checkers 70%)"""

    def __init__(self, threshold: float = 75.0):
        super().__init__(threshold)
        self._client = None

    def get_checker_type(self) -> str:
        return "llm_judge"

    def calculate_score(self, data: Dict, context: Optional[Dict] = None) -> float:
        content = data.get("content", "")
        if not content:
            return 0.0
        try:
            response = self._call_llm_sync(self._build_judge_prompt(content, context))
            scores = self._parse_response(response)
            if not scores:
                logger.warning("LLM judge empty, retrying with stricter prompt")
                response = self._call_llm_sync(self._build_strict_prompt(content, context))
                scores = self._parse_response(response)
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}, falling back to conservative score")
            return 40.0
        if not scores:
            return 35.0
        return min(
            scores.get("logic_score", 0) * 0.30 +
            scores.get("quant_score", 0) * 0.25 +
            scores.get("counter_score", 0) * 0.25 +
            scores.get("consistency_score", 0) * 0.20, 100.0)

    def _build_strict_prompt(self, content: str, context: Optional[Dict]) -> str:
        return f"""You are a strict quality reviewer. Output ONLY valid JSON.

CRITICAL: Your response must contain ONLY a JSON object. No other text.

{{
  "logic_score": <0-100 integer>,
  "quant_score": <0-100 integer>,
  "counter_score": <0-100 integer>,
  "consistency_score": <0-100 integer>
}}

Content: {content[:4000]}"""

    def _call_llm_sync(self, prompt: str) -> str:
        """Synchronous LLM call via unified call_llm_sync."""
        from src.core.llm_client import call_llm_sync
        from src.config.llm_profiles import RoutingHint

        result = call_llm_sync(
            prompt=prompt,
            system_prompt="You are a strict quality reviewer. Output only JSON.",
            max_tokens=500,
            temperature=0.3,
            routing_hint=RoutingHint(action="quality_judge"),
        )
        if result.get("success"):
            return result.get("content", "")
        logger.warning(f"LLM judge call failed: {result.get('message', 'unknown')}")
        return ""

    def _build_judge_prompt(self, content: str, context: Optional[Dict]) -> str:
        return f"""You are a strict quality reviewer. Review this content.

1. logic_score (0-100): Core judgment supported by data? Complete reasoning chain?
2. quant_score (0-100): Numerical relationships correct? Sum of parts = total?
3. counter_score (0-100): Specific boundary conditions or templated phrasing?
4. consistency_score (0-100): Same metric with different values across paragraphs?

Content: {content[:4000]}

Output ONLY valid JSON (use actual integer values, NOT ranges like 0-100):
{{"logic_score":75,"quant_score":60,"counter_score":50,"consistency_score":80,"issues":["issue1"],"verdict":"fail"}}"""

    def _parse_response(self, response: str) -> Dict[str, float]:
        try:
            s, e = response.find('{'), response.rfind('}') + 1
            if s >= 0 and e > s:
                parsed = json.loads(response[s:e])
                if isinstance(parsed, dict):
                    return parsed
                logger.warning(f"LLM judge response parsed but not a dict: type={type(parsed).__name__}")
                return {}
            logger.warning(f"LLM judge response has no JSON object: len={len(response)}, preview={response[:200]}")
            return {}
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"LLM judge JSON parse failed: {e}, response preview={response[:200]}")
            return {}

    def generate_suggestions(self, score: float, data: Dict, context: Optional[Dict] = None) -> List[str]:
        if score >= self.threshold:
            return []
        suggestions = []
        if score < 50:
            suggestions.append("分析质量严重不足，建议重新搜索更多数据源并重构分析逻辑")
        elif score < self.threshold:
            suggestions.append("分析质量未达标，建议补充数据口径声明和量化归因分解")
        return suggestions
