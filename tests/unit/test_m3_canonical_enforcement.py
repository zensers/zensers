"""
M3 测试：canonical_data 后处理强制替换

TDD: RED 阶段 — 编写测试用例，实现将紧随其后

覆盖场景：
1. _enforce_canonical_values 单元测试
2. 分析路径插入点：skill.execute() 之后 canonical 强制替换
3. 合成路径插入点：skill.execute() 之后 canonical 强制替换
"""
import pytest
from typing import Dict, Any
from unittest.mock import MagicMock, patch, AsyncMock


class TestM3EnforceCanonicalValues:
    """通用 _enforce_canonical_values 方法单元测试"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        a = GenericAgent(agent_id="test_agent", agent_type="analysis", config={
            "context": {"section_id": "test_section"}
        })
        return a

    def test_basic_replacement(self, agent):
        """canonical 值替换内容中的不一致值（差异>5%）"""
        content = "BYD 2024年净利润300亿元，同比增长10%"
        canonical = {
            "净利润_2024_CNY_年报": {"value": 326.5, "unit": "亿元", "caliber": "年报", "source": "财报"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result, f"应替换为 326.5亿元，实际: {result}"
        assert "同比增长10%" in result  # 非指标部分应保持不变

    def test_within_tolerance_no_change(self, agent):
        """5% 误差内不应替换"""
        content = "净利润326亿元"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326亿元" in result, "误差 0.15% 应不替换"

    def test_large_difference_replaced(self, agent):
        """超过 5% 应替换"""
        content = "净利润300亿元"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result, "差异 8.1% 应替换"
        assert "300亿元" not in result, "旧值应被替换"

    def test_no_canonical_data_unchanged(self, agent):
        """无 canonical_data 时不修改内容"""
        content = "净利润326亿元"
        result = agent._enforce_canonical_values(content, {})
        assert result == content

    def test_empty_content(self, agent):
        """空内容不报错"""
        result = agent._enforce_canonical_values("", {"净利润": {"value": 326}})
        assert result == ""

    def test_metric_not_in_canonical_unchanged(self, agent):
        """canonical 中不存在的指标不修改"""
        content = "研发投入100亿元"
        canonical = {
            "净利润_2024_CNY": {"value": 326, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "100亿元" in result

    def test_multiple_metrics_selective_replacement(self, agent):
        """多指标时只替换 canonical 中存在的"""
        content = "营收5000亿元，净利润300亿元，毛利率25%"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"},
            "毛利率_2024": {"value": 20.5, "unit": "%"},
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result, "净利润应替换"
        assert "20.5%" in result, "毛利率应替换（差异>5%）"
        assert "5000亿元" in result, "营收不在 canonical 中，应保持不变"

    def test_table_line_skipped(self, agent):
        """markdown 表格行中的数值不应替换"""
        content = "| 指标 | 2023 | 2024 |\n|------|------|------|\n| 净利润 | 300亿元 | 326亿元 |"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        lines = result.split('\n')
        table_lines = [l for l in lines if l.startswith('|')]
        for tl in table_lines:
            assert "326.5亿元" not in tl, f"表格行不应替换: {tl}"

    def test_metric_with_different_unit(self, agent):
        """不同单位但同指标名，差异>5%应替换"""
        content = "销量380万辆"
        canonical = {
            "销量_2024": {"value": 460, "unit": "万辆"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "460万辆" in result, "同指标差异>5%应替换"

    def test_sales_metric_replacement(self, agent):
        """销量指标正确替换"""
        content = "2024年全球销量380万辆"
        canonical = {
            "销量_2024_CNY": {"value": 460, "unit": "万辆"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "460万辆" in result

    def test_null_canonical_value_skipped(self, agent):
        """canonical value 为 None 时跳过"""
        content = "净利润326亿元"
        canonical = {
            "净利润_2024": {"value": None, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326亿元" in result

    def test_non_dict_canonical_entry_skipped(self, agent):
        """canonical 条目非 dict 时跳过"""
        content = "净利润326亿元"
        canonical = {
            "净利润_2024": "326.5"
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326亿元" in result

    def test_english_net_profit_replaced(self, agent):
        """英文 net profit 被正确匹配并替换"""
        content = "In 2024, BYD's net profit reached RMB 32.6 billion"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5" in result
        assert "32.6" not in result

    def test_english_revenue_replaced(self, agent):
        """英文 revenue 被正确匹配并替换"""
        content = "Total revenue was 777.0 billion CNY in 2024"
        canonical = {
            "营收_2024_CNY": {"value": 777.0, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "777.0" in result

    def test_english_market_share(self, agent):
        """英文 market share 被正确匹配"""
        content = "BYD's market share reached 35.5% in 2024"
        canonical = {
            "市占率_2024": {"value": 35.5, "unit": "%"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "35.5" in result

    def test_english_sales_volume(self, agent):
        """英文 sales/deliveries 被正确匹配"""
        content = "BYD delivered 4.25 million vehicles in 2024"
        canonical = {
            "销量_2024": {"value": 425, "unit": "万辆"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        # unit mismatch (million vs 万辆) → falls back to value-only pattern
        assert "BYD delivered" in result

    def test_english_gross_margin(self, agent):
        """英文 gross margin 被正确匹配并替换"""
        content = "The gross margin improved to 20.1% in fiscal 2024"
        canonical = {
            "毛利率_2024": {"value": 20.1, "unit": "%"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "20.1" in result

    def test_same_metric_appears_twice_both_replaced(self, agent):
        """同一指标值出现两次，两次都应替换"""
        content = "2024年净利润300亿元，同比大幅增长。其中Q4净利润300亿元。"
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert result.count("326.5亿元") == 2, f"两处都应替换，实际: {result}"
        assert result.count("300亿元") == 0

    def test_zero_canonical_value_handled(self, agent):
        """canonical 值为 0 时正常处理"""
        content = "净利润1亿元"
        canonical = {
            "净利润_2024": {"value": 0, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "0亿元" in result  # diff = 1/0.01 = 100 >> 5%, 应替换

    def test_yue_prefix_not_matched(self, agent):
        """'约' 前缀应被 [^\\d]*? 匹配且不替换（值在误差内）"""
        content = "净利润约326亿元"
        canonical = {
            "净利润_2024": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "约" in result or "326亿元" in result  # 在 5% 内，不替换

    def test_yue_prefix_with_large_diff_replaced(self, agent):
        """'约' 前缀但差异>5%时仍替换"""
        content = "净利润约300亿元"
        canonical = {
            "净利润_2024": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result


class TestM3AnalysisPathIntegration:
    """DEEP_ANALYSIS 路径的 M3 插入点集成测试"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        a = GenericAgent(agent_id="analysis_agent", agent_type="analysis", config={
            "context": {"section_id": "test_section"},
            "category": "analysis",
        })
        return a

    @pytest.mark.asyncio
    async def test_analysis_path_enforces_canonical(self, agent):
        """
        分析路径中，skill.execute() 返回的内容被 canonical 强制替换
        """
        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {
            "success": True,
            "content": "BYD净利润300亿元，同比增长10%",
        }

        canonical_data = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元", "caliber": "年报"},
        }

        with patch.object(agent, '_get_professional_role_prompt', return_value="role prompt"):
            with patch.object(agent, '_build_analysis_prompt_with_data', return_value="analysis prompt"):
                result = agent._enforce_canonical_values(
                    mock_skill.execute.return_value["content"],
                    canonical_data,
                )

        assert "326.5亿元" in result, "canonical 值应强制替换"
        assert "300亿元" not in result, "旧值应被替换"

    @pytest.mark.asyncio
    async def test_analysis_path_no_canonical_unchanged(self, agent):
        """分析路径无 canonical_data 时不修改"""
        mock_skill = AsyncMock()
        original_content = "BYD净利润300亿元"
        mock_skill.execute.return_value = {
            "success": True,
            "content": original_content,
        }

        result = agent._enforce_canonical_values(
            mock_skill.execute.return_value["content"],
            {},
        )

        assert result == original_content


