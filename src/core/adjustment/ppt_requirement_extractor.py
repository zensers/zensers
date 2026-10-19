from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.core.adjustment.extraction_types import ExtractionResult


@dataclass
class PptRequirement:
    topic: str
    audience: str = "business_professional"
    focus: List[str] = field(default_factory=list)
    page_count: Optional[int] = None
    style: str = "professional"
    confirmed: bool = False


class PptRequirementExtractor:
    def extract(self, extraction: ExtractionResult,
                user_description: str = "") -> PptRequirement:
        if user_description:
            return self._from_description(extraction, user_description)
        return self._from_data(extraction)

    def _from_data(self, extraction: ExtractionResult) -> PptRequirement:
        topic = extraction.title
        if not topic:
            topic = extraction.key_topics[0] if extraction.key_topics else "未命名主题"

        focus = extraction.key_topics[:5]
        page_count = max(3, len(extraction.sections) * 2)

        return PptRequirement(
            topic=topic,
            focus=focus,
            page_count=page_count,
        )

    def _from_description(self, extraction: ExtractionResult,
                          desc: str) -> PptRequirement:
        topic = self._extract_topic_from_text(desc)
        if not topic:
            topic = extraction.title or (extraction.key_topics[0] if extraction.key_topics else "未命名主题")

        focus = extraction.key_topics[:5]
        page_count = max(3, len(extraction.sections) * 2)

        return PptRequirement(
            topic=topic,
            focus=focus,
            page_count=page_count,
        )

    def _extract_topic_from_text(self, text: str) -> str:
        patterns = [
            r"关于(.+?)(?:的|之)PPT",
            r"关于(.+?)(?:的|之)汇报",
            r"关于(.+?)(?:的|之)报告",
            r"(.+?)PPT",
            r"(.+?)汇报",
            r"(.+?)报告",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()
        return ""
