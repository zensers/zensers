# -*- coding: utf-8 -*-
"""
Search Query Deduplicator - per-query lock based deduplication with cache.

Prevents redundant search queries across agents, ensuring each unique query
is executed only once. Results are shared via deep copy to avoid cross-agent
state mutation.
"""

import asyncio
import copy
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class SearchQueryDeduplicator:
    def __init__(self, gateway: Any = None):
        self._cache: Dict[str, Dict] = {}
        self._query_sections: Dict[str, List[str]] = {}
        self._query_locks: Dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()
        self.gateway = gateway

    def _normalize_query(self, query: str) -> str:
        normalized = ' '.join(query.split())
        return normalized.lower()

    async def search(
        self,
        query: str,
        section_id: str,
        search_skill: Any = None,
        *,
        scope: str = "execution_engine",
    ) -> Dict:
        normalized = self._normalize_query(query)

        async with self._meta_lock:
            if normalized not in self._query_locks:
                self._query_locks[normalized] = asyncio.Lock()
            query_lock = self._query_locks[normalized]

        async with query_lock:
            if normalized in self._cache:
                self._query_sections[normalized].append(section_id)
                logger.info(f"SearchQueryDeduplicator: cache hit for '{query}' (section {section_id})")
                return copy.deepcopy(self._cache[normalized])

            if self.gateway is not None:
                from src.core.search.gateway import SearchRequest

                response = await self.gateway.search(
                    SearchRequest(query=query),
                    scope=scope,
                )
                result = {
                    "success": response.success,
                    "results": [
                        {
                            "title": item.title,
                            "url": item.url,
                            "href": item.url,
                            "snippet": item.snippet,
                            "body": item.snippet,
                            "source": item.source,
                            "published_at": item.published_at,
                            "quality_score": item.quality_score,
                            "evidence_id": item.evidence_id,
                            "provenance_id": item.provenance_id,
                            "evidence_excerpt": item.excerpt,
                            "locator": item.locator,
                            "task_id": item.task_id,
                            "request_id": item.request_id,
                            "retrieved_at": item.retrieved_at,
                        }
                        for item in response.results
                    ],
                    "provider": response.provider,
                    "error_class": response.error_class,
                    "message": response.message,
                    "stop_reason": response.stop_reason,
                    "cache_hit": response.cache_hit,
                }
            elif search_skill is not None:
                # Compatibility path for tests and callers not yet migrated.
                result = await search_skill.execute(query=query)
            else:
                raise ValueError("SearchQueryDeduplicator requires a gateway")
            self._cache[normalized] = result
            self._query_sections[normalized] = [section_id]
            logger.info(f"SearchQueryDeduplicator: executed search for '{query}' (section {section_id})")
            return copy.deepcopy(result)

    def get_shared_queries(self) -> Dict[str, List[str]]:
        return {q: ss for q, ss in self._query_sections.items() if len(ss) > 1}

    def clear(self):
        self._cache.clear()
        self._query_sections.clear()
        self._query_locks.clear()
