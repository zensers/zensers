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
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._query_sections: Dict[str, List[str]] = {}
        self._query_locks: Dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    def _normalize_query(self, query: str) -> str:
        normalized = ' '.join(query.split())
        return normalized.lower()

    async def search(self, query: str, section_id: str, search_skill: Any) -> Dict:
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

            result = await search_skill.execute(query=query)
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
