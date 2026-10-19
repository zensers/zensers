from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.adjustment.extraction_types import ExtractionResult
from src.core.adjustment.ppt_requirement_extractor import PptRequirement


@dataclass
class DataGap:
    topic: str
    priority: str
    search_queries: List[str]
    search_results: List[Any] = field(default_factory=list)
    filled: bool = False


class PptDataSupplementer:
    async def supplement_async(self, gaps: List[DataGap], gateway=None) -> List[DataGap]:
        """Fill gaps through the task SearchGateway.

        The synchronous ``supplement`` method remains as a compatibility
        shim for legacy tests/callers and must not be used by production
        Gateway paths.
        """
        if gateway is None:
            return gaps
        from src.core.search import SearchRequest

        for gap in gaps:
            if gap.filled or not gap.search_queries:
                continue
            response = await gateway.search(
                SearchRequest(
                    query=gap.search_queries[0],
                    objective="ppt_supplement",
                ),
                scope="ppt_supplement",
            )
            if response.success and response.results:
                gap.search_results = [
                    {
                        "title": item.title,
                        "snippet": item.snippet,
                        "url": item.url,
                        "source": item.source,
                        "published_at": item.published_at,
                        "quality_score": item.quality_score,
                    }
                    for item in response.results
                ]
                gap.filled = True
        return gaps

    def analyze_gaps(self, extraction: ExtractionResult,
                     requirement: PptRequirement) -> List[DataGap]:
        covered = set(extraction.key_topics)
        gaps: List[DataGap] = []
        for focus_area in requirement.focus:
            if focus_area not in covered:
                gaps.append(DataGap(
                    topic=focus_area,
                    priority="critical",
                    search_queries=[f"{focus_area} {requirement.topic}"],
                ))
        return gaps

    def supplement(self, gaps: List[DataGap],
                   search_skill=None) -> List[DataGap]:
        for gap in gaps:
            if gap.filled:
                continue
            if search_skill:
                results = search_skill.execute(query=gap.search_queries[0], max_results=5)
                if results and results.get("success"):
                    data = results.get("data", {})
                    search_results = data.get("results", [])
                    if search_results:
                        gap.search_results = search_results
                        gap.filled = True
        return gaps
