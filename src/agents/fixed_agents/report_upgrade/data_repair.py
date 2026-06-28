import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from src.agents.fixed_agents.report_upgrade.models import (
    DataConflict,
    DataConflictResolution,
    DataGap,
    DataRepairResult,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)

SOURCE_AUTHORITY: Dict[str, int] = {
    "gov.cn": 10,
    "worldbank.org": 9,
    "imf.org": 9,
    "iimedia.cn": 8,
    "iresearch.cn": 8,
    "mckinsey.com": 8,
    "idc.com": 8,
    "gartner.com": 8,
    "statista.com": 7,
    "36kr.com": 4,
    "sohu.com": 3,
}

DESCRIPTION_RULES: List[tuple] = [
    (r"国家统计局|官方统计|政府公告", 10),
    (r"年报|季报|财报|IPO招股书", 8),
    (r"研究报告|白皮书|行业报告", 7),
    (r"新闻报道|媒体报道", 4),
]


class DataRepairAgent:
    def __init__(
        self,
        search_skill,
        web_scraper_skill=None,
        llm_skill=None,
        prompt_manager: PromptManager = None,
    ):
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._prompts = prompt_manager

    async def repair_gap(self, gap: DataGap, topic: str) -> DataRepairResult:
        query = f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}"
        search_result = await self._search.execute(query=query, max_results=10)
        if not search_result.get("success"):
            return DataRepairResult(gap=gap, found=False)

        results = search_result.get("results", [])
        scraped_texts = []
        for item in results[:3]:
            url = item.get("href", "")
            if not url:
                continue
            scrape_result = await self._scraper.execute(
                url=url, action="extract_markdown", max_chars=3000,
            )
            if scrape_result.get("success") and scrape_result.get("text"):
                scraped_texts.append(
                    f"[{scrape_result.get('title', '')}]({url}):\n{scrape_result['text']}"
                )

        if not scraped_texts:
            return DataRepairResult(gap=gap, found=False)

        search_results_text = "\n\n".join(scraped_texts)
        prompt = self._prompts.get(
            "data_extraction",
            metric=gap.metric,
            context=gap.context,
            topic=topic,
            search_results=search_results_text,
        )
        llm_result = await call_llm(prompt=prompt, max_tokens=2048)
        if not llm_result.get("success"):
            return DataRepairResult(gap=gap, found=False)

        return self._parse_extraction(llm_result["content"], gap)

    async def repair_batch(
        self, gaps: List[DataGap], topic: str,
    ) -> List[DataRepairResult]:
        sem = asyncio.Semaphore(5)

        async def _repair(gap: DataGap) -> DataRepairResult:
            async with sem:
                return await self.repair_gap(gap, topic)

        tasks = [_repair(g) for g in gaps]
        return await asyncio.gather(*tasks)

    def _parse_extraction(self, raw: str, gap: DataGap) -> DataRepairResult:
        try:
            json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("found"):
                    return DataRepairResult(
                        gap=gap,
                        found=True,
                        value=data.get("value"),
                        unit=data.get("unit"),
                        source=data.get("source"),
                        source_title=data.get("source_title"),
                        confidence=float(data.get("confidence") or 0.0),
                    )
            return DataRepairResult(gap=gap, found=False)
        except (json.JSONDecodeError, ValueError, TypeError):
            return DataRepairResult(gap=gap, found=False)


class ConflictResolver:
    def __init__(
        self,
        llm_skill=None,
        search_skill=None,
        web_scraper_skill=None,
        prompt_manager: PromptManager = None,
    ):
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._prompts = prompt_manager

    async def resolve(
        self, conflict: DataConflict, topic: str,
    ) -> DataConflictResolution:
        scored = []
        for entry in conflict.entries:
            score = self._score_entry(entry)
            scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_entry = scored[0]
        if best_score >= 6:
            chapters_to_update = [
                e.get("chapter_id", "")
                for e in conflict.entries
                if e.get("value") != best_entry.get("value")
            ]
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=best_entry.get("value", ""),
                canonical_unit=best_entry.get("unit", ""),
                canonical_source=best_entry.get("source", ""),
                reason=f"Source authority score {best_score}",
                chapters_to_update=chapters_to_update,
            )

        return await self._resolve_by_search(conflict, topic)

    def _score_entry(self, entry: Dict) -> int:
        source = entry.get("source", "")
        description = entry.get("description", "")
        score = 0
        for domain, authority in SOURCE_AUTHORITY.items():
            if domain in source:
                score = max(score, authority)
        for pattern, bonus in DESCRIPTION_RULES:
            if re.search(pattern, description):
                score = max(score, bonus)
        return score

    async def _resolve_by_search(
        self, conflict: DataConflict, topic: str,
    ) -> DataConflictResolution:
        if self._search is None:
            first = conflict.entries[0] if conflict.entries else {}
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=first.get("value", ""),
                canonical_unit=first.get("unit", ""),
                canonical_source=first.get("source", ""),
                reason="No search skill available, using first entry",
                chapters_to_update=[e.get("chapter_id", "") for e in conflict.entries[1:]],
            )

        query = f"{conflict.metric} {topic}"
        search_result = await self._search.execute(query=query, max_results=5)
        search_texts = []
        if search_result.get("success"):
            for item in search_result.get("results", [])[:3]:
                url = item.get("href", "")
                if not url:
                    continue
                if self._scraper is None:
                    search_texts.append(
                        f"- {item.get('title', '')}: {item.get('body', '')}"
                    )
                    continue
                scrape_result = await self._scraper.execute(
                    url=url, action="extract_markdown", max_chars=3000,
                )
                if scrape_result.get("success") and scrape_result.get("text"):
                    search_texts.append(
                        f"[{scrape_result.get('title', '')}]({url}):\n{scrape_result['text']}"
                    )

        conflict_entries_text = json.dumps(conflict.entries, ensure_ascii=False)
        search_results_text = "\n\n".join(search_texts) if search_texts else "无搜索结果"
        prompt = self._prompts.get(
            "conflict_resolution",
            metric=conflict.metric,
            conflict_entries=conflict_entries_text,
            search_results=search_results_text,
        )
        llm_result = await call_llm(prompt=prompt, max_tokens=2048)
        if not llm_result.get("success"):
            first = conflict.entries[0] if conflict.entries else {}
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=first.get("value", ""),
                canonical_unit=first.get("unit", ""),
                canonical_source=first.get("source", ""),
                reason="LLM failed, using first entry",
                chapters_to_update=[e.get("chapter_id", "") for e in conflict.entries[1:]],
            )

        try:
            json_match = re.search(r'\{[^{}]*\}', llm_result["content"], re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return DataConflictResolution(
                    conflict=conflict,
                    canonical_value=data.get("canonical_value", ""),
                    canonical_unit=data.get("canonical_unit", ""),
                    canonical_source=data.get("canonical_source", ""),
                    reason=data.get("reason", ""),
                    chapters_to_update=[e.get("chapter_id", "") for e in conflict.entries],
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            first = conflict.entries[0] if conflict.entries else {}
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=first.get("value", ""),
                canonical_unit=first.get("unit", ""),
                canonical_source=first.get("source", ""),
                reason="JSON parse failed, using first entry",
                chapters_to_update=[e.get("chapter_id", "") for e in conflict.entries[1:]],
            )
