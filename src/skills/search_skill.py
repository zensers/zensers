"""
MultiSearchSkill - Search Engine Integration Skill (v5.0 Simplified)

精简至 5 个有效引擎：
- baidu: baidu-serp-api（结构化 API，无需 HTML 解析）
- duckduckgo: DDGS 库（稳定可靠）
- google / google_hk: web_fetch + Scrapling adaptive（保留英文搜索）
- bing_cn / bing_intl: web_fetch（备选）
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from src.skills.base import Skill, SkillConfig
from src.core.search_quality_filter import SearchQualityFilter

logger = logging.getLogger(__name__)


SEARCH_ENGINES = {
    "baidu": {
        "name": "Baidu",
        "region": "cn",
        "priority": 1,
        "use_api": True,
    },
    "bing_cn": {
        "name": "Bing China",
        "url": "https://cn.bing.com/search?q={keyword}&ensearch=0",
        "region": "cn",
        "priority": 2,
        "selectors": {
            "container": ".b_algo",
            "title": "h2 a",
            "link": "h2 a",
            "snippet": ".b_caption p, p",
        }
    },
    "bing_intl": {
        "name": "Bing International",
        "url": "https://cn.bing.com/search?q={keyword}&ensearch=1",
        "region": "global",
        "priority": 3,
        "selectors": {
            "container": ".b_algo",
            "title": "h2 a",
            "link": "h2 a",
            "snippet": ".b_caption p, p",
        }
    },
    "google": {
        "name": "Google",
        "url": "https://www.google.com/search?q={keyword}",
        "pagination": {"param": "start", "start": 0, "step": 10},
        "region": "global",
        "priority": 10,
        "selectors": {
            "container": ".g, .tF2Cxc, .rc",
            "title": "h3",
            "link": "a[href^='http']",
            "snippet": ".VwiC3b, .s3v9rd, .s, .st",
        }
    },
    "google_hk": {
        "name": "Google Hong Kong",
        "url": "https://www.google.com.hk/search?q={keyword}",
        "pagination": {"param": "start", "start": 0, "step": 10},
        "region": "global",
        "priority": 11,
        "selectors": {
            "container": ".g, .tF2Cxc, .rc",
            "title": "h3",
            "link": "a[href^='http']",
            "snippet": ".VwiC3b, .s3v9rd, .s, .st",
        }
    },
}

DDGS_AVAILABLE = False
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        pass


class MultiSearchSkill(Skill):

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        self.quality_filter = SearchQualityFilter(min_quality_score=40.0)
        self.timeout = 30

    @property
    def name(self) -> str:
        return "search_skill"

    @property
    def description(self) -> str:
        return (
            "Search the web for information, data, or research. "
            "Supports Baidu (API), Google, Bing, DuckDuckGo. "
            "No API Key required."
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "").strip()
        engines = kwargs.get("engines")
        max_results = min(kwargs.get("max_results", 10), 200)
        region = kwargs.get("region", "cn")
        use_ddgs = kwargs.get("use_ddgs", True)
        enable_quality_filter = kwargs.get("enable_quality_filter", True)
        min_quality_score = kwargs.get("min_quality_score", 40.0)
        context = kwargs.get("context")
        time_range = kwargs.get("time_range")

        if not query:
            return self._failure("query cannot be empty")

        if min_quality_score != 40.0:
            self.quality_filter.min_quality_score = min_quality_score

        all_results = []
        engines_used = []

        # 1. DDGS (most reliable)
        if use_ddgs and DDGS_AVAILABLE:
            try:
                ddgs_results = await self._search_with_ddgs(query, max_results, time_range=time_range)
                if ddgs_results:
                    all_results.extend(ddgs_results)
                    engines_used.append("duckduckgo")
                    logger.info(f"DDGS: {len(ddgs_results)} results")
            except Exception as e:
                logger.warning(f"DDGS failed: {e}")

        # 2. Baidu API (for CN queries)
        is_cn = region and region.lower().startswith(("cn", "zh"))
        if len(all_results) < max_results and is_cn:
            try:
                baidu_results = await self._search_with_baidu_api(query, max_results)
                if baidu_results:
                    all_results.extend(baidu_results)
                    engines_used.append("baidu")
                    logger.info(f"Baidu API: {len(baidu_results)} results")
            except Exception as e:
                logger.warning(f"Baidu API failed: {e}")

        # 3. Web fetch engines (Google, Bing) as supplement
        if len(all_results) < max_results:
            if engines:
                engines_to_use = [e for e in engines if e in SEARCH_ENGINES and e != "baidu"]
            else:
                engines_to_use = self._select_engines(region)

            for engine_id in engines_to_use[:2]:
                if len(all_results) >= max_results:
                    break
                try:
                    results = await self._search_with_web_fetch(engine_id, query, max_results - len(all_results))
                    if results:
                        all_results.extend(results)
                        if engine_id not in engines_used:
                            engines_used.append(engine_id)
                except Exception as e:
                    logger.warning(f"Engine {engine_id} failed: {e}")

        # Deduplicate
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("href", "") or r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        raw_results = unique_results

        if not raw_results:
            return self._failure("All search engines unavailable", "Search failed")

        # Quality filtering
        if enable_quality_filter and raw_results:
            filtered_results, quality_scores = self.quality_filter.filter_results(raw_results, query, context)

            if len(filtered_results) < min(3, max_results):
                scored_raw = []
                for r in raw_results:
                    score = self.quality_filter._calculate_quality_score(r, query, context)
                    if not score.is_filtered:
                        r_with_score = r.copy()
                        r_with_score["quality_score"] = score.overall_score
                        scored_raw.append(r_with_score)
                scored_raw.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
                filtered_results = scored_raw[:max_results] if scored_raw else raw_results[:max_results]

            filtered_results = filtered_results[:max_results]
            tier_counts = {}
            for score in quality_scores:
                tier = score.credibility.value
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

            logger.info(f"Quality: {len(raw_results)} -> {len(filtered_results)} results")

            return self._success({
                "results": filtered_results,
                "query": query,
                "total": len(filtered_results),
                "raw_total": len(raw_results),
                "engines_used": engines_used,
                "quality_stats": {
                    "filtered_count": len(raw_results) - len(filtered_results),
                    "tier_distribution": tier_counts,
                },
            }, f"Search completed using {len(engines_used)} engines, kept {len(filtered_results)}/{len(raw_results)} results")

        return self._success({
            "results": raw_results[:max_results],
            "query": query,
            "total": len(raw_results[:max_results]),
            "engines_used": engines_used,
        }, f"Search completed, found {len(raw_results)} results")

    def _select_engines(self, region: str) -> List[str]:
        is_cn = region and region.lower().startswith(("cn", "zh"))
        engines = []
        for eng_id, eng_config in SEARCH_ENGINES.items():
            if eng_id == "baidu":
                continue  # baidu is handled separately via API
            if is_cn and eng_config["region"] == "cn":
                engines.append((eng_id, eng_config["priority"]))
            elif not is_cn and eng_config["region"] in ("global", "cn"):
                engines.append((eng_id, eng_config["priority"]))
        engines.sort(key=lambda x: x[1])
        return [eng[0] for eng in engines]

    async def _search_with_ddgs(self, query: str, max_results: int, time_range: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS
            IS_NEW = True
        except ImportError:
            from duckduckgo_search import DDGS
            IS_NEW = False

        def sync_search():
            with DDGS(timeout=self.timeout) as ddgs:
                kwargs = {"max_results": max_results}
                if time_range:
                    kwargs["timelimit"] = time_range
                if IS_NEW:
                    return list(ddgs.text(query=query, **kwargs))
                else:
                    return list(ddgs.text(keywords=query, **kwargs))

        raw_results = await asyncio.to_thread(sync_search)
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "href": r.get("href", ""),
                "body": r.get("body", ""),
            })
        return results

    async def _search_with_baidu_api(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search Baidu via baidu-serp-api (structured data, no HTML parsing)."""
        from baidu_serp_api import BaiduPc
        searcher = BaiduPc()
        raw = searcher.search(query, pn=1)
        items = raw.get("data", {}).get("results", [])
        results = []
        for item in items[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("description", ""),
            })
        return results

    async def _search_with_web_fetch(self, engine_id: str, query: str, max_results: int) -> List[Dict[str, Any]]:
        engine = SEARCH_ENGINES.get(engine_id)
        if not engine or "url" not in engine:
            return []

        import httpx
        from bs4 import BeautifulSoup

        encoded_query = quote(query)
        search_url = engine["url"].format(keyword=encoded_query)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(search_url, headers=headers)
                response.raise_for_status()
                html = response.text

            soup = BeautifulSoup(html, "lxml")
            results = []
            selectors = engine.get("selectors", {})
            containers = soup.select(selectors.get("container", ".result"))

            for container in containers[:max_results * 2]:
                try:
                    title_elem = container.select_one(selectors.get("title", "a"))
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    link_elem = container.select_one(selectors.get("link", "a"))
                    href = link_elem.get("href", "") if link_elem else ""
                    if href and not href.startswith("http"):
                        if href.startswith("//"):
                            href = "https:" + href
                        elif href.startswith("/"):
                            base_url = "/".join(search_url.split("/")[:3])
                            href = base_url + href
                    snippet_elem = container.select_one(selectors.get("snippet", "p"))
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title and href and len(title) > 2:
                        results.append({"title": title, "href": href, "body": snippet})
                        if len(results) >= max_results:
                            break
                except Exception:
                    continue

            logger.info(f"Engine {engine_id} got {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"web_fetch failed ({engine_id}): {e}")
            return []


SearchSkill = MultiSearchSkill
WebSearchSkill = MultiSearchSkill


class NewsSearchSkill(Skill):

    @property
    def name(self) -> str:
        return "news_search"

    @property
    def description(self) -> str:
        return "Search for recent news articles using DuckDuckGo."

    async def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "").strip()
        max_results = min(kwargs.get("max_results", 10), 50)
        time_range = kwargs.get("time_range", "w")

        if not query:
            return self._failure("query cannot be empty")

        if DDGS_AVAILABLE:
            try:
                try:
                    from ddgs import DDGS
                    IS_NEW = True
                except ImportError:
                    from duckduckgo_search import DDGS
                    IS_NEW = False

                def sync_search():
                    with DDGS() as ddgs:
                        if IS_NEW:
                            return list(ddgs.news(query=query, max_results=max_results, timelimit=time_range))
                        else:
                            return list(ddgs.news(keywords=query, max_results=max_results, timelimit=time_range))

                raw_results = await asyncio.to_thread(sync_search)
                if raw_results:
                    results = []
                    for r in raw_results:
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("url", ""),
                            "body": r.get("body", ""),
                            "source": r.get("source", ""),
                            "date": r.get("date", ""),
                        })
                    return self._success(
                        {"results": results, "query": query, "total": len(results)},
                        f"News search completed, found {len(results)} results"
                    )
            except Exception as e:
                logger.warning(f"DDGS news failed: {e}")

        return self._failure("DDGS news unavailable", "News search failed")
