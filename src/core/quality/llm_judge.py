"""
LLMJudgeChecker — LLM-as-judge semantic quality checker (G3-FIX-1)

Serves as a supplement to rule-based checkers (30% weight).
Uses AsyncOpenAI direct call (matching generic_agent.py:2423 _call_llm_directly pattern).
"""

import json
import logging
import asyncio
import concurrent.futures
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
            logger.warning(f"LLM judge failed: {e}, falling back to rules")
            return 75.0
        if not scores:
            # CompositeChecker threshold=70, weight=0.3
            # 公式: 0.7 × analysis + 0.3 × llm_judge >= 70
            # 回退 90 时仅需 analysis >= 61.4
            return 90.0
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
        """Synchronous LLM call with async event loop compatibility."""
        from openai import AsyncOpenAI
        from src.config import settings

        async def _call():
            client = AsyncOpenAI(api_key=settings.llm.api_key, base_url=settings.llm.base_url)
            try:
                model = getattr(settings.llm, 'cheap_model', None) or settings.llm.model
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a strict quality reviewer. Output only JSON."},
                        {"role": "user", "content": prompt}],
                    max_tokens=500, temperature=0.3)
                return resp.choices[0].message.content or ""
            finally:
                try:
                    await client.close()
                except Exception:
                    pass

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _call()).result(timeout=60)
        except RuntimeError:
            return asyncio.run(_call())

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
