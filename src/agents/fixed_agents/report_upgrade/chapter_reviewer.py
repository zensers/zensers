import re
import json
import logging
from typing import Dict, Any

from .models import ChapterReviewInput, ChapterReviewOutput, ChapterIssue
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


class ChapterReviewAgent:

    def __init__(self, llm_skill=None, prompt_manager: PromptManager = None) -> None:
        self._prompts = prompt_manager

    async def review(self, input_data: ChapterReviewInput) -> ChapterReviewOutput:
        chapter_spec = input_data.chapter_spec
        prompt = self._prompts.get(
            "chapter_review",
            topic=input_data.topic,
            section_name=chapter_spec.get('section_name', ''),
            section_role=str(chapter_spec.get('section_role', '')),
            preceding_summary=input_data.preceding_summary,
            used_metrics_summary=input_data.used_metrics_summary,
            chapter_content=input_data.chapter_content,
            writer_self_check_issues=(
                chr(10).join(f'- {issue}' for issue in input_data.writer_self_check_issues)
                if input_data.writer_self_check_issues else '无'
            ),
            chapter_data=json.dumps(input_data.chapter_data, ensure_ascii=False, indent=2)
                         if input_data.chapter_data else '无可用数据',
        )

        result = await call_llm(prompt=prompt, max_tokens=8192, temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Chapter review LLM call failed: {result}")

        return self._parse_output(result["content"])

    def _parse_output(self, raw: str) -> ChapterReviewOutput:
        try:
            json_str = None
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                logger.warning(f"ChapterReviewAgent: no ```json``` block found, trying raw JSON. Raw len={len(raw)}")
                brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if brace_match:
                    json_str = brace_match.group(0)
            if json_str:
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON content found")
            issues = [
                ChapterIssue(
                    category=iss.get("category", "style"),
                    severity=iss.get("severity", "MEDIUM"),
                    location=iss.get("location", ""),
                    description=iss.get("description", ""),
                    suggestion=iss.get("suggestion", ""),
                )
                for iss in data.get("issues", [])
            ]
            return ChapterReviewOutput(
                passed=data.get("passed", True),
                score=float(data.get("score") or 100.0),
                issues=issues,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse review output: {e}")

        return ChapterReviewOutput(passed=False, score=0.0)
