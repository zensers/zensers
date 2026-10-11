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
import os
import re
import socket
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from src.skills.base import Skill, SkillConfig
from src.core.search_quality_filter import SearchQualityFilter, SourceCredibility

logger = logging.getLogger(__name__)

# Windows-specific guard: concurrent per-request SSL context creation inside
# the httpx client constructor can deadlock against crypto store operations
# running in executor threads (py-spy froze the run inside
# ssl.create_default_context while Baidu/DDGS threads held TLS handshakes).
# Build ONE context from the certifi CA bundle and reuse it process-wide.
_SHARED_SSL_CONTEXT: Optional[Any] = None


def _get_shared_ssl_context() -> Any:
    global _SHARED_SSL_CONTEXT
    if _SHARED_SSL_CONTEXT is None:
        import ssl
        try:
            import certifi
            _SHARED_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _SHARED_SSL_CONTEXT = ssl.create_default_context()
    return _SHARED_SSL_CONTEXT


def _search_thread_timeout() -> float:
    """Hard ceiling for executor-thread searches (requests cannot be
    cancelled once submitted, so the awaiting side must time out)."""
    try:
        return max(5.0, float(os.environ.get("ZENSERS_SEARCH_THREAD_TIMEOUT", "45")))
    except (TypeError, ValueError):
        return 45.0


