"""
WebScraperSkill 测试 - TDD模式（Mock HTML内容）
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestWebScraperSkill:
    """测试网页内容抓取 Skill"""

    @pytest.fixture
    def skill(self):
        from src.skills.web_scraper_skill import WebScraperSkill
        from src.skills.base import SkillConfig
        return WebScraperSkill(SkillConfig(name="web_scraper", version="1.0.0"))

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

    def test_scraper_init(self, skill):
        """测试初始化"""
        assert skill.name == "web_scraper"
        assert skill.description is not None

    @pytest.mark.asyncio
    async def test_extract_text_from_html(self, skill):
        """测试从 HTML 提取纯文本"""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = self.SAMPLE_HTML
            result = await skill.execute(
                url="https://example.com/report",
                action="extract_text"
            )

        assert result["success"] is True
        assert "新能源汽车市场分析" in result["text"]
        assert "2024年" in result["text"]
        # script 内容应被过滤
        assert "var x = 1" not in result["text"]

    @pytest.mark.asyncio
    async def test_extract_title(self, skill):
        """测试提取页面标题"""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = self.SAMPLE_HTML
            result = await skill.execute(
                url="https://example.com",
                action="extract_text"
            )

        assert result["success"] is True
        assert result.get("title") == "测试页面"

    @pytest.mark.asyncio
    async def test_extract_tables(self, skill):
        """测试提取表格数据"""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = self.SAMPLE_HTML
            result = await skill.execute(
                url="https://example.com",
                action="extract_tables"
            )

        assert result["success"] is True
        assert "tables" in result
        assert len(result["tables"]) >= 1
        # 验证表格数据
        table = result["tables"][0]
        assert any("比亚迪" in str(row) for row in table)

    @pytest.mark.asyncio
    async def test_handle_invalid_html(self, skill):
        """测试处理无效 HTML"""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "<invalid><<broken>html"
            result = await skill.execute(
                url="https://example.com",
                action="extract_text"
            )

        # 即使HTML损坏也应尽力返回内容，不崩溃
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fetch_error_handling(self, skill):
        """测试获取页面失败"""
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("网络连接失败")
            result = await skill.execute(
                url="https://unreachable.com",
                action="extract_text"
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill):
        """测试未知动作"""
        result = await skill.execute(url="https://example.com", action="magic")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_empty_url_rejected(self, skill):
        """测试空 URL 被拒绝"""
        result = await skill.execute(url="", action="extract_text")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_extract_links(self, skill):
        """测试提取链接"""
        html_with_links = """
        <html><body>
            <a href="https://example.com/page1">页面1</a>
            <a href="https://example.com/page2">页面2</a>
            <a href="/relative/page">相对链接</a>
        </body></html>
        """
        with patch.object(skill, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html_with_links
            result = await skill.execute(
                url="https://example.com",
                action="extract_links"
            )

        assert result["success"] is True
        assert "links" in result
        assert len(result["links"]) >= 2
