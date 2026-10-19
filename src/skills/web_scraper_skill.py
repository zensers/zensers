"""
WebScraperSkill - Web Content Scraping Skill (v4.0)

Three-layer architecture:
1. URL resolution  → strip search-engine redirects (Google/Bing/Baidu/Sogou/360/generic)
2. Fetch strategy  → Scrapling → Playwright → Jina Reader (fallback chain)
3. Content extract → text / markdown / tables / links
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse, unquote

from src.skills.base import Skill, SkillConfig

logger = logging.getLogger(__name__)


JS_DOMAINS = [
    "eastmoney.com", "10jqka.com.cn", "xueqiu.com",
    "caifuhao.eastmoney.com", "sohu.com",
    "36kr.com", "hstong.com",
]

_REDIRECT_DOMAINS = {
    "google.com", "www.google.com",
    "google.com.hk", "www.google.com.hk",
    "bing.com", "cn.bing.com", "www.bing.com",
    "baidu.com", "www.baidu.com",
    "sogou.com", "www.sogou.com",
    "so.com", "www.so.com",
}

_REDIRECT_PATHS = {
    "/url", "/search/url", "/imgres",
    "/link", "/click",
    "/LINGROB/",
}


def _is_search_redirect(url: str) -> bool:
    """Check if URL is a search-engine redirect (not a search results page)."""
    parsed = urlparse(url)
    path = parsed.path
    for rp in _REDIRECT_PATHS:
        if path.startswith(rp) or rp in path:
            return True
    return False


class WebScraperSkill(Skill):
    """
    Web Scraper Skill (v4.0)

    Three-layer pipeline:
    - Layer 1: URL resolution (search-engine redirect → real URL)
    - Layer 2: Fetch with fallback chain (Scrapling → Playwright → Jina Reader)
    - Layer 3: Content extraction (text/markdown/tables/links)
    """

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        self._proxy = self._load_proxy()

    @staticmethod
    def _load_proxy() -> str:
        """
        Read proxy URL from settings.yaml or env vars.

        Priority: env vars > settings.yaml proxy.url > settings.yaml search.proxy
        """
        import os
        env_proxy = (
            os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            or os.environ.get("https_proxy") or os.environ.get("http_proxy")
        )
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
                    # Global proxy first
                    val = cfg.get("proxy", {}).get("url", "")
                    if val:
                        configured_proxy = str(val)
                        break
                    # Legacy search.proxy fallback
                    val = cfg.get("search", {}).get("proxy", "")
                    if val:
                        configured_proxy = str(val)
                        break
        except Exception:
            configured_proxy = ""

        # Reuse the search skill's local-listener detection. FeiVPN TUN mode
        # exposes no HTTP/SOCKS port, so an empty result correctly means that
        # httpx should use the system route.
        from src.skills.search_skill import MultiSearchSkill
        if configured_proxy and MultiSearchSkill._proxy_is_listening(configured_proxy):
            return configured_proxy
        if configured_proxy:
            logger.warning("Configured proxy is unavailable: %s; using auto-detection", configured_proxy)
        return MultiSearchSkill._detect_local_proxy()

    def _httpx_client(self, timeout: int = 30, follow_redirects: bool = True, **kwargs):
        """Create an httpx AsyncClient with proxy if configured."""
        import httpx
        client_kwargs = {"timeout": timeout, "follow_redirects": follow_redirects, **kwargs}
        if self._proxy:
            client_kwargs["proxy"] = self._proxy
        return httpx.AsyncClient(**client_kwargs)

    @property
    def name(self) -> str:
        return "web_scraper"

    @property
    def description(self) -> str:
        return (
            "Extract content from a specific web page URL. "
            "Use this tool when the user provides a URL or link. "
            "NOT for: searching the web (use search_skill or news_search). "
            "Supports markdown/text extraction, auto-filters ads and navigation."
        )

    # ── Layer 1: URL classification ──────────────────────────────────

    @staticmethod
    def _classify_url(url: str) -> str:
        """Classify URL into fetch strategy."""
        path = urlparse(url).path.lower()
        if url.endswith(".pdf") or ".pdf?" in url or path.endswith(".pdf"):
            return "pdf"
        domain = urlparse(url).netloc.lower()
        if domain in _REDIRECT_DOMAINS:
            if _is_search_redirect(url):
                return "search_redirect"
        for js_domain in JS_DOMAINS:
            if js_domain in domain:
                return "js"
        return "static"

    # ── Layer 1: Search-engine redirect resolution ────────────────────

    @staticmethod
    def _resolve_google_url(url: str) -> Optional[str]:
        """Resolve Google redirect: /url?q=REAL_URL&sa=..."""
        parsed = urlparse(url)
        if parsed.path not in ("/url", "/search/url", "/imgres"):
            return None
        qs = parse_qs(parsed.query)
        real = qs.get("q", qs.get("url", qs.get("imgurl", [])))
        if real and real[0].startswith("http"):
            return unquote(real[0])
        return None

    @staticmethod
    def _resolve_bing_url(url: str) -> Optional[str]:
        """Resolve Bing redirect via query params or /LINGROB/ path."""
        parsed = urlparse(url)
        if "/LINGROB/" in parsed.path or parsed.path.startswith("/click"):
            qs = parse_qs(parsed.query)
            real = qs.get("u", [])
            if real:
                return unquote(real[0])
        return None

    @staticmethod
    def _resolve_sogou_url(url: str) -> Optional[str]:
        """Resolve Sogou redirect: /link?url=REAL_URL"""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        real = qs.get("url", [])
        if real and real[0].startswith("http"):
            return unquote(real[0])
        return None

    @staticmethod
    def _resolve_360_url(url: str) -> Optional[str]:
        """Resolve 360 search redirect: /link?url=REAL_URL"""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        real = qs.get("url", qs.get("q", []))
        if real and real[0].startswith("http"):
            return unquote(real[0])
        return None

    async def _resolve_baidu_url(self, url: str) -> Optional[str]:
        """Resolve Baidu redirect: /link?url=... via HTTP meta/js parsing."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with self._httpx_client(timeout=10, follow_redirects=False) as client:
                resp = await client.get(url, headers=headers)
                html = resp.text

            m = re.search(
                r'<meta\s+http-equiv=["\']refresh["\']\s+content=["\']\d+;url=([^"\']+)["\']',
                html, re.IGNORECASE,
            )
            if m:
                return m.group(1).strip()

            m = re.search(r'window\.location(?:\s*=\s*|\.href\s*=\s*["\'])([^"\'\s;]+)', html)
            if m:
                return m.group(1).strip()
        except Exception as e:
            logger.debug(f"Baidu redirect resolution failed: {e}")
        return None

    async def _resolve_redirect_url(self, url: str) -> str:
        """
        Unified redirect resolution: detect search-engine redirect URLs
        and extract the real target URL.

        Falls back to HTTP HEAD follow-redirect for unknown redirect patterns.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        resolved = None

        # Google
        if domain in ("google.com", "www.google.com",
                       "google.com.hk", "www.google.com.hk"):
            resolved = self._resolve_google_url(url)

        # Bing
        elif domain in ("bing.com", "cn.bing.com", "www.bing.com"):
            resolved = self._resolve_bing_url(url)

        # Baidu
        elif domain in ("baidu.com", "www.baidu.com"):
            resolved = await self._resolve_baidu_url(url)

        # Sogou
        elif domain in ("sogou.com", "www.sogou.com"):
            resolved = self._resolve_sogou_url(url)

        # 360
        elif domain in ("so.com", "www.so.com"):
            resolved = self._resolve_360_url(url)

        # Generic fallback: HTTP HEAD follow-redirect
        if resolved is None and domain in _REDIRECT_DOMAINS:
            resolved = await self._resolve_via_head(url)

        if resolved:
            logger.info(f"Redirect resolved: {url[:60]} -> {resolved[:60]}")
            return resolved

        return url

    async def _resolve_via_head(self, url: str) -> Optional[str]:
        """Follow HTTP redirects (HEAD) to find the final URL."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with self._httpx_client(
                timeout=10, follow_redirects=True, max_redirects=5
            ) as client:
                resp = await client.head(url, headers=headers)
                final_url = str(resp.url)
                if final_url != url:
                    return final_url
        except Exception as e:
            logger.debug(f"HEAD redirect resolution failed: {e}")
        return None

    # ── Layer 2: Fetch strategies ────────────────────────────────────

    async def _fetch_html(self, url: str, timeout: int = 30) -> str:
        """Fetch a static HTML page via Scrapling (auto anti-bot detection)."""
        from scrapling.fetchers.requests import AsyncFetcher

        response = await AsyncFetcher.get(url)
        if response is None:
            raise IOError(f"Scrapling returned None: {url}")
        if response.status >= 400:
            raise IOError(f"HTTP {response.status}: {url}")
        return response.body.decode(response.encoding or "utf-8")

    async def _fetch_with_playwright(self, url: str, timeout: int = 30) -> Tuple[str, str]:
        """
        Fetch a JS-rendered page via Playwright.

        Returns:
            (html_string, title_string)
        """
        from playwright.async_api import async_playwright

        launch_opts: dict = {"headless": True}
        if self._proxy:
            launch_opts["proxy"] = {"server": self._proxy}

        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_opts)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                html = await page.content()
                title = await page.title()
                return html, title
            finally:
                await browser.close()

    async def _fetch_with_jina(self, url: str, timeout: int = 30) -> str:
        """Fetch via Jina Reader as last-resort fallback (returns markdown)."""
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain",
        }
        async with self._httpx_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def _fetch_pdf(self, url: str, timeout: int = 30) -> Tuple[str, str]:
        """
        Fetch and extract text from a PDF file.

        Returns:
            (text_string, title_string)
        """
        import pdfplumber
        import io

        async with self._httpx_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        title = url.split("/")[-1] if "/" in url else url
        text_parts = []
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)

        return "\n".join(text_parts), title

    async def _fetch_with_fallback(
        self, url: str, url_type: str, timeout: int = 30
    ) -> Tuple[str, str, str]:
        """
        Execute fetch with full fallback chain.

        Returns:
            (html_or_text, title, strategy_used)
        """
        errors = []

        if url_type == "js":
            strategies = [
                ("playwright", self._fetch_with_playwright),
                ("jina", self._fetch_with_jina),
            ]
        else:
            strategies = [
                ("scrapling", self._fetch_html_as_tuple),
                ("playwright", self._fetch_with_playwright),
                ("jina", self._fetch_with_jina_as_tuple),
            ]

        for strategy_name, fetch_fn in strategies:
            try:
                result = await fetch_fn(url, timeout)
                logger.info(f"Fetched {url[:50]} via {strategy_name}")
                if isinstance(result, tuple):
                    return result[0], result[1], strategy_name
                return result, "", strategy_name
            except Exception as e:
                errors.append(f"{strategy_name}: {e}")
                logger.debug(f"Strategy {strategy_name} failed for {url[:50]}: {e}")
                continue

        raise RuntimeError(
            f"All fetch strategies failed for {url}: {'; '.join(errors)}"
        )

    async def _fetch_html_as_tuple(
        self, url: str, timeout: int = 30
    ) -> Tuple[str, str]:
        """Wrapper so _fetch_html returns (html, title) like Playwright."""
        html = await self._fetch_html(url, timeout)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        return html, title

    async def _fetch_with_jina_as_tuple(
        self, url: str, timeout: int = 30
    ) -> Tuple[str, str]:
        """Wrapper so Jina returns (text, title) like Playwright."""
        text = await self._fetch_with_jina(url, timeout)
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""
        return text, title

    # ── Main execute ────────────────────────────────────────────────

    async def execute(self, **kwargs) -> Dict[str, Any]:
        url = kwargs.get("url", "").strip()
        action = kwargs.get("action", "extract_text")
        timeout = kwargs.get("timeout", 30)
        max_chars = kwargs.get("max_chars")

        if not url:
            return self._failure("url cannot be empty")
        if not url.startswith(("http://", "https://")):
            return self._failure(f"Invalid URL format: {url}")

        handlers = {
            "extract_text": self._extract_text,
            "extract_markdown": self._extract_markdown,
            "extract_tables": self._extract_tables,
            "extract_links": self._extract_links,
        }
        handler = handlers.get(action)
        if handler is None:
            return self._failure(f"Unsupported action: {action}")

        # Layer 1: URL resolution
        url_type = self._classify_url(url)
        original_url = url
        if url_type == "search_redirect":
            resolved = await self._resolve_redirect_url(url)
            if resolved != url:
                url = resolved
                url_type = self._classify_url(url)

        # Layer 2+3: Fetch & extract
        try:
            if url_type == "pdf":
                text, title = await self._fetch_pdf(url, timeout)
                if max_chars and len(text) > max_chars:
                    text = text[:max_chars] + "\n...[content truncated]"
                return self._success(
                    {
                        "text": text, "title": title,
                        "url": url, "original_url": original_url,
                        "content_length": len(text),
                    },
                    "PDF extraction successful",
                )

            html, title, strategy = await self._fetch_with_fallback(url, url_type, timeout)

            result = await handler(html, url, max_chars)
            if result.get("success"):
                data = result.get("result", result)
                if isinstance(data, dict):
                    data["original_url"] = original_url
                    data["fetch_strategy"] = strategy
                    if url != original_url:
                        data["resolved_url"] = url
            return result

        except Exception as e:
            return self._failure(str(e), "Web scraping failed")

    # ── Layer 3: Content extraction ──────────────────────────────────

    async def _extract_text(
        self, html: str, url: str, max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "meta", "noscript", "iframe", "svg"]):
            tag.decompose()
        for selector in [
            "nav", "header", "footer", "aside",
            ".nav", ".navigation", ".menu", ".sidebar", ".aside",
            ".ad", ".ads", ".advertisement", ".banner", ".popup",
            "#nav", "#navigation", "#menu", "#sidebar", "#aside",
            "#ad", "#ads", "#advertisement", "#banner", "#popup",
            "[class*='nav-']", "[class*='sidebar-']", "[class*='ad-']",
        ]:
            for tag in soup.select(selector):
                tag.decompose()

        main_content = None
        for selector in ["article", "main", ".content", ".article", ".post", "#content", "#article"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        if not main_content:
            main_content = soup.body if soup.body else soup

        title = ""
        title_tag = soup.title
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(strip=True) or title

        text = main_content.get_text(separator="\n", strip=True)
        lines = [line for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        if max_chars and len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars] + "\n...[content truncated]"

        return self._success(
            {"text": clean_text, "title": title, "url": url, "content_length": len(clean_text)},
            "Text extraction successful",
        )

    async def _extract_markdown(
        self, html: str, url: str, max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "meta", "noscript", "iframe", "svg"]):
            tag.decompose()
        for selector in ["nav", "header", "footer", "aside", ".nav", ".sidebar", ".ad"]:
            for tag in soup.select(selector):
                tag.decompose()

        main_content = None
        for selector in ["article", "main", ".content", ".article", ".post"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        if not main_content:
            main_content = soup.body if soup.body else soup

        markdown = self._html_to_markdown(main_content)
        title = ""
        title_tag = soup.title
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        if max_chars and len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n\n...[content truncated]"

        return self._success(
            {"text": markdown, "title": title, "url": url, "content_length": len(markdown)},
            "Markdown extraction successful",
        )

    def _html_to_markdown(self, element) -> str:
        from bs4 import NavigableString, Tag

        result = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    result.append(text)
            elif isinstance(child, Tag):
                tag_name = child.name.lower()
                if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    level = int(tag_name[1])
                    result.append(f"\n{'#' * level} {child.get_text(strip=True)}\n")
                elif tag_name == "p":
                    result.append(f"\n{self._html_to_markdown(child)}\n")
                elif tag_name in ["ul", "ol"]:
                    items = child.find_all("li", recursive=False)
                    for i, item in enumerate(items):
                        prefix = f"{i + 1}." if tag_name == "ol" else "-"
                        result.append(f"{prefix} {item.get_text(strip=True)}")
                    result.append("")
                elif tag_name == "a":
                    text = child.get_text(strip=True)
                    href = child.get("href", "")
                    result.append(f"[{text}]({href})" if href else text)
                elif tag_name in ["strong", "b"]:
                    result.append(f"**{child.get_text(strip=True)}**")
                elif tag_name in ["em", "i"]:
                    result.append(f"*{child.get_text(strip=True)}*")
                elif tag_name == "code":
                    text = child.get_text()
                    result.append(f"```\n{text}\n```" if child.parent and child.parent.name == "pre" else f"`{text}`")
                elif tag_name == "pre":
                    result.append(f"\n```\n{child.get_text()}\n```\n")
                elif tag_name == "blockquote":
                    for line in child.get_text(strip=True).split("\n"):
                        result.append(f"> {line}")
                    result.append("")
                elif tag_name == "br":
                    result.append("\n")
                elif tag_name in ["div", "span", "section", "article"]:
                    result.append(self._html_to_markdown(child))
                else:
                    result.append(self._html_to_markdown(child))
        return "".join(result)

    async def _extract_tables(self, html: str, url: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                row = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if row:
                    rows.append(row)
            if rows:
                tables.append(rows)
        return self._success({"tables": tables, "count": len(tables), "url": url}, f"Extracted {len(tables)} tables")

    async def _extract_links(self, html: str, url: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") or not href.startswith("http"):
                href = urljoin(url, href)
            links.append({"url": href, "text": a.get_text(strip=True)})
        return self._success({"links": links, "count": len(links), "url": url}, f"Extracted {len(links)} links")


WebFetchSkill = WebScraperSkill
