"""
WebScraperSkill tests — TDD pattern with mock fetch layer.

Tests cover:
1. All existing extraction modes (text, markdown, tables, links) — regression
2. URL classification (static / js / pdf / baidu_redirect)
3. PDF content extraction via pdfplumber
4. Baidu redirect URL resolution
5. Fallback: httpx → Playwright → error
6. Error handling and edge cases
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock


SAMPLE_HTML = """
<html>
<head><title>测试页面</title></head>
<body>
    <h1>新能源汽车市场分析</h1>
    <p>2024年中国新能源汽车销量突破900万辆，同比增长35%。</p>
    <table>
        <tr><th>品牌</th><th>销量</th></tr>
        <tr><td>比亚迪</td><td>300万辆</td></tr>
        <tr><td>特斯拉</td><td>180万辆</td></tr>
    </table>
    <script>var x = 1;</script>
</body>
</html>
"""

HTML_WITH_LINKS = """
<html><body>
    <a href="https://example.com/page1">页面1</a>
    <a href="https://example.com/page2">页面2</a>
    <a href="/relative/page">相对链接</a>
</body></html>
"""


@pytest.fixture
def skill():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    return WebScraperSkill(SkillConfig(name="web_scraper", version="1.0.0"))


class TestWebScraperContract:
    """Interface contract tests — these must never break."""

    def test_name(self, skill):
        assert skill.name == "web_scraper"

    def test_description(self, skill):
        assert isinstance(skill.description, str)

    @pytest.mark.asyncio
    async def test_empty_url_rejected(self, skill):
        result = await skill.execute(url="", action="extract_text")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill):
        result = await skill.execute(url="https://example.com", action="magic")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_fetch_error_returns_failure(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.side_effect = Exception("network error")
            result = await skill.execute(url="https://unreachable.com", action="extract_text")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_success_response_has_required_fields(self, skill):
        """Every successful response must include success, text/message."""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = SAMPLE_HTML
            result = await skill.execute(url="https://example.com", action="extract_text")
        assert result["success"] is True
        assert "text" in result
        assert "title" in result
        assert "url" in result


class TestWebScraperExtraction:
    """Content extraction modes — mocked fetch layer."""

    @pytest.mark.asyncio
    async def test_extract_text(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = SAMPLE_HTML
            result = await skill.execute(url="https://example.com/report", action="extract_text")
        assert result["success"] is True
        assert "新能源汽车市场分析" in result["text"]
        assert "2024年" in result["text"]
        assert "var x = 1" not in result["text"]

    @pytest.mark.asyncio
    async def test_extract_title(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = SAMPLE_HTML
            result = await skill.execute(url="https://example.com", action="extract_text")
        assert result["success"] is True
        assert result["title"] == "新能源汽车市场分析"

    @pytest.mark.asyncio
    async def test_extract_tables(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = SAMPLE_HTML
            result = await skill.execute(url="https://example.com", action="extract_tables")
        assert result["success"] is True
        assert "tables" in result
        assert len(result["tables"]) >= 1
        assert any("比亚迪" in str(row) for row in result["tables"][0])

    @pytest.mark.asyncio
    async def test_extract_links(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = HTML_WITH_LINKS
            result = await skill.execute(url="https://example.com", action="extract_links")
        assert result["success"] is True
        assert len(result["links"]) >= 2

    @pytest.mark.asyncio
    async def test_invalid_html_does_not_crash(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = "<invalid><<broken>html"
            result = await skill.execute(url="https://example.com", action="extract_text")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_max_chars_respected(self, skill):
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = SAMPLE_HTML
            result_no_limit = await skill.execute(url="https://example.com", action="extract_text")
            result_limited = await skill.execute(url="https://example.com", action="extract_text", max_chars=10)
        assert result_limited["success"] is True
        assert "[content truncated]" in result_limited["text"]
        assert len(result_limited["text"]) < len(result_no_limit["text"])


class TestWebScraperUrlClassification:
    """URL type routing."""

    def test_classify_static_url(self, skill):
        assert skill._classify_url("https://example.com/article") == "static"
        assert skill._classify_url("https://finance.sina.com.cn/stock/123.html") == "static"

    def test_classify_js_url(self, skill):
        js_domains = ["eastmoney.com", "10jqka.com.cn", "xueqiu.com",
                      "caifuhao.eastmoney.com", "sohu.com"]
        for domain in js_domains:
            assert skill._classify_url(f"https://{domain}/article") == "js"

    def test_classify_pdf_url(self, skill):
        assert skill._classify_url("https://static.cninfo.com.cn/report.pdf") == "pdf"
        assert skill._classify_url("https://example.com/file.pdf?download=1") == "pdf"

    def test_classify_baidu_redirect(self, skill):
        assert skill._classify_url("http://www.baidu.com/link?url=NhxGkTS80e4") == "baidu_redirect"

    def test_classify_unknown_domain_falls_back_static(self, skill):
        assert skill._classify_url("https://unknown-site-123.com/page") == "static"


class TestWebScraperBaiduRedirect:
    """Baidu redirect URL resolution."""

    @pytest.mark.asyncio
    async def test_resolve_baidu_redirect(self, skill):
        """Baidu redirect URL should extract real URL from baidu page."""
        baidu_redirect_page = """
        <html><head><meta http-equiv="refresh" content="0;url=https://real-target.com/article?id=123">
        </head><body></body></html>
        """
        real_url = await skill._resolve_baidu_url(
            "http://www.baidu.com/link?url=abc123",
            fetch_mock=AsyncMock(return_value=baidu_redirect_page),
        )
        assert real_url == "https://real-target.com/article?id=123"

    @pytest.mark.asyncio
    async def test_resolve_baidu_url_no_redirect_fallback(self, skill):
        """If no redirect found in baidu page, return the original URL."""
        no_redirect = "<html><head><title>百度安全验证</title></head><body></body></html>"
        real_url = await skill._resolve_baidu_url(
            "http://www.baidu.com/link?url=abc",
            fetch_mock=AsyncMock(return_value=no_redirect),
        )
        assert real_url == "http://www.baidu.com/link?url=abc"

    @pytest.mark.asyncio
    async def test_baidu_redirect_integration(self, skill):
        """Baidu redirect URLs should flow through the full execute pipeline."""
        with patch.object(skill, "_classify_url", return_value="baidu_redirect"):
            with patch.object(skill, "_resolve_baidu_url", new_callable=AsyncMock) as resolve:
                resolve.return_value = "https://real-target.com/article"
                with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as fetch:
                    fetch.return_value = SAMPLE_HTML
                    result = await skill.execute(
                        url="http://www.baidu.com/link?url=abc123",
                        action="extract_text",
                    )
        assert result["success"] is True
        resolve.assert_called_once()
        assert "新能源汽车" in result["text"]


class TestWebScraperPdfExtraction:
    """PDF content extraction."""

    @pytest.mark.asyncio
    async def test_pdf_url_routed_correctly(self, skill):
        """PDF URLs should use _fetch_pdf, not _fetch_html."""
        with patch.object(skill, "_classify_url", return_value="pdf"):
            with patch.object(skill, "_fetch_pdf", new_callable=AsyncMock) as pdf_mock:
                pdf_mock.return_value = ("2024年报摘要\n营收6770亿元\n净利润326.5亿元", "比亚迪2024年报")
                result = await skill.execute(
                    url="https://static.cninfo.com.cn/report.pdf",
                    action="extract_text",
                )
        assert result["success"] is True
        assert "6770亿元" in result["text"]
        assert result["title"] == "比亚迪2024年报"
        pdf_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_fetch_error(self, skill):
        """PDF fetch failure should return error."""
        with patch.object(skill, "_classify_url", return_value="pdf"):
            with patch.object(skill, "_fetch_pdf", new_callable=AsyncMock) as pdf_mock:
                pdf_mock.side_effect = Exception("PDF download failed")
                result = await skill.execute(
                    url="https://example.com/report.pdf",
                    action="extract_text",
                )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_pdf_empty_content(self, skill):
        """PDF with no extractable text should still succeed with empty text."""
        with patch.object(skill, "_classify_url", return_value="pdf"):
            with patch.object(skill, "_fetch_pdf", new_callable=AsyncMock) as pdf_mock:
                pdf_mock.return_value = ("", "Untitled")
                result = await skill.execute(
                    url="https://example.com/scanned.pdf",
                    action="extract_text",
                )
        assert result["success"] is True
        assert result["content_length"] == 0


class TestWebScraperFallbackChain:
    """Fallback: Scrapling → Playwright → error."""

    @pytest.mark.asyncio
    async def test_js_url_uses_playwright(self, skill):
        """JS-classified URLs should fall through to Playwright."""
        with patch.object(skill, "_classify_url", return_value="js"):
            with patch.object(skill, "_fetch_with_playwright", new_callable=AsyncMock) as pw_mock:
                pw_mock.return_value = ("<html><body><p>JS rendered content</p></body></html>", "JS Page")
                with patch.object(skill, "_extract_text") as extract:
                    extract.return_value = {"success": True, "text": "JS rendered content", "title": "JS Page"}
                    result = await skill.execute(
                        url="https://xueqiu.com/12345",
                        action="extract_text",
                    )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_playwright_fallback_to_error(self, skill):
        """When both Scrapling and Playwright fail, return error."""
        with patch.object(skill, "_classify_url", return_value="js"):
            with patch.object(skill, "_fetch_with_playwright", new_callable=AsyncMock) as pw_mock:
                pw_mock.side_effect = Exception("Playwright failed")
                result = await skill.execute(
                    url="https://xueqiu.com/12345",
                    action="extract_text",
                )
        assert result["success"] is False


class TestWebScraperMarkdown:
    """Markdown extraction mode."""

    @pytest.mark.asyncio
    async def test_extract_markdown_headers(self, skill):
        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = html
            result = await skill.execute(url="https://example.com", action="extract_markdown")
        assert result["success"] is True
        assert "# Title" in result["text"]
        assert "Content" in result["text"]

    @pytest.mark.asyncio
    async def test_extract_markdown_list(self, skill):
        html = "<html><body><ul><li>A</li><li>B</li></ul></body></html>"
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as m:
            m.return_value = html
            result = await skill.execute(url="https://example.com", action="extract_markdown")
        assert result["success"] is True
        assert "- A" in result["text"]
        assert "- B" in result["text"]
