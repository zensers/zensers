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
        search_skill=None,
        web_scraper_skill=None,
        prompt_manager: PromptManager = None,
        search_gateway=None,
        scrape_timeout: float = 45.0,
        llm_timeout: float = 180.0,
    ):
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._prompts = prompt_manager
        self._gateway = search_gateway
        self._scrape_timeout = max(1.0, float(scrape_timeout))
        self._llm_timeout = max(1.0, float(llm_timeout))

    async def repair_gap(self, gap: DataGap, topic: str) -> DataRepairResult:
        query = f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}"
        if self._gateway is not None:
            from src.core.search import SearchRequest

            response = await self._gateway.search(
                SearchRequest(query=query, objective="report_repair"),
                scope="report_repair",
            )
            search_result = {
                "success": response.success,
                "results": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "source": item.source,
                        "evidence_id": item.evidence_id,
                        "provenance_id": item.provenance_id,
                        "evidence_excerpt": item.excerpt or item.snippet,
                        "locator": item.locator,
                        "task_id": item.task_id,
                        "request_id": item.request_id,
                        "retrieved_at": item.retrieved_at,
                    }
                    for item in response.results
                ],
            }
        elif self._search is not None:
            search_result = await self._search.execute(query=query, max_results=10)
        else:
            return DataRepairResult(gap=gap, found=False)
        if not search_result.get("success"):
            return DataRepairResult(gap=gap, found=False)

        results = search_result.get("results", [])
        scraped_texts = []
        evidence_candidates = []
        for item in results[:3]:
            url = item.get("url", "") or item.get("href", "")
            if not url:
                continue
            try:
                scrape_result = await self._scraper.execute(
                    url=url, action="extract_markdown", max_chars=3000
                )
            except Exception as scrape_error:
                logger.warning("Evidence scrape failed: %s", scrape_error)
                continue
            if scrape_result.get("success") and scrape_result.get("text"):
                excerpt = str(
                    item.get("evidence_excerpt")
                    or scrape_result.get("text")
                    or item.get("snippet", "")
                ).strip()
                evidence_candidates.append({
                    "title": str(item.get("title", "") or scrape_result.get("title", "")).strip(),
                    "url": str(url).strip(),
                    "evidence_id": str(item.get("evidence_id", "") or "").strip(),
                    "provenance_id": str(item.get("provenance_id", "") or "").strip(),
                    "evidence_excerpt": excerpt,
                    "locator": str(item.get("locator", "") or "").strip(),
                    "task_id": str(item.get("task_id", "") or "").strip(),
                    "request_id": str(item.get("request_id", "") or "").strip(),
                    "retrieved_at": item.get("retrieved_at"),
                })
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
        try:
            llm_result = await call_llm(prompt=prompt, max_tokens=2048)
        except Exception as llm_error:
            logger.warning("Data extraction LLM failed: %s", llm_error)
            return DataRepairResult(gap=gap, found=False)
        if not llm_result.get("success"):
            return DataRepairResult(gap=gap, found=False)

        return self._parse_extraction(
            llm_result["content"], gap, evidence_candidates=evidence_candidates
        )

    async def repair_batch(
        self, gaps: List[DataGap], topic: str,
    ) -> List[DataRepairResult]:
        sem = asyncio.Semaphore(5)

        async def _repair(gap: DataGap) -> DataRepairResult:
            async with sem:
                return await self.repair_gap(gap, topic)

        tasks = [_repair(g) for g in gaps]
        return await asyncio.gather(*tasks)

    def _parse_extraction(
        self,
        raw: str,
        gap: DataGap,
        evidence_candidates: Optional[List[Dict]] = None,
    ) -> DataRepairResult:
        try:
            json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("found"):
                    candidates = evidence_candidates or []
                    source_title = str(data.get("source_title") or "").strip()
                    source_url = str(data.get("source_url") or "").strip()
                    matched = [
                        candidate for candidate in candidates
                        if (source_url and candidate.get("url") == source_url)
                        or (source_title and candidate.get("title") == source_title)
                    ]
                    if source_url and len(matched) != 1:
                        return DataRepairResult(gap=gap, found=False)
                    selected = matched[0] if len(matched) == 1 else (
                        candidates[0] if len(candidates) == 1 else {}
                    )
                    if not selected or not (
                        selected.get("url")
                        or selected.get("evidence_id")
                        or selected.get("provenance_id")
                    ):
                        return DataRepairResult(gap=gap, found=False)
                    return DataRepairResult(
                        gap=gap,
                        found=True,
                        value=data.get("value"),
                        unit=data.get("unit"),
                        source=data.get("source"),
                        source_title=source_title or data.get("source_title"),
                        confidence=float(data.get("confidence") or 0.0),
                        source_url=source_url or str(selected.get("url", "")),
                        evidence_id=str(selected.get("evidence_id", "")),
                        provenance_id=str(selected.get("provenance_id", "")),
                        evidence_excerpt=str(selected.get("evidence_excerpt", "")),
                        locator=str(selected.get("locator", "")),
                        task_id=str(selected.get("task_id", "")),
                        request_id=str(selected.get("request_id", "")),
                        retrieved_at=selected.get("retrieved_at"),
                        geographic_scope=str(data.get("geographic_scope") or "").strip(),
                        period=str(data.get("period") or "").strip(),
                        population=str(data.get("population") or "").strip(),
                        epistemic_level=str(data.get("epistemic_level") or "").strip(),
                    )
            return DataRepairResult(gap=gap, found=False)
        except (json.JSONDecodeError, ValueError, TypeError):
            return DataRepairResult(gap=gap, found=False)


