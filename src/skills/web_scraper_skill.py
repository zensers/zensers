"""
WebScraperSkill - Web Content Scraping Skill (v2.0 Refactored)

Implements OpenClaw-style web_fetch functionality:
- Intelligent content extraction: Auto-identify main content, filter navigation, ads, sidebars
- Multiple extraction modes: markdown mode preserves structure, text mode returns plain text
- Lightweight retry mechanism: Auto-handle network errors
- Resource optimization: Support character limit, control return content size

v2.0 improvements:
- Use httpx instead of aiohttp (better performance)
- Add intelligent content extraction algorithm
- Support markdown and text extraction modes
- Built-in error retry mechanism
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from src.skills.base import Skill, SkillConfig

logger = logging.getLogger(__name__)


class WebScraperSkill(Skill):
    """
    Web Scraper Skill (v2.0)
    
    Implements OpenClaw web_fetch-like functionality:
    - Fetch web content from specified URL
    - Intelligently extract main content
    - Support markdown and text output formats
    
    Usage:
        skill = WebScraperSkill()
        result = await skill.execute(
            url="https://example.com/article",
            action="extract_text",  # or "extract_markdown"
            max_chars=15000,
        )
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

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute web scraping

        Args:
            url: Target page URL (required)
            action: Extraction action (extract_text/extract_markdown/extract_tables/extract_links)
            timeout: Timeout in seconds (default 30)
            max_chars: Maximum character limit (default unlimited)
            retry_count: Retry count (default 3)

        Returns:
            Operation result dictionary
        """
        url = kwargs.get("url", "").strip()
        action = kwargs.get("action", "extract_text")
        timeout = kwargs.get("timeout", 30)
        max_chars = kwargs.get("max_chars")
        retry_count = kwargs.get("retry_count", 3)

        if not url:
            return self._failure("url cannot be empty")

        # Validate URL format
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

        # Execute with retry
        for attempt in range(retry_count):
            try:
                html = await self._fetch_html(url, timeout)
                result = await handler(html, url, max_chars)
                return result
            except Exception as e:
                if attempt < retry_count - 1:
                    # Exponential backoff
                    wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"Scraping failed (attempt {attempt + 1}/{retry_count}), retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    return self._failure(str(e), "Web scraping failed")
        
        # All retries failed (shouldn't reach here, but for type safety)
        return self._failure("Scraping failed", "Web scraping failed")

    async def _fetch_html(self, url: str, timeout: int = 30) -> str:
        """Fetch page HTML"""
        import httpx
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
        }
        
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    async def _extract_text(
        self, 
        html: str, 
        url: str, 
        max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract plain text (intelligent content extraction)
        
        Uses intelligent algorithm to identify main content, filtering:
        - Navigation bars
        - Sidebars
        - Ads
        - Footers
        - Scripts and styles
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "lxml")
        
        # Remove irrelevant elements
        for tag in soup(["script", "style", "meta", "noscript", "iframe", "svg"]):
            tag.decompose()
        
        # Remove common navigation, sidebar, ad elements
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
        
        # Try to find main content area
        main_content = None
        for selector in ["article", "main", ".content", ".article", ".post", "#content", "#article"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # If no main area found, use entire body
        if not main_content:
            main_content = soup.body if soup.body else soup
        
        # Extract title
        title = ""
        title_tag = soup.title
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        
        # Also try to get title from h1
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(strip=True) or title
        
        # Extract text
        text = main_content.get_text(separator="\n", strip=True)
        
        # Clean extra blank lines
        lines = [line for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        
        # Character limit
        if max_chars and len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars] + "\n...[content truncated]"
        
        return self._success(
            {
                "text": clean_text,
                "title": title,
                "url": url,
                "content_length": len(clean_text),
            },
            "Text extraction successful"
        )

    async def _extract_markdown(
        self, 
        html: str, 
        url: str, 
        max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract Markdown format (preserve structure)
        
        Convert HTML to Markdown format, preserving:
        - Heading levels
        - Lists
        - Links
        - Code blocks
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "lxml")
        
        # Remove irrelevant elements
        for tag in soup(["script", "style", "meta", "noscript", "iframe", "svg"]):
            tag.decompose()
        
        # Remove navigation, sidebar, ads
        for selector in ["nav", "header", "footer", "aside", ".nav", ".sidebar", ".ad"]:
            for tag in soup.select(selector):
                tag.decompose()
        
        # Find main content
        main_content = None
        for selector in ["article", "main", ".content", ".article", ".post"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.body if soup.body else soup
        
        # Convert to Markdown
        markdown = self._html_to_markdown(main_content)
        
        # Extract title
        title = ""
        title_tag = soup.title
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        
        # Character limit
        if max_chars and len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n\n...[content truncated]"
        
        return self._success(
            {
                "text": markdown,
                "title": title,
                "url": url,
                "content_length": len(markdown),
            },
            "Markdown extraction successful"
        )

    def _html_to_markdown(self, element) -> str:
        """Convert HTML element to Markdown"""
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
                    text = child.get_text(strip=True)
                    result.append(f"\n{'#' * level} {text}\n")
                
                elif tag_name == "p":
                    text = self._html_to_markdown(child)
                    result.append(f"\n{text}\n")
                
                elif tag_name in ["ul", "ol"]:
                    items = child.find_all("li", recursive=False)
                    for i, item in enumerate(items):
                        text = item.get_text(strip=True)
                        prefix = f"{i + 1}." if tag_name == "ol" else "-"
                        result.append(f"{prefix} {text}")
                    result.append("")
                
                elif tag_name == "li":
                    text = child.get_text(strip=True)
                    result.append(f"- {text}")
                
                elif tag_name == "a":
                    text = child.get_text(strip=True)
                    href = child.get("href", "")
                    if href:
                        result.append(f"[{text}]({href})")
                    else:
                        result.append(text)
                
                elif tag_name in ["strong", "b"]:
                    text = child.get_text(strip=True)
                    result.append(f"**{text}**")
                
                elif tag_name in ["em", "i"]:
                    text = child.get_text(strip=True)
                    result.append(f"*{text}*")
                
                elif tag_name == "code":
                    text = child.get_text()
                    if child.parent and child.parent.name == "pre":
                        result.append(f"```\n{text}\n```")
                    else:
                        result.append(f"`{text}`")
                
                elif tag_name == "pre":
                    code = child.get_text()
                    result.append(f"\n```\n{code}\n```\n")
                
                elif tag_name == "blockquote":
                    text = child.get_text(strip=True)
                    lines = text.split("\n")
                    for line in lines:
                        result.append(f"> {line}")
                    result.append("")
                
                elif tag_name == "br":
                    result.append("\n")
                
                elif tag_name in ["div", "span", "section", "article"]:
                    result.append(self._html_to_markdown(child))
                
                else:
                    # Other tags, recursively process children
                    result.append(self._html_to_markdown(child))
        
        return "".join(result)

    async def _extract_tables(self, html: str, url: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        """Extract table data"""
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

        return self._success(
            {"tables": tables, "count": len(tables), "url": url},
            f"Extracted {len(tables)} tables"
        )

    async def _extract_links(self, html: str, url: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        """Extract all links"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Complete relative links
            if href.startswith("/") or not href.startswith("http"):
                href = urljoin(url, href)
            text = a.get_text(strip=True)
            links.append({"url": href, "text": text})

        return self._success(
            {"links": links, "count": len(links), "url": url},
            f"Extracted {len(links)} links"
        )


# Alias, maintain backward compatibility
WebFetchSkill = WebScraperSkill
