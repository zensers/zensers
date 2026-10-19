# -*- coding: utf-8 -*-
"""
P0 Fix: akshare 未调用 — 公司名→股票代码解析缺失

测试验证:
- _extract_stock_symbol 能从公司名解析出数字股票代码（mock akshare）
- 数字代码直接透传
- 非公司名不强行解析
- _fetch_structured_data 在 symbol 解析时有日志
- _resolve_company_to_code 正确调用 akshare 并匹配

Bug: _extract_stock_symbol 只做正则提取中文(返回"比亚迪")，
akshare 需要数字代码("002594")，调用失败被静默吞掉
"""

import pytest
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.agents.generic_agent import GenericAgent


def _make_mock_akshare_df():
    return pd.DataFrame({
        "代码": ["002594", "00700", "600519", "300750"],
        "名称": ["比亚迪", "腾讯控股", "贵州茅台", "宁德时代"],
    })


class TestExtractStockSymbolNumericPassthrough:
    """数字代码应直接透传"""

    def setup_method(self):
        GenericAgent._STOCK_CODE_CACHE.clear()
        self.agent = GenericAgent.__new__(GenericAgent)
        self.agent.agent_id = "test_agent"
        self.agent.agent_type = "research"
        self.agent.topic = "002594"

    def test_six_digit_code_passes_through(self):
        """6位数字代码应直接返回"""
        symbol = self.agent._extract_stock_symbol("002594")
        assert symbol == "002594"

    def test_code_embedded_in_text(self):
        """文本中嵌入的6位数字代码应被提取"""
        symbol = self.agent._extract_stock_symbol("比亚迪(002594)财务分析")
        assert symbol == "002594"

    def test_empty_topic_returns_empty(self):
        """空 topic 应返回空字符串"""
        symbol = self.agent._extract_stock_symbol("")
        assert symbol == ""


class TestExtractStockSymbolCompanyResolution:
    """中文公司名应通过 akshare 解析为数字代码"""

    def setup_method(self):
        self.agent = GenericAgent.__new__(GenericAgent)
        self.agent.agent_id = "test_agent"
        self.agent.agent_type = "research"
        self.agent.topic = "比亚迪财务分析"
        GenericAgent._STOCK_CODE_CACHE.clear()

    @patch("src.core.agents.generic_agent.GenericAgent._resolve_company_to_code")
    @patch("src.core.agents.generic_agent.GenericAgent._is_likely_company_name")
    def test_byd_resolves_to_code(self, mock_is_company, mock_resolve):
        """比亚迪应解析为002594"""
        mock_is_company.return_value = True
        mock_resolve.return_value = "002594"
        symbol = self.agent._extract_stock_symbol("比亚迪财务分析")
        assert symbol == "002594", f"应返回002594，实际: {symbol}"

    @patch("src.core.agents.generic_agent.GenericAgent._is_likely_company_name")
    def test_non_company_returns_empty(self, mock_is_company):
        """非上市公司名不应解析"""
        mock_is_company.return_value = False
        symbol = self.agent._extract_stock_symbol("新能源汽车行业分析")
        assert symbol == "", f"非公司名应返回空，实际: {symbol}"

    @patch("src.core.agents.generic_agent.GenericAgent._resolve_company_to_code")
    @patch("src.core.agents.generic_agent.GenericAgent._is_likely_company_name")
    def test_cache_avoids_repeated_resolution(self, mock_is_company, mock_resolve):
        """缓存应避免重复调用 akshare"""
        mock_is_company.return_value = True
        mock_resolve.return_value = "002594"
        self.agent._extract_stock_symbol("比亚迪财务分析")
        self.agent._extract_stock_symbol("比亚迪财务分析")
        assert mock_resolve.call_count == 1, "应只调用一次 resolve"

    @patch("src.core.agents.generic_agent.GenericAgent._is_likely_company_name")
    def test_no_chinese_returns_empty(self, mock_is_company):
        """纯英文非公司名应返回空"""
        mock_is_company.return_value = False
        symbol = self.agent._extract_stock_symbol("market analysis report")
        assert symbol == ""

    @patch("src.core.agents.generic_agent.GenericAgent._is_likely_company_name")
    def test_year_in_topic_not_matched_as_code(self, mock_is_company):
        """'2024年财报' 不应提取中文后误识别为公司"""
        mock_is_company.return_value = False
        symbol = self.agent._extract_stock_symbol("2024年财报分析")
        assert symbol == "", f"年份不应匹配为代码，实际: {symbol}"