class ConflictResolver:
    def __init__(
        self,
        search_skill=None,
        web_scraper_skill=None,
        prompt_manager: PromptManager = None,
        search_gateway=None,
        scrape_timeout: float = 45.0,
        llm_timeout: float = 180.0,
    ):
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._prompts = prompt_manager
        self._gateway = search_gateway
        self._scrape_timeout = max(1.0, float(scrape_timeout))
        self._llm_timeout = max(1.0, float(llm_timeout))

    async def resolve(
        self, conflict: DataConflict, topic: str,
    ) -> DataConflictResolution:
        caliber_notes = self._detect_caliber_differences(conflict)

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
            reason = f"Source authority score {best_score}"
            if caliber_notes:
                reason += f"; {caliber_notes}"
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=best_entry.get("value", ""),
                canonical_unit=best_entry.get("unit", ""),
                canonical_source=best_entry.get("source", ""),
                reason=reason,
                chapters_to_update=chapters_to_update,
            )

        resolution = await self._resolve_by_search(conflict, topic)
        if caliber_notes:
            resolution.reason += f"; {caliber_notes}"
        return resolution

    def _detect_caliber_differences(self, conflict: DataConflict) -> str:
        caliber_keywords = ["调整", "调整后", "剔除", "扣非", "经调整", "非经常性", "一次性"]
        caliber_entries = []
        for entry in conflict.entries:
            source = entry.get("source", "")
            description = entry.get("description", "")
            for kw in caliber_keywords:
                if kw in source or kw in description:
                    caliber_entries.append(
                        f"{entry.get('value', '')}{entry.get('unit', '')}({kw}口径: {source})"
                    )
                    break
        if not caliber_entries:
            return ""
        return f"口径差异: {'; '.join(caliber_entries)}"

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
        if self._gateway is not None:
            from src.core.search import SearchRequest

            response = await self._gateway.search(
                SearchRequest(query=query, objective="conflict_resolution"),
                scope="conflict_resolver",
            )
            search_result = {
                "success": response.success,
                "results": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "source": item.source,
                    }
                    for item in response.results
                ],
            }
        elif self._search is not None:
            search_result = await self._search.execute(query=query, max_results=5)
        else:
            search_result = {"success": False, "results": []}
        search_texts = []
        if search_result.get("success"):
            for item in search_result.get("results", [])[:3]:
                url = item.get("url", "") or item.get("href", "")
                if not url:
                    continue
                if self._scraper is None:
                    search_texts.append(
                        f"- {item.get('title', '')}: {item.get('body', '')}"
                    )
                    continue
                try:
                    scrape_result = await self._scraper.execute(
                        url=url, action="extract_markdown", max_chars=3000
                    )
                except Exception as scrape_error:
                    logger.warning("Conflict evidence scrape failed: %s", scrape_error)
                    continue
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
        try:
            llm_result = await call_llm(prompt=prompt, max_tokens=2048)
        except Exception as llm_error:
            logger.warning("Conflict resolution LLM failed: %s", llm_error)
            llm_result = {"success": False, "error": str(llm_error)}
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
