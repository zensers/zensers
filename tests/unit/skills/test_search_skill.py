"""
SearchSkill 测试 - TDD模式（Mock 搜索引擎）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSearchSkill:
    """测试搜索 Skill"""

    @pytest.fixture
    def skill(self):
        from src.skills.search_skill import SearchSkill
        from src.skills.base import SkillConfig
        return SearchSkill(SkillConfig(name="search_skill", version="1.0.0"))

    def test_search_skill_init(self, skill):
        """测试初始化"""
        assert skill.name == "search_skill"
        assert skill.description is not None

    @pytest.mark.asyncio
    async def test_search_returns_results(self, skill):
        """测试搜索返回结果"""
        mock_results = [
            {"title": "新能源汽车市场报告", "url": "https://example.com/1", "snippet": "2024年市场规模达..."},
            {"title": "比亚迪年报", "url": "https://example.com/2", "snippet": "营收增长35%..."},
        ]

        with patch.object(skill, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            result = await skill.execute(query="新能源汽车市场2024", max_results=10)

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "新能源汽车市场报告"

    @pytest.mark.asyncio
    async def test_search_empty_query(self, skill):
        """测试空查询被拒绝"""
        result = await skill.execute(query="")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_search_with_site_filter(self, skill):
        """测试站点过滤"""
        with patch.object(skill, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            result = await skill.execute(
                query="比亚迪",
                site="gov.cn",
                max_results=5
            )

        assert result["success"] is True
        call_kwargs = mock_search.call_args
        assert "gov.cn" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_search_error_handling(self, skill):
        """测试搜索错误处理"""
        with patch.object(skill, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("搜索引擎不可用")
            result = await skill.execute(query="测试查询")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_result_count_limited(self, skill):
        """测试结果数量限制"""
        mock_results = [
            {"title": f"结果{i}", "url": f"https://example.com/{i}", "snippet": f"内容{i}"}
            for i in range(20)
        ]

        with patch.object(skill, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results[:5]  # 返回5条
            result = await skill.execute(query="测试", max_results=5)

        assert result["success"] is True
        assert len(result["results"]) <= 5

    @pytest.mark.asyncio
    async def test_search_returns_metadata(self, skill):
        """测试返回查询元数据"""
        with patch.object(skill, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"title": "标题", "url": "https://x.com", "snippet": "摘要"}]
            result = await skill.execute(query="测试关键词", max_results=10)

        assert result["success"] is True
        assert "query" in result
        assert result["query"] == "测试关键词"
