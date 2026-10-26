import re
import json
import logging
from typing import Dict, Any, Optional

from .models import ChapterReviewInput, ChapterReviewOutput, ChapterIssue
from .chapter_writer import DELIMITER_OUTPUT_CONTRACT
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm_ex
from src.core.llm_retry import Budget, LLMBudgetExhausted, ParseOutcome

logger = logging.getLogger(__name__)

# Reviewer fixed-format contract (primary; JSON is the compat fallback) —
# same cross-provider fragility rationale as the chapter writer contract.
_REVIEW_START_MARKER = "<<<CHAPTER_REVIEW>>>"
_REVIEW_END_MARKER = "<<<END_CHAPTER_REVIEW>>>"
_REVIEW_ISSUES_MARKER = "<<<ISSUES>>>"
_REVIEW_FORMAT_REINFORCEMENT = "严格按上述标记格式输出，不要输出任何其他内容。"


class ChapterReviewAgent:

    def __init__(self, prompt_manager: PromptManager = None) -> None:
        self._prompts = prompt_manager

    async def review(self, input_data: ChapterReviewInput) -> ChapterReviewOutput:
        chapter_spec = input_data.chapter_spec

        def build_prompt(variations) -> str:
            from .models import resolve_expected_chars

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
                min_chars=resolve_expected_chars(chapter_spec, input_data.framework_config),
            )
            if variations.strict_json_prefix:
                # Delimiter contract: this builder owns the rung and
                # reinforces the marker format instead of demanding JSON.
                prompt = f"{prompt}\n{_REVIEW_FORMAT_REINFORCEMENT}"
            return prompt

        try:
            outcome = await call_llm_ex(
                build_prompt,
                output_contract=DELIMITER_OUTPUT_CONTRACT,
                expected_output_chars=1500,
                budget=Budget(max_calls=3, max_seconds=240),
                parse=self._parse_with_outcome,
                task_tag=f"reviewer:{chapter_spec.get('section_id', '')}",
            )
        except LLMBudgetExhausted as exhausted:
            logger.warning(
                "ChapterReviewer budget exhausted for %s: %s",
                chapter_spec.get('section_id', ''), exhausted,
            )
            return ChapterReviewOutput(passed=False, score=0.0, parse_failed=True)

        if isinstance(outcome, ChapterReviewOutput):
            return outcome
        return self._parse_output(str(outcome or ""))

    def _parse_with_outcome(self, raw: str) -> ParseOutcome:
        """Engine parse hook: delimiter contract first, then JSON compat;
        anything unparseable is rejected so the failure ladder mutates."""
        delimiter_output = self._parse_review_delimiter(raw)
        if delimiter_output is not None and not delimiter_output.parse_failed:
            return ParseOutcome(True, value=delimiter_output)
        output = self._parse_output(raw)
        if output.parse_failed:
            return ParseOutcome(False, "no_json")
        return ParseOutcome(True, value=output)

    def _parse_review_delimiter(self, raw: str) -> Optional[ChapterReviewOutput]:
        """Parse the reviewer fixed-format contract.

        Returns None when the reply does not use the contract (JSON path
        still gets its turn); returns a parse_failed marker only when the
        markers are present but PASSED/SCORE are missing or garbage.
        """
        text = str(raw or "")
        if _REVIEW_START_MARKER not in text:
            return None
        header = text.split(_REVIEW_ISSUES_MARKER, 1)[0]
        passed_match = re.search(
            r"^\s*PASSED\s*:\s*(true|false)\s*$", header,
            re.MULTILINE | re.IGNORECASE)
        score_match = re.search(
            r"^\s*SCORE\s*:\s*(\d+(?:\.\d+)?)", header, re.MULTILINE | re.IGNORECASE)
        if passed_match is None or score_match is None:
            return ChapterReviewOutput(passed=False, score=0.0, parse_failed=True)
        passed = passed_match.group(1).lower() == "true"
        score = float(score_match.group(1))
        issues: list = []
        issues_text = text.split(_REVIEW_ISSUES_MARKER, 1)[1]
        if _REVIEW_END_MARKER in issues_text:
            issues_text = issues_text.split(_REVIEW_END_MARKER, 1)[0]
        for line in issues_text.splitlines():
            line = line.strip().lstrip("-").strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3 or not parts[0] or not parts[2]:
                continue  # malformed issue line
            issues.append(ChapterIssue(
                category="style",
                severity=parts[0],
                location=parts[1],
                description=parts[2],
                suggestion=parts[3] if len(parts) > 3 else "",
            ))
        return ChapterReviewOutput(passed=passed, score=score, issues=issues)

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

        return ChapterReviewOutput(passed=False, score=0.0, parse_failed=True)
