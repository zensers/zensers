# -*- coding: utf-8 -*-
"""
Content Cleaner
===============

Cleans upstream Agent output to ensure format compliance before
ContentOrchestrator processes it.

Handles:
1. Blacklist title detection (e.g., "章节内容", "Section Content")
2. JSON code block extraction (extract 'content' field from ```json blocks)
3. Internal debug field removal (self_check_*, data_points_used, etc.)
"""

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

TITLE_BLACKLIST = frozenset({
    "章节内容", "Section Content", "内容", "正文",
    "Content", "Section", "章节", "正文内容",
})

_REFUSAL_PATTERNS = [
    re.compile(r'初稿为空.*无法执行精修', re.DOTALL),
    re.compile(r'total_sources:\s*0.*未包含任何实质性', re.DOTALL),
    re.compile(r'禁止从头重写|禁止编造数据', re.DOTALL),
    re.compile(r'补充完整初稿后.*再提交精修', re.DOTALL),
    re.compile(r'draft is empty.*(?:cannot|cannot perform|refuse)', re.DOTALL | re.IGNORECASE),
    re.compile(r'no substantive content.*(?:refine|found)', re.DOTALL | re.IGNORECASE),
]


def clean_section(section_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clean a single section data dict.

    Mutates and returns the same dict.
    """
    title = section_data.get("title", "").strip()
    if title in TITLE_BLACKLIST:
        logger.debug(f"ContentCleaner: blacklisted title '{title}' -> ''")
        section_data["title"] = ""

    content = section_data.get("content", "")
    if content:
        if _is_refusal_content(content):
            logger.info(f"ContentCleaner: refusal/empty-draft content detected for '{title}', clearing section")
            section_data["content"] = ""
            section_data["_refusal"] = True
            return section_data
        cleaned = _extract_json_content(content)
        if cleaned is not content:
            logger.debug("ContentCleaner: extracted content from JSON code block")
            section_data["content"] = cleaned

    return section_data


def _is_refusal_content(content: str) -> bool:
    """Detect if content is a refinement refusal / empty-draft notice.

    When the research agent finds no data and the refinement agent refuses
    to fabricate content, it produces messages like:
    "当前初稿为空，无法执行精修润色。分析研究员提交的初稿内容为空..."
    These should NOT appear in the final report.
    """
    for pattern in _REFUSAL_PATTERNS:
        if pattern.search(content):
            return True
    return False


def _extract_json_content(content: str) -> str:
    """If content is a ```json block with a 'content' field, extract it.

    Otherwise return content unchanged.
    """
    stripped = content.strip()
    if not stripped.startswith("```json"):
        return content

    lines = stripped.split("\n")
    code_end = len(lines)
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip().startswith("```"):
            code_end = i
            break

    json_str = "\n".join(lines[1:code_end])
    try:
        data = json.loads(json_str)
        if isinstance(data, dict) and "content" in data:
            extracted = data["content"]
            if isinstance(extracted, str):
                return extracted
            return json.dumps(extracted, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    return content