SEARCH_ENGINES = {
    "baidu": {
        "name": "Baidu",
        "region": "cn",
        "priority": 1,
        "use_api": True,
    },
    "bing_cn": {
        "name": "Bing China",
        "url": "https://www.bing.com/search?q={keyword}&mkt=zh-CN&ensearch=0",
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

    # Optional legacy/local provider capability.  A missing optional package
    # must not be rediscovered for every query in a long report run.
    _BAIDU_API_AVAILABLE: Optional[bool] = None

    # DDGS rotates through public backends and is sensitive to burst traffic.
    # Keep the global limit process-wide because every Agent owns its own
    # MultiSearchSkill instance during a research run.
    _DDGS_MAX_CONCURRENCY = 4
    _DDGS_CONCURRENCY = threading.BoundedSemaphore(_DDGS_MAX_CONCURRENCY)

    # These are local listener ports used by common desktop proxy clients.
    # A TUN-only VPN does not expose any of them and should be used directly.
    _LOCAL_PROXY_CANDIDATES = (
        ("http://127.0.0.1:7890", "Clash HTTP"),
        ("http://127.0.0.1:7897", "Clash HTTP"),
        ("http://127.0.0.1:10809", "V2RayN HTTP"),
        ("socks5://127.0.0.1:1080", "Shadowsocks SOCKS5"),
    )

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        _min_quality = self._load_min_quality_score()
        self.quality_filter = SearchQualityFilter(min_quality_score=_min_quality)
        self.timeout = 30
        self._proxy = self._load_proxy()

    @staticmethod
    def _load_min_quality_score() -> float:
        """Read min_quality_score from settings.yaml, fallback to 40.0."""
        try:
            import yaml
            from pathlib import Path
            for candidate in (
                Path("config/settings.yaml"),
                Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml",
            ):
                if candidate.exists():
                    with open(candidate, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f)
                    val = cfg.get("search", {}).get("min_quality_score")
                    if val is not None:
                        return float(val)
        except Exception:
            pass
        return 40.0

    @staticmethod
    def _load_proxy() -> str:
        """
        Read proxy URL from settings.yaml or env vars.

        Priority: env vars > settings.yaml proxy.url > settings.yaml search.proxy
        """
        env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("https_proxy") or os.environ.get("http_proxy")
        if env_proxy:
            return env_proxy
        configured_proxy = ""
        try:
            import yaml
            from pathlib import Path
            for candidate in (
                Path("config/settings.yaml"),
                Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml",
            ):
                if candidate.exists():
                    with open(candidate, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f)
                    val = cfg.get("proxy", {}).get("url", "")
                    if val:
                        configured_proxy = str(val)
                        break
                    val = cfg.get("search", {}).get("proxy", "")
                    if val:
                        configured_proxy = str(val)
                        break
        except Exception:
            configured_proxy = ""

        # Do not keep routing every request to a stale localhost port. If the
        # configured local listener is down, try another common listener and
        # finally fall back to the system/TUN route.
        if configured_proxy and MultiSearchSkill._proxy_is_listening(configured_proxy):
            return configured_proxy
        if configured_proxy:
            logger.warning("Configured proxy is unavailable: %s; trying auto-detection", configured_proxy)

        detected = MultiSearchSkill._detect_local_proxy()
        if detected:
            logger.info("Auto-detected local proxy: %s", detected)
        return detected

    @staticmethod
    def _proxy_is_listening(proxy_url: str, timeout: float = 0.25) -> bool:
        """Check only local proxy listeners; never probe remote user data."""
        try:
            parsed = urlparse(proxy_url)
            host = parsed.hostname
            port = parsed.port
            if not host or not port:
                return False
            if host not in {"127.0.0.1", "localhost", "::1"}:
                return True  # Remote proxy may be intentional and cannot be TCP-probed safely here.
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, ValueError):
            return False

    @classmethod
    def _detect_local_proxy(cls) -> str:
        for proxy_url, label in cls._LOCAL_PROXY_CANDIDATES:
            if cls._proxy_is_listening(proxy_url):
                logger.info("Detected %s at %s", label, proxy_url)
                return proxy_url
        return ""

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
        """Execute a search and normalize failures at the skill boundary.

        ``_do_search`` is intentionally kept as the overridable search
        implementation.  Besides making the multi-engine implementation
        testable, this preserves the contract used by integrations that need
        to inject a deterministic search provider.
        """
        raw_query = kwargs.get("query", "")
        query = " ".join(str(item).strip() for item in raw_query if str(item).strip()) if isinstance(raw_query, (list, tuple, set)) else str(raw_query or "").strip()
        if not query:
            return self._failure("query cannot be empty")
        try:
            normalized_kwargs = dict(kwargs)
            normalized_kwargs["query"] = query
            result = await self._do_search(**normalized_kwargs)
            # Backward-compatible provider contract: injected providers may
            # return the raw result list instead of the envelope used by the
            # built-in multi-engine implementation.
            if isinstance(result, list):
                limited = result[:min(kwargs.get("max_results", 10), 200)]
                return self._success({
                    "results": limited,
                    "query": query,
                    "total": len(limited),
                }, f"Search completed, found {len(limited)} results")
            return result
        except Exception as exc:
            logger.exception("Search execution failed")
            return self._failure(str(exc), "Search failed")

    async def _do_search(self, **kwargs) -> Dict[str, Any]:
        raw_query = kwargs.get("query", "")
        query = " ".join(str(item).strip() for item in raw_query if str(item).strip()) if isinstance(raw_query, (list, tuple, set)) else str(raw_query or "").strip()
        engines = kwargs.get("engines")
        site = kwargs.get("site")
        max_results = min(kwargs.get("max_results", 10), 200)
        region = kwargs.get("region", "cn")
        use_ddgs = kwargs.get("use_ddgs", True)
        enable_quality_filter = kwargs.get("enable_quality_filter", True)
        min_quality_score = kwargs.get("min_quality_score", 40.0)
        context = kwargs.get("context")
        time_range = kwargs.get("time_range")

        if not query:
            return self._failure("query cannot be empty")

        if site:
            site = str(site).strip()
            if site:
                query = f"site:{site} {query}"

        if min_quality_score != 40.0:
            self.quality_filter.min_quality_score = min_quality_score

        is_cn = region and region.lower().startswith(("cn", "zh"))

        search_tasks: Dict[str, asyncio.Task] = {}

        if use_ddgs and DDGS_AVAILABLE:
            search_tasks["duckduckgo"] = asyncio.create_task(
                self._search_with_ddgs(query, max_results, time_range=time_range),
                name="search_ddgs"
            )

        # Baidu SERP scraping is only enabled when a proxy is available;
        # direct requests are routinely closed by Baidu anti-bot controls.
        if is_cn and self._proxy and self._baidu_api_available():
            search_tasks["baidu"] = asyncio.create_task(
                self._search_with_baidu_api(query, max_results),
                name="search_baidu"
            )

        if engines:
            engines_to_use = [e for e in engines if e in SEARCH_ENGINES and e != "baidu"]
        else:
            engines_to_use = self._select_engines(region)

        for engine_id in engines_to_use[:2]:
            search_tasks[engine_id] = asyncio.create_task(
                self._web_fetch_isolated(engine_id, query, max_results),
                name=f"search_{engine_id}"
            )

        if not search_tasks:
            return self._failure("No search engines available", "Search failed")

        task_names = list(search_tasks.keys())
        logger.info(f"Parallel search: {task_names}")

        done, pending = await asyncio.wait(
            search_tasks.values(),
            timeout=self.timeout + 5,
            return_when=asyncio.ALL_COMPLETED,
        )

        for task in pending:
            task.cancel()
        if pending:
            # 被取消的 to_thread/隔离线程任务可能永远无法完成（如线程死在
            # C 层 TLS 握手），gather 必须有上限，超时则放弃泄漏线程继续
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=_search_thread_timeout())
            except asyncio.TimeoutError:
                logger.warning("Search cleanup abandoned (threads leaked): %s",
                               [t.get_name() for t in pending])

        all_results = []
        engines_used = []
        engine_errors = {}
        engine_status = {}
        for eng_name, task in search_tasks.items():
            if task not in done:
                engine_status[eng_name] = "timeout"
                engine_errors[eng_name] = f"Timed out after {self.timeout + 5}s"
                continue
            try:
                results = task.result()
                if results:
                    all_results.extend(results)
                    engines_used.append(eng_name)
                    engine_status[eng_name] = "ok"
                    logger.info(f"{eng_name}: {len(results)} results")
                else:
                    engine_status[eng_name] = "empty"
                    logger.info(f"{eng_name}: 0 results")
            except Exception as e:
                engine_status[eng_name] = "error"
                engine_errors[eng_name] = str(e)
                logger.warning(f"{eng_name} failed: {e}")

        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("href", "") or r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        raw_results = unique_results

        if not raw_results:
            failure = self._failure("All search engines unavailable", "Search failed")
            failure.update({"engine_status": engine_status, "engine_errors": engine_errors})
            return failure

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
                if scored_raw:
                    filtered_results = scored_raw[:max_results]
                    logger.warning(f"Quality filter too strict for query: {query}, using {len(filtered_results)} low-quality results")
                else:
                    # Preserve partially relevant, non-marketing evidence for
                    # downstream review.  Returning an empty set here makes
                    # the report look like data was never searched.  Truly
                    # unrelated or explicitly tier-5 results remain blocked.
                    rescue = []
                    for r, score in zip(raw_results, quality_scores):
                        if score.credibility == SourceCredibility.TIER5_LOW_QUALITY:
                            continue
                        if score.relevance_score < 10.0:
                            continue
                        item = r.copy()
                        item["quality_score"] = score.overall_score
                        item["credibility"] = score.credibility.value
                        item["quality_rescue"] = True
                        rescue.append(item)
                    rescue.sort(key=lambda item: item.get("quality_score", 0), reverse=True)
                    if rescue:
                        filtered_results = rescue[:max_results]
                        logger.warning(
                            "All results missed the configured threshold for query: %s; "
                            "returning %d partially relevant evidence items for review",
                            query,
                            len(filtered_results),
                        )
                    else:
                        logger.warning(f"All results filtered out for query: {query}, no relevant evidence to rescue")
                        return self._failure("All results below quality threshold", "Search quality insufficient")

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
                "engine_status": engine_status,
                "engine_errors": engine_errors,
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
            "engine_status": engine_status,
            "engine_errors": engine_errors,
        }, f"Search completed, found {len(raw_results)} results")

    @classmethod
    def _baidu_api_available(cls) -> bool:
        """Return cached availability for the optional Baidu adapter."""
        if cls._BAIDU_API_AVAILABLE is not None:
            return cls._BAIDU_API_AVAILABLE
        try:
            from baidu_serp_api import BaiduPc  # noqa: F401
        except ImportError:
            cls._BAIDU_API_AVAILABLE = False
            logger.warning(
                "Baidu provider disabled: optional package 'baidu-serp-api' "
                "is not installed; continuing with AnySearch/local fallbacks"
            )
        else:
            cls._BAIDU_API_AVAILABLE = True
        return cls._BAIDU_API_AVAILABLE

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
        def sync_search(proxy: str = ""):
            # Import lazily inside the worker.  This keeps retry/fallback
            # behavior testable and prevents an optional provider import
            # failure from bypassing the normal provider error path.
            try:
                from ddgs import DDGS
                is_new = True
            except ImportError:
                from duckduckgo_search import DDGS
                is_new = False
            ddgs_kwargs = {"timeout": self.timeout}
            if proxy:
                ddgs_kwargs["proxy"] = proxy
            acquired = MultiSearchSkill._DDGS_CONCURRENCY.acquire(timeout=self.timeout)
            if not acquired:
                raise TimeoutError("DuckDuckGo concurrency limit reached")
            try:
                with DDGS(**ddgs_kwargs) as ddgs:
                    kwargs = {"max_results": max_results}
                    if time_range:
                        kwargs["timelimit"] = time_range
                    if is_new:
                        return list(ddgs.text(query=query, **kwargs))
                    else:
                        return list(ddgs.text(keywords=query, **kwargs))
            finally:
                MultiSearchSkill._DDGS_CONCURRENCY.release()

        try:
            raw_results = await asyncio.wait_for(asyncio.to_thread(sync_search, self._proxy), timeout=_search_thread_timeout())
        except Exception as proxy_error:
            if self._proxy:
                logger.warning("DDGS proxy request failed; retrying direct: %s", proxy_error)
                raw_results = await asyncio.wait_for(asyncio.to_thread(sync_search, ""), timeout=_search_thread_timeout())
            else:
                # Public DDGS backends occasionally time out under burst
                # traffic. One bounded retry improves availability without
                # multiplying the search fan-out or changing query scope.
                logger.warning("DDGS direct request failed; retrying once: %s", proxy_error)
                raw_results = await asyncio.wait_for(asyncio.to_thread(sync_search, ""), timeout=_search_thread_timeout())
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

        def sync_search():
            searcher = BaiduPc()
            proxies = None
            if self._proxy:
                proxies = {"http": self._proxy, "https": self._proxy}
            return searcher.search(query, pn=1, proxies=proxies)

        raw = await asyncio.wait_for(asyncio.to_thread(sync_search), timeout=_search_thread_timeout())
        if isinstance(raw, dict):
            # baidu-serp-api uses HTTP-like ``200`` for success while older
            # releases/examples used ``0``.  Treat only explicit non-success
            # codes as errors; the previous truthiness check rejected 200.
            code = raw.get("code")
            if code not in (None, 0, 200, "0", "200"):
                raise RuntimeError(f"Baidu SERP error {code}: {raw.get('msg', '')}")
        items = raw.get("data", {}).get("results", [])
        results = []
        for item in items[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("description", ""),
            })
        return results

    async def _web_fetch_isolated(self, engine_id: str, query: str,
                                  max_results: int):
        """独立 daemon 线程 + 独立事件循环中执行网页抓取。

        Windows/anyio 下经代理的 TLS 握手可能把事件循环死锁在 C 层
        （实测主循环阻塞 35 分钟、全部超时机制失效，隧道 socket 甚至已
        消失）。隔离到独立 daemon 线程后：宿主循环存活、超时正常触发、
        死线程不阻塞进程退出，最坏损失 = 该次搜索结果为空（调用方按
        引擎超时降级）。
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        def _runner() -> None:
            try:
                result = asyncio.run(
                    self._search_with_web_fetch(engine_id, query, max_results))
            except BaseException as exc:
                if not fut.done():
                    loop.call_soon_threadsafe(
                        fut.set_exception if not fut.cancelled()
                        else fut.cancel, exc)
            else:
                if not fut.done():
                    loop.call_soon_threadsafe(fut.set_result, result)

        threading.Thread(target=_runner, daemon=True,
                         name=f"webfetch-{engine_id}").start()
        return await fut

    async def _search_with_web_fetch(self, engine_id: str, query: str, max_results: int) -> List[Dict[str, Any]]:
        engine = SEARCH_ENGINES.get(engine_id)
        if not engine or "url" not in engine:
            return []

        import httpx
        from bs4 import BeautifulSoup

        encoded_query = quote(query)
        engine_url = engine["url"]
        if engine_id == "bing_cn":
            try:
                import yaml
                from pathlib import Path
                cfg_path = Path("config/settings.yaml")
                if cfg_path.exists():
                    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                    engine_url = cfg.get("search", {}).get("bing_cn_url", engine_url)
            except Exception:
                pass
        search_url = engine_url.format(keyword=encoded_query)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }

        _UA_LIST = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        ]

        try:
            client_kwargs = {"timeout": self.timeout, "follow_redirects": True, "verify": _get_shared_ssl_context()}
            if self._proxy:
                client_kwargs["proxy"] = self._proxy
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.get(search_url, headers=headers)
                    if response.status_code == 403 and engine_id not in ("baidu",):
                        alt_headers = dict(headers)
                        alt_headers["User-Agent"] = _UA_LIST[1]
                        response = await client.get(search_url, headers=alt_headers)
                    response.raise_for_status()
                    html = response.text

            except Exception as proxy_error:
                if not self._proxy:
                    raise
                logger.warning("%s proxy request failed; retrying direct: %s", engine_id, proxy_error)
                direct_kwargs = {"timeout": self.timeout, "follow_redirects": True}
                async with httpx.AsyncClient(**direct_kwargs) as client:
                    response = await client.get(search_url, headers=headers)
                    response.raise_for_status()
                    html = response.text

            final_path = (response.url.path or "").lower()
            if engine_id.startswith("bing") and final_path.rstrip("/") in ("", "/"):
                raise RuntimeError(f"Bing redirected to homepage: {response.url}")

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
            raise


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
        raw_query = kwargs.get("query", "")
        query = " ".join(str(item).strip() for item in raw_query if str(item).strip()) if isinstance(raw_query, (list, tuple, set)) else str(raw_query or "").strip()
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
