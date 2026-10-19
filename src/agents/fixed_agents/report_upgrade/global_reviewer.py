import re
import json
import logging
import os
from typing import Dict, Any, List

from .models import (
    ReviewInput, ReviewOutput, ReviewIssue, FixSuggestion, ChapterWriteOutput,
)
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


def _review_max_tokens() -> int:
    """Review JSON competes with reasoning tokens for the same budget.

    Reasoning-first models (MIMO 2.5/2.6) consume reasoning_content tokens
    from max_tokens before emitting the answer, so an 8192 cap truncates
    the global review JSON mid-string and triggers unnecessary repair
    rounds.
    """
    try:
        value = int(os.environ.get("ZENSERS_REVIEW_MAX_TOKENS", "16384"))
    except (TypeError, ValueError):
        return 16384
    return max(8192, min(32768, value))


class GlobalReviewAgent:

    def __init__(self, prompt_manager: PromptManager = None) -> None:
        self._prompts = prompt_manager

    async def review(self, input_data: ReviewInput) -> ReviewOutput:
        prompt = self._prompts.get(
            "global_review",
            framework_name=input_data.framework_config.get('name', '通用研究报告'),
            report_summary=input_data.report_summary,
            conflicts_summary=input_data.conflicts_summary,
        )

        result = await call_llm(prompt=prompt, max_tokens=_review_max_tokens(), temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Global review LLM call failed: {result}")

        return self._parse_output(result["content"])

    async def verify_issues(self, issues: List[ReviewIssue],
                            chapters: List[ChapterWriteOutput]) -> List[ReviewIssue]:
        if not issues:
            return []

        all_contexts = []
        for issue in issues:
            relevant_content = self._extract_relevant_chapters(issue, chapters)
            all_contexts.append(
                f"问题：{issue.description}\n位置：{issue.location}\n相关原文：\n{relevant_content[:2000]}"
            )

        issues_context = chr(10).join(
            f"### 问题{i+1}{chr(10)}{ctx}" for i, ctx in enumerate(all_contexts)
        )
        prompt = self._prompts.get("global_verify_issues", issues_context=issues_context)

        result = await call_llm(prompt=prompt, max_tokens=_review_max_tokens(), temperature=0.3)
        if not result.get("success"):
            return issues

        try:
            json_match = re.search(r'\[.*\]', result["content"], re.DOTALL)
            if json_match:
                parsed_list = json.loads(json_match.group())
                verified = []
                for i, parsed in enumerate(parsed_list):
                    if i >= len(issues):
                        break
                    if parsed.get("confirmed"):
                        verified.append(ReviewIssue(
                            dimension=issues[i].dimension,
                            severity=issues[i].severity,
                            description=parsed.get("refined_description", issues[i].description),
                            location=issues[i].location,
                            evidence=parsed.get("refined_evidence", issues[i].evidence),
                        ))
                return verified
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return issues

    @staticmethod
    def _extract_relevant_chapters(issue: ReviewIssue,
                                   chapters: List[ChapterWriteOutput]) -> str:
        raw_location = issue.location
        if isinstance(raw_location, (list, tuple, set)):
            location_ids = [str(loc).strip() for loc in raw_location if str(loc).strip()]
        else:
            location_ids = [loc.strip() for loc in str(raw_location or "").split(",") if loc.strip()]
        parts = []
        for ch in chapters:
            if ch.chapter_id in location_ids:
                parts.append(f"### {ch.title}（{ch.chapter_id}）\n{ch.content[:3000]}")
        return "\n\n".join(parts) if parts else "未找到相关章节"

    def _parse_output(self, raw: str) -> ReviewOutput:
        try:
            json_str = None
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                logger.warning(f"GlobalReviewAgent: no ```json``` block found, trying raw JSON. Raw len={len(raw)}")
                brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if brace_match:
                    json_str = brace_match.group(0)
            if json_str:
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON content found")
            issues = [
                ReviewIssue(
                    dimension=iss.get("dimension", ""),
                    severity=iss.get("severity", "MEDIUM"),
                    description=iss.get("description", ""),
                    location=iss.get("location", ""),
                    evidence=iss.get("evidence", ""),
                )
                for iss in data.get("issues", [])
            ]
            fix_suggestions = [
                FixSuggestion(
                    target_chapter=fix.get("target_chapter", ""),
                    issue_id=fix.get("issue_id", ""),
                    fix_type=fix.get("fix_type", "rewrite"),
                    fix_instruction=fix.get("fix_instruction", ""),
                    priority=fix.get("priority", "MEDIUM"),
                )
                for fix in data.get("fix_suggestions", [])
            ]
            return ReviewOutput(
                overall_score=float(data.get("overall_score") or 100.0),
                dimension_scores=data.get("dimension_scores", {}),
                issues=issues,
                fix_suggestions=fix_suggestions,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse global review output: {e}")

        return ReviewOutput(overall_score=0.0)


def serialize_report_for_review(chapters: List[ChapterWriteOutput],
                                data_registry) -> str:
    sections_summary = []
    for i, ch in enumerate(chapters):
        content = ch.content or ""
        content_head = content[:400]
        content_tail = content[-400:] if len(content) > 800 else content[400:]
        data_summary = [f"  {dp.metric}: {dp.value} {dp.unit}" for dp in ch.data_points_used]
        sections_summary.append(
            f"### 第{i+1}章：{ch.title}\n"
            f"核心结论：{'; '.join(str(c) for c in ch.key_conclusions)}\n"
            f"正文前段：{content_head}\n"
            f"正文后段：{content_tail}\n"
            f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
        )
    return "\n\n".join(sections_summary)
