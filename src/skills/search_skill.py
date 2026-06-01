"""
MultiSearchSkill - Multi-Search Engine Integration Skill (v4.0 Full Version)

Based on web_fetch technology, integrates 17 search engines without requiring API Keys.

Core principles:
1. Use web_fetch to directly access search engine URLs
2. Parse returned HTML to extract search results
3. Support pagination, advanced search operators, time filtering

Search engine list:
- Domestic (8): Baidu, Bing CN/INT, 360, Sogou, WeChat, Toutiao, Jisilu
- International (9): Google, Google HK, DuckDuckGo, Yahoo, Startpage, Brave, Ecosia, Qwant, WolframAlpha

Reference: C:/Users/Administrator/.workbuddy/skills/multi-search-engine/SKILL.md
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

from src.skills.base import Skill, SkillConfig
from src.core.search_quality_filter import SearchQualityFilter

logger = logging.getLogger(__name__)


# Search engine configuration - 17 engines
SEARCH_ENGINES = {
    # === Domestic search engines (8) ===
    "baidu": {
        "name": "Baidu",
        "url": "https://www.baidu.com/s?wd={keyword}",
        "pagination": {"param": "pn", "start": 0, "step": 10},
        "region": "cn",
        "priority": 1,
        "selectors": {
            "container": ".result, #content_left > div",
            "title": "h3 a, .t a",
            "link": "h3 a, .t a",
            "snippet": ".c-abstract, .c-span9, p",
        }
    },
    "bing_cn": {
        "name": "Bing China",
        "url": "https://cn.bing.com/search?q={keyword}&ensearch=0",
        "pagination": {"param": "first", "start": 1, "step": 10},
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
        "pagination": {"param": "first", "start": 1, "step": 10},
        "region": "global",
        "priority": 3,
        "selectors": {
            "container": ".b_algo",
            "title": "h2 a",
            "link": "h2 a",
            "snippet": ".b_caption p, p",
        }
    },
    "so": {
        "name": "360 Search",
        "url": "https://www.so.com/s?q={keyword}",
        "pagination": {"param": "pn", "start": 0, "step": 10},
        "region": "cn",
        "priority": 4,
        "selectors": {
            "container": ".result, li[data-index]",
            "title": "h3 a, a[href]",
            "link": "h3 a, a[href]",
            "snippet": "p",
        }
    },
    "sogou": {
        "name": "Sogou",
        "url": "https://sogou.com/web?query={keyword}",
        "pagination": {"param": "page", "start": 1, "step": 1},
        "region": "cn",
        "priority": 5,
        "selectors": {
            "container": ".vrwrap, .result",
            "title": "h3 a, a[href]",
            "link": "h3 a, a[href]",
            "snippet": "p, .str-text-info",
        }
    },
    "wechat": {
        "name": "WeChat Search",
        "url": "https://wx.sogou.com/weixin?type=2&query={keyword}",
        "pagination": {"param": "page", "start": 1, "step": 1},
        "region": "cn",
        "priority": 6,
        "selectors": {
            "container": ".news-box, .txt-box",
            "title": "h3 a, .tit a",
            "link": "h3 a, .tit a",
            "snippet": "p, .txt",
        }
    },
    "toutiao": {
        "name": "Toutiao Search",
        "url": "https://so.toutiao.com/search?keyword={keyword}",
        "pagination": {"param": "offset", "start": 0, "step": 10},
        "region": "cn",
        "priority": 7,
        "selectors": {
            "container": ".result, article",
            "title": "a[href]",
            "link": "a[href]",
            "snippet": "p",
        }
    },
    "jisilu": {
        "name": "Jisilu",
        "url": "https://www.jisilu.cn/explore/?keyword={keyword}",
        "pagination": None,
        "region": "cn",
        "priority": 8,
        "selectors": {
            "container": ".item, article",
            "title": "a[href]",
            "link": "a[href]",
            "snippet": "p",
        }
    },
    
    # === International search engines (9) ===
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
    "duckduckgo": {
        "name": "DuckDuckGo",
        "url": "https://duckduckgo.com/html/?q={keyword}",
        "pagination": {"param": "s", "start": 0, "step": 30},
        "region": "global",
        "priority": 12,
        "selectors": {
            "container": ".result, article",
            "title": "h2 a, a.result__a",
            "link": "h2 a, a.result__a",
            "snippet": ".result__snippet, a[href]",
        }
    },
    "yahoo": {
        "name": "Yahoo",
        "url": "https://search.yahoo.com/search?p={keyword}",
        "pagination": {"param": "b", "start": 1, "step": 10},
        "region": "global",
        "priority": 13,
        "selectors": {
            "container": ".dd.algo, .Sr",
            "title": "h3 a, a[href]",
            "link": "h3 a, a[href]",
            "snippet": "p, .compText",
        }
    },
    "startpage": {
        "name": "Startpage",
        "url": "https://www.startpage.com/sp/search?query={keyword}",
        "pagination": None,
        "region": "global",
        "priority": 14,
        "selectors": {
            "container": ".w-gl, .result",
            "title": "a.result-link, h3 a, a[href]",
            "link": "a.result-link, h3 a, a[href]",
            "snippet": "p.description, p",
        }
    },
    "brave": {
        "name": "Brave Search",
        "url": "https://search.brave.com/search?q={keyword}",
        "pagination": {"param": "offset", "start": 0, "step": 10},
        "region": "global",
        "priority": 15,
        "selectors": {
            "container": ".snippet, div[data-pos]",
            "title": "a.snippet-title, h3 a, a[href]",
            "link": "a.snippet-title, h3 a, a[href]",
            "snippet": "p, .snippet-description",
        }
    },
    "ecosia": {
        "name": "Ecosia",
        "url": "https://www.ecosia.org/search?q={keyword}",
        "pagination": None,
        "region": "global",
        "priority": 16,
        "selectors": {
            "container": ".result, article",
            "title": "a.result-title, h2 a, a[href]",
            "link": "a.result-title, h2 a, a[href]",
            "snippet": "p.snippet, p",
        }
    },
    "qwant": {
        "name": "Qwant",
        "url": "https://www.qwant.com/?q={keyword}",
        "pagination": None,
        "region": "global",
        "priority": 17,
        "selectors": {
            "container": ".result, article",
            "title": "a[href]",
            "link": "a[href]",
            "snippet": "p",
        }
    },
    "wolframalpha": {
        "name": "WolframAlpha",
        "url": "https://www.wolframalpha.com/input?i={keyword}",
        "pagination": None,
        "region": "global",
        "priority": 18,
        "selectors": {
            "container": ".output, .pod",
            "title": "title",
            "link": None,
            "snippet": ".output, .pod",
        }
    },
}

# DuckDuckGo library as fallback (more reliable)
# Note: duckduckgo_search has been renamed to ddgs, prefer new package name
DDGS_AVAILABLE = False
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        # Compatible with old package name
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        pass


class MultiSearchSkill(Skill):
    """
    Multi-Search Engine Skill (v4.0)
    
    Supports two search modes:
    1. **web_fetch mode**: Directly access search engine URLs, parse HTML
    2. **DDGS mode**: Use duckduckgo-search library (more reliable)
    
    Usage:
        skill = MultiSearchSkill()
        result = await skill.execute(
            query="AI market size",
            engines=["baidu", "bing_cn", "duckduckgo"],
            max_results=20,
        )
    """
    
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
            "Search the web for general information, data, or research. "
            "Use this tool for: market data, company info, industry analysis, general knowledge. "
            "NOT for: current news (use news_search), specific URLs (use web_scraper). "
            "Supports 17 search engines (Baidu, Bing, Google, etc.). No API Key required."
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute multi-engine search
        
        Args:
            query: Search keyword (required)
            engines: Search engine list (default auto-select)
            max_results: Maximum return count (default 10)
            region: Region (cn/global, default cn)
            use_ddgs: Prefer DuckDuckGo library (default True, more reliable)
            enable_quality_filter: Enable quality filtering (default True)
            min_quality_score: Minimum quality score threshold (default 40)
            time_range: DDGS time limit - "d" (day), "w" (week), "m" (month), "y" (year)
            
        Returns:
            Search result dictionary
        """
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
        
        # Threshold override: @property setter in SearchQualityFilter
        # enforces a floor of 30.0, so even if a caller passes a low value,
        # the filter remains effective.
        if min_quality_score != 40.0:
            self.quality_filter.min_quality_score = min_quality_score
        
        all_results = []
        engines_used = []
        
        # Prefer DDGS library (more reliable)
        if use_ddgs and DDGS_AVAILABLE:
            try:
                ddgs_results = await self._search_with_ddgs(query, max_results, time_range=time_range)
                if ddgs_results:
                    all_results.extend(ddgs_results)
                    engines_used.append("duckduckgo_search")
                    logger.info(f"DDGS search successful, got {len(ddgs_results)} results")
            except Exception as e:
                logger.warning(f"DDGS search failed: {e}, trying other engines")
        
        # If DDGS results insufficient, use web_fetch mode to supplement
        if len(all_results) < max_results:
            # Select search engines
            if engines:
                engines_to_use = [e for e in engines if e in SEARCH_ENGINES]
            else:
                engines_to_use = self._select_engines(region)
            
            # Search with web_fetch
            for engine_id in engines_to_use[:3]:  # Try at most 3 engines
                if len(all_results) >= max_results:
                    break
                    
                try:
                    results = await self._search_with_web_fetch(
                        engine_id, query, max_results - len(all_results)
                    )
                    if results:
                        all_results.extend(results)
                        if engine_id not in engines_used:
                            engines_used.append(engine_id)
                except Exception as e:
                    logger.warning(f"Engine {engine_id} search failed: {e}")
                    continue
        
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
            filtered_results, quality_scores = self.quality_filter.filter_results(
                raw_results, query, context
            )
            
            # Guard: if filter is too aggressive, fall back to top-N scored raw results
            # This prevents legitimate data (e.g., Chinese news sources) being
            # discarded by overly broad domain patterns
            if len(filtered_results) < min(3, max_results):
                logger.warning(
                    f"Quality filter too aggressive: {len(raw_results)} -> {len(filtered_results)}, "
                    f"falling back to top-{max_results} scored raw results"
                )
                # Score raw results and take top-N instead of bypassing filter entirely
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
            
            logger.info(f"Quality filtering: {len(raw_results)} -> {len(filtered_results)} results")
            
            return self._success(
                {
                    "results": filtered_results,
                    "query": query,
                    "total": len(filtered_results),
                    "raw_total": len(raw_results),
                    "engines_used": engines_used,
                    "quality_stats": {
                        "filtered_count": len(raw_results) - len(filtered_results),
                        "tier_distribution": tier_counts,
                    },
                },
                f"Search completed using {len(engines_used)} engines, kept {len(filtered_results)}/{len(raw_results)} results"
            )
        
        return self._success(
            {
                "results": raw_results[:max_results],
                "query": query,
                "total": len(raw_results[:max_results]),
                "engines_used": engines_used,
            },
            f"Search completed, found {len(raw_results)} results"
        )

    def _select_engines(self, region: str) -> List[str]:
        """Select search engines based on region"""
        is_cn = region and region.lower().startswith(("cn", "zh"))
        
        engines = []
        for eng_id, eng_config in SEARCH_ENGINES.items():
            if is_cn and eng_config["region"] == "cn":
                engines.append((eng_id, eng_config["priority"]))
            elif not is_cn and eng_config["region"] in ("global", "cn"):
                engines.append((eng_id, eng_config["priority"]))
        
        engines.sort(key=lambda x: x[1])
        return [eng[0] for eng in engines]

    async def _search_with_ddgs(self, query: str, max_results: int, time_range: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo library (more reliable)"""
        # Prefer new package name ddgs, compatible with old package name
        try:
            from ddgs import DDGS
            IS_NEW_DDGS = True
        except ImportError:
            from duckduckgo_search import DDGS
            IS_NEW_DDGS = False
        
        def sync_search():
            with DDGS(timeout=self.timeout) as ddgs:
                ddgs_kwargs = {"max_results": max_results}
                if time_range:
                    ddgs_kwargs["timelimit"] = time_range
                # New ddgs uses query parameter, old version uses keywords
                if IS_NEW_DDGS:
                    results = list(ddgs.text(
                        query=query,
                        **ddgs_kwargs,
                    ))
                else:
                    results = list(ddgs.text(
                        keywords=query,
                        **ddgs_kwargs,
                    ))
            return results
        
        raw_results = await asyncio.to_thread(sync_search)
        
        # Normalize result format
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "href": r.get("href", ""),
                "body": r.get("body", ""),
            })
        
        return results

    async def _search_with_web_fetch(
        self,
        engine_id: str,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        Search using web_fetch mode
        
        This is OpenClaw's core method: directly access search engine URLs, parse HTML
        """
        import httpx
        from bs4 import BeautifulSoup
        
        engine = SEARCH_ENGINES.get(engine_id)
        if not engine:
            return []
        
        # Build search URL
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
            
            # Parse HTML
            soup = BeautifulSoup(html, "lxml")
            results = []
            
            selectors = engine.get("selectors", {})
            containers = soup.select(selectors.get("container", ".result"))
            
            for container in containers[:max_results * 2]:
                try:
                    # Extract title
                    title_elem = container.select_one(selectors.get("title", "a"))
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Extract link
                    link_elem = container.select_one(selectors.get("link", "a"))
                    href = link_elem.get("href", "") if link_elem else ""
                    
                    # Clean link (handle redirects)
                    if href and not href.startswith("http"):
                        if href.startswith("//"):
                            href = "https:" + href
                        elif href.startswith("/"):
                            base_url = "/".join(search_url.split("/")[:3])
                            href = base_url + href
                    
                    # Extract snippet
                    snippet_elem = container.select_one(selectors.get("snippet", "p"))
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    if title and href and len(title) > 2:
                        results.append({
                            "title": title,
                            "href": href,
                            "body": snippet,
                        })
                        
                        if len(results) >= max_results:
                            break
                            
                except Exception as e:
                    logger.debug(f"Failed to parse result: {e}")
                    continue
            
            logger.info(f"Engine {engine_id} got {len(results)} results")
            return results
            
        except Exception as e:
            logger.warning(f"web_fetch search failed ({engine_id}): {e}")
            return []


# Maintain backward compatibility
SearchSkill = MultiSearchSkill
WebSearchSkill = MultiSearchSkill


class NewsSearchSkill(Skill):
    """News Search Skill - with fallback to web search when DDGS fails"""

    @property
    def name(self) -> str:
        return "news_search"

    @property
    def description(self) -> str:
        return (
            "Search for recent news articles. "
            "Use this tool when you need to find CURRENT news, events, or time-sensitive information. "
            "NOT for: general web pages, historical data, or URLs (use web_scraper for URLs). "
            "Supports Chinese and English queries. No API Key required."
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute news search with fallback mechanism"""
        query = kwargs.get("query", "").strip()
        max_results = min(kwargs.get("max_results", 10), 50)
        time_range = kwargs.get("time_range", "w")
        
        if not query:
            return self._failure("query cannot be empty")
        
        # Try DDGS first
        if DDGS_AVAILABLE:
            try:
                # Prefer new package name ddgs, compatible with old package name
                try:
                    from ddgs import DDGS
                    IS_NEW_DDGS = True
                except ImportError:
                    from duckduckgo_search import DDGS
                    IS_NEW_DDGS = False
                
                def sync_search():
                    with DDGS() as ddgs:
                        # New ddgs uses query parameter, old version uses keywords
                        if IS_NEW_DDGS:
                            return list(ddgs.news(
                                query=query,
                                max_results=max_results,
                                timelimit=time_range,
                            ))
                        else:
                            return list(ddgs.news(
                                keywords=query,
                                max_results=max_results,
                                timelimit=time_range,
                            ))
                
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
                else:
                    logger.warning("DDGS news returned empty, falling back to web search")
                    
            except Exception as e:
                logger.warning(f"DDGS news search failed: {e}, falling back to web search")
        
        # Fallback: Use MultiSearchSkill with news-enhanced query
        # This provides robustness when DDGS is unavailable or fails
        logger.info(f"[NewsSearch] Using fallback: web search for '{query}'")
        
        try:
            search_skill = MultiSearchSkill()
            # Enhance query with news-related keywords
            enhanced_query = f"{query} 最新 新闻"
            
            result = await search_skill.execute(
                query=enhanced_query,
                engines=["baidu", "bing_cn", "toutiao", "sogou"],  # Prefer CN engines for news
                max_results=max_results,
                region="cn",
                use_ddgs=False,  # Avoid DDGS in fallback
            )
            
            if result.get("success") and result.get("result", {}).get("results"):
                # Transform web search results to news format
                web_results = result["result"]["results"]
                news_results = []
                for r in web_results:
                    news_results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", ""),
                        "source": r.get("href", "").split("/")[2] if r.get("href") else "",
                        "date": "",  # Web search doesn't have date
                    })
                
                return self._success(
                    {"results": news_results, "query": query, "total": len(news_results)},
                    f"News search (fallback) completed, found {len(news_results)} results"
                )
            else:
                return self._failure("Both DDGS and fallback web search failed", "News search failed")
                
        except Exception as fallback_error:
            logger.error(f"Fallback web search also failed: {fallback_error}")
            return self._failure(str(fallback_error), "News search failed (including fallback)")