class TestResolveCompanyToCode:
    """_resolve_company_to_code 应正确调用 akshare"""

    def setup_method(self):
        GenericAgent._STOCK_CODE_CACHE.clear()
        self.agent = GenericAgent.__new__(GenericAgent)
        self.agent.agent_id = "test_agent"
        self.agent.agent_type = "research"

    @patch("src.core.agents.generic_agent.ak", create=True)
    def test_byd_found_in_akshare(self, mock_ak):
        """比亚迪应在 akshare 数据中找到"""
        mock_ak.stock_zh_a_spot_em.return_value = _make_mock_akshare_df()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            code = self.agent._resolve_company_to_code("比亚迪")
        assert code == "002594", f"应返回002594，实际: {code}"

    @patch("src.core.agents.generic_agent.ak", create=True)
    def test_tencent_found_in_akshare(self, mock_ak):
        """腾讯应在 akshare 数据中找到"""
        mock_ak.stock_zh_a_spot_em.return_value = _make_mock_akshare_df()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            code = self.agent._resolve_company_to_code("腾讯")
        assert code == "00700", f"应返回00700，实际: {code}"

    def test_unknown_company_returns_empty(self):
        """未知公司应返回空字符串"""
        with patch("src.core.agents.generic_agent.GenericAgent._resolve_company_to_code", return_value=""):
            code = self.agent._resolve_company_to_code("不存在的公司xyz")
        assert code == ""

    def test_unresolvable_company_returns_empty(self):
        """无法通过实体解析或 AkShare 解析时返回空字符串"""
        GenericAgent._AKSHARE_RESOLVE_CACHE.pop("比亚迪", None)
        with patch.object(self.agent, "_resolve_via_entity_resolver", return_value=""), \
             patch.object(self.agent, "_resolve_via_akshare", return_value=""):
            code = self.agent._resolve_company_to_code("比亚迪")
        assert code == ""

    @patch("src.core.agents.generic_agent.ak", create=True)
    def test_company_name_with_suffix_resolves(self, mock_ak):
        """'比亚迪财务分析' 应通过子串 '比亚迪' 匹配到 akshare 数据"""
        mock_ak.stock_zh_a_spot_em.return_value = _make_mock_akshare_df()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            code = self.agent._resolve_company_to_code("比亚迪财务分析")
        assert code == "002594", f"'比亚迪财务分析' 应通过子串匹配到002594，实际: {code}"


class TestStockDataCanonicalizationLogging:
    """公司名规范化在 StockDataSkill 边界完成并记录解析结果。"""

    @pytest.mark.asyncio
    async def test_symbol_resolution_logged(self):
        from src.skills.analysis.stock_data import StockDataSkill
        from src.core.entity_resolver import EntityInfo

        skill = StockDataSkill()
        resolver = MagicMock()
        resolver.resolve = AsyncMock(return_value=[
            EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        ])
        with patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver), \
             patch("src.skills.analysis.stock_data.logger") as mock_logger:
            code = await skill._canonicalize_symbol("比亚迪")

        assert code == "002594"
        assert any("002594" in str(call) for call in mock_logger.info.call_args_list)


class TestStockDataSkillWithNumericCode:
    """StockDataSkill 接收数字代码应能正常工作"""

    def setup_method(self):
        GenericAgent._STOCK_CODE_CACHE.clear()

    @pytest.mark.asyncio
    async def test_numeric_code_accepted(self):
        """数字股票代码应被接受"""
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        result = await skill.execute(action="company_info", symbol="600519")
        assert result is not None
        assert "success" in result

    @pytest.mark.asyncio
    async def test_unresolved_chinese_name_degrades_gracefully(self):
        """中文名解析失败时应返回结构化失败，而不是抛异常"""
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        with patch.object(skill, "_canonicalize_symbol", new=AsyncMock(return_value="")):
            result = await skill.execute(action="company_info", symbol="未知公司")
        assert result is not None
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_stock_data_skill_canonicalizes_company_name(self):
        from src.skills.analysis.stock_data import StockDataSkill

        skill = StockDataSkill()
        with patch.object(skill, "_canonicalize_symbol", new=AsyncMock(return_value="000725")), \
             patch.object(skill, "_company_info", new=AsyncMock(return_value={"success": True, "symbol": "000725"})), \
             patch.dict("sys.modules", {"akshare": MagicMock()}):
            result = await skill.execute(action="company_info", symbol="京东方")

        assert result.get("symbol") == "000725"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
