"""
WebScraperSkill - Web Content Scraping Skill (v3.0)

Multi-strategy content fetching:
1. Static pages → httpx + BeautifulSoup (fast, no overhead)
2. JS-rendered pages → Playwright (headless Chromium)
3. PDF files → pdfplumber
4. Baidu redirect links → extract real URL then re-classify
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from src.skills.base import Skill, SkillConfig

logger = logging.getLogger(__name__)


# Domains known to require JavaScript rendering
JS_DOMAINS = [
    "eastmoney.com", "10jqka.com.cn", "xueqiu.com",
    "caifuhao.eastmoney.com", "sohu.com",
    "36kr.com", "hstong.com",
]


class WebScraperSkill(Skill):
    """
    Web Scraper Skill (v3.0)

    Auto-routes URLs to the appropriate fetch strategy:
    - Static HTML → httpx
    - JS-heavy sites → Playwright
    - PDF files → pdfplumber
    - Baidu redirects → resolve then re-route
    """

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

    # ── URL classification ──────────────────────────────────────────

    @staticmethod
    def _classify_url(url: str) -> str:
        """Classify URL into fetch strategy."""
        path = urlparse(url).path.lower()
        if url.endswith(".pdf") or ".pdf?" in url or path.endswith(".pdf"):
            return "pdf"
        if "baidu.com/link?" in url:
            return "baidu_redirect"
        domain = urlparse(url).netloc.lower()
        for js_domain in JS_DOMAINS:
            if js_domain in domain:
                return "js"
        return "static"

    # ── Baidu redirect resolution ───────────────────────────────────

    async def _resolve_baidu_url(
        self,
        url: str,
        fetch_mock: Optional[Any] = None,
    ) -> str:
        """
        Resolve a Baidu redirect URL to the real target URL.

        Args:
            url: Baidu redirect URL (http://www.baidu.com/link?url=...)
            fetch_mock: Optional mock for testing (async callable returning HTML)

        Returns:
            Real target URL, or original URL if resolution fails.
        """
        try:
            if fetch_mock is not None:
                html = await fetch_mock(url)
            else:
                import httpx
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }
                async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                    resp = await client.get(url, headers=headers)
                    html = resp.text

            # Try meta refresh redirect first
            m = re.search(
                r'<meta\s+http-equiv=["\']refresh["\']\s+content=["\']\d+;url=([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if m:
                return m.group(1).strip()

            # Try window.location redirect
            m = re.search(r'window\.location(?:\s*=\s*|\.href\s*=\s*["\'])([^"\'\s;]+)', html)
            if m:
                return m.group(1).strip()

        except Exception as e:
            logger.debug(f"Baidu redirect resolution failed: {e}")

        return url

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

        # URL classification & resolution
        url_type = self._classify_url(url)
        if url_type == "baidu_redirect":
            resolved = await self._resolve_baidu_url(url)
            if resolved != url:
                logger.info(f"Baidu redirect resolved: {url[:50]} -> {resolved[:50]}")
                url = resolved
                url_type = self._classify_url(url)

        # Fetch by type
        try:
            if url_type == "pdf":
                text, title = await self._fetch_pdf(url, timeout)
                if max_chars and len(text) > max_chars:
                    text = text[:max_chars] + "\n...[content truncated]"
                return self._success(
                    {"text": text, "title": title, "url": url, "content_length": len(text)},
                    "PDF extraction successful",
                )

            if url_type == "js":
                html, title = await self._fetch_with_playwright(url, timeout)
            else:
                html = await self._fetch_html(url, timeout)

            return await handler(html, url, max_chars)

        except Exception as e:
            return self._failure(str(e), "Web scraping failed")

    # ── Fetch strategies ────────────────────────────────────────────

    async def _fetch_html(self, url: str, timeout: int = 30) -> str:
        """Fetch a static HTML page via Scrapling (auto anti-bot detection)."""
        from scrapling.fetchers.requests import AsyncFetcher

        fetcher = AsyncFetcher()
        fetcher.adaptive = True
        response = await fetcher.get(url)
        if response.status >= 400:
            raise IOError(f"HTTP {response.status} {response.reason}: {url}")
        return response.body.decode(response.encoding or "utf-8")

    async def _fetch_with_playwright(self, url: str, timeout: int = 30) -> tuple:
        """
        Fetch a JS-rendered page via Playwright.

        Returns:
            (html_string, title_string)
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                html = await page.content()
                title = await page.title()
                return html, title
            finally:
                await browser.close()

    async def _fetch_pdf(self, url: str, timeout: int = 30) -> tuple:
        """
        Fetch and extract text from a PDF file.

        Returns:
            (text_string, title_string)
        """
        import httpx
        import pdfplumber
        import io

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
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

    # ── Content extraction (unchanged from v2) ──────────────────────

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
