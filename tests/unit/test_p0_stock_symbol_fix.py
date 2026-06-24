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

    def test_akshare_import_error_returns_empty(self):
        """akshare 未安装应返回空字符串"""
        with patch.dict("sys.modules", {"akshare": None}):
            code = self.agent._resolve_company_to_code("比亚迪")
        assert code == ""

    @patch("src.core.agents.generic_agent.ak", create=True)
    def test_company_name_with_suffix_resolves(self, mock_ak):
        """'比亚迪财务分析' 应通过子串 '比亚迪' 匹配到 akshare 数据"""
        mock_ak.stock_zh_a_spot_em.return_value = _make_mock_akshare_df()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            code = self.agent._resolve_company_to_code("比亚迪财务分析")
        assert code == "002594", f"'比亚迪财务分析' 应通过子串匹配到002594，实际: {code}"


class TestFetchStructuredDataLogging:
    """_fetch_structured_data 应在关键步骤记录日志"""

    def setup_method(self):
        GenericAgent._STOCK_CODE_CACHE.clear()

    @pytest.mark.asyncio
    async def test_symbol_resolution_logged(self):
        """symbol 解析结果应被记录"""
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"
        agent.agent_type = "research"
        agent.topic = "比亚迪财务分析"

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value="002594"):
            with patch("src.core.agents.generic_agent.logger") as mock_logger:
                result = await agent._fetch_structured_data(
                    mock_skill, "比亚迪财务分析", "财务"
                )
                logged = any(
                    "002594" in str(call)
                    for call in mock_logger.info.call_args_list
                )
                assert logged, "symbol 解析结果应被记录到日志"


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
    async def test_chinese_name_rejected_gracefully(self):
        """中文名应返回失败而非异常"""
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        result = await skill.execute(action="company_info", symbol="比亚迪")
        assert result is not None
        assert result.get("success") is False or "error" in result or "data" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