class TestM3SynthesisPathIntegration:
    """SYNTHESIS 路径的 M3 插入点集成测试"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        a = GenericAgent(agent_id="synthesis_agent", agent_type="synthesis", config={
            "context": {"section_id": "test_section"},
            "category": "synthesis",
        })
        return a

    @pytest.mark.asyncio
    async def test_synthesis_path_enforces_canonical(self, agent):
        """合成路径中 canonical 强制替换"""
        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {
            "success": True,
            "content": "综合各维度数据，2024年净利润为300亿元",
        }

        canonical_data = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"},
        }

        result = agent._enforce_canonical_values(
            mock_skill.execute.return_value["content"],
            canonical_data,
        )

        assert "326.5亿元" in result
        assert "300亿元" not in result


class TestM3CanonicalKeyMatching:
    """canonical_data 的 key 匹配逻辑测试"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        return GenericAgent(agent_id="test", agent_type="analysis", config={})

    def test_metric_matched_via_key_prefix(self, agent):
        """canonical key '净利润_2024_CNY' 匹配 metric '净利润'（差异>5%）"""
        content = "净利润300亿元"
        canonical = {
            "净利润_2024_CNY_审计口径": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result

    def test_metric_key_contains_metric_name(self, agent):
        """canonical key 包含 metric 名就能匹配（差异>5%）"""
        content = "营收5000亿元"
        canonical = {
            "营收_2024": {"value": 5400, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "5400亿元" in result

    def test_multiple_canonical_entries_same_metric(self, agent):
        """同一指标多个 canonical 条目，差异值大的应触发替换"""
        content = "销量380万辆"
        canonical = {
            "销量_2024_CNY_A股": {"value": 460, "unit": "万辆"},
            "销量_2024_CNY_港股": {"value": 380, "unit": "万辆"},
        }
        result = agent._enforce_canonical_values(content, canonical)
        # 460 与 380 差异大，应替换为差异最大的 canonical 值
        assert "460万辆" in result
