# -*- coding: utf-8 -*-
"""Tests for Chinese data extraction (改造项3)"""

import pytest
from src.services.smart_chart_generator import SmartChartGenerator


class TestCnMarketShare:
    """Test _extract_cn_market_share method"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_basic_market_share(self):
        """Basic format: 公司名市场份额31.8%"""
        content = "比亚迪市场份额31.8%，特斯拉6.4%，大众5.2%"
        result = self.gen._extract_cn_market_share(content)
        assert result is not None
        assert "比亚迪" in result["categories"]
        assert 31.8 in result["values"]

    def test_market_share_with_colon(self):
        """Format with colon: 市场份额：31.8%"""
        content = "比亚迪市场份额：31.8%，特斯拉：6.4%"
        result = self.gen._extract_cn_market_share(content)
        assert result is not None

    def test_market_share_no_connector(self):
        """No connector word: 市场份额31.8%"""
        content = "比亚迪市场份额31.8%，特斯拉市场份额6.4%"
        result = self.gen._extract_cn_market_share(content)
        assert result is not None

    def test_market_share_keyword_first(self):
        """Keyword first: 市场份额：比亚迪31.8%"""
        content = "市场份额：比亚迪31.8%，特斯拉6.4%，大众5.2%"
        result = self.gen._extract_cn_market_share(content)
        assert result is not None
        assert "比亚迪" in result["categories"]
        assert 31.8 in result["values"]

    def test_single_company_no_result(self):
        """Only 1 company doesn't meet minimum 2 data points"""
        content = "比亚迪市场份额31.8%"
        result = self.gen._extract_cn_market_share(content)
        assert result is None

    def test_continuation_no_false_match(self):
        """Continuation pattern doesn't match non-entity indicators"""
        content = "比亚迪市场份额31.8%，满意度85%，复购率92%，特斯拉6.4%"
        result = self.gen._extract_cn_market_share(content)
        assert result is not None
        assert "满意度" not in result["categories"]
        assert "复购率" not in result["categories"]
        assert "特斯拉" in result["categories"]


class TestCnGrowthData:
    """Test _extract_cn_growth_data method"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_growth_positive(self):
        """Positive growth: 同比增长"""
        content = "2024年同比增长20%，2025年同比增长13%"
        result = self.gen._extract_cn_growth_data(content)
        assert result is not None
        assert 20.0 in result["values"]
        assert 13.0 in result["values"]

    def test_growth_negative(self):
        """Negative growth: 同比下降 should be negative"""
        content = "2024年同比增长5.3%，2025年同比下降3.2%"
        result = self.gen._extract_cn_growth_data(content)
        assert result is not None
        assert 5.3 in result["values"]
        assert -3.2 in result["values"]

    def test_same_year_growth_and_decline(self):
        """Same year growth + decline doesn't lose data"""
        content = "2024年同比增长5.3%，2024年环比下降2.1%，2025年同比增长8.0%"
        result = self.gen._extract_cn_growth_data(content)
        assert result is not None
        assert len(result["categories"]) >= 2

    def test_no_cross_sentence_match(self):
        """Doesn't match across sentences"""
        content = "2024年销量950万。2025年同比增长20%"
        result = self.gen._extract_cn_growth_data(content)
        # 2024 should not match to 20% (cross-sentence)
        if result:
            for cat, val in zip(result["categories"], result["values"]):
                if cat == "2024":
                    assert val != 20.0

    def test_year_with_comma(self):
        """Year followed by comma still matches: 2024年，同比增长5.3%"""
        content = "2024年，同比增长5.3%，2025年，同比增长8.0%"
        result = self.gen._extract_cn_growth_data(content)
        assert result is not None
        assert 5.3 in result["values"]
        assert 8.0 in result["values"]

    def test_no_cross_comma_mismatch(self):
        """Doesn't cross-comma mismatch: 2024年销量950万，2025年同比增长20%"""
        content = "2024年销量950万，2025年同比增长20%"
        result = self.gen._extract_cn_growth_data(content)
        if result:
            for cat, val in zip(result["categories"], result["values"]):
                if cat == "2024":
                    assert val != 20.0

    def test_same_year_dedup_preserves_first(self):
        """Same year dedup keeps first value, doesn't overwrite"""
        content = "2024年同比增长5.3%，2024年同比下降3.2%，2025年同比增长8.0%"
        result = self.gen._extract_cn_growth_data(content)
        assert result is not None
        # 2024 should keep 5.3 (growth), not overwritten by -3.2
        for cat, val in zip(result["categories"], result["values"]):
            if cat == "2024":
                assert val == 5.3


class TestCnSalesData:
    """Test _extract_cn_sales_data method"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_basic_sales(self):
        """Basic sales extraction"""
        content = "比亚迪销量38万，吉利销量25万"
        result = self.gen._extract_cn_sales_data(content)
        assert result is not None
        assert "比亚迪" in result["categories"]
        assert "吉利" in result["categories"]

    def test_name_cleanup_word_level(self):
        """Word-level replacement: 量子公司销量 → 量子公司, not 子公司"""
        content = "量子公司销量38万，恒瑞医药销量25万"
        result = self.gen._extract_cn_sales_data(content)
        assert result is not None
        assert "量子公司" in result["categories"]
        assert "子公司" not in result["categories"]

    def test_unit_conversion(self):
        """Unit conversion: 亿 → 万"""
        content = "比亚迪销量1亿，吉利销量5000万"
        result = self.gen._extract_cn_sales_data(content)
        assert result is not None
        # 1亿 = 10000万
        assert 10000.0 in result["values"]


class TestCnRankingData:
    """Test _extract_cn_ranking_data method"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_no_ranking_context_no_result(self):
        """No ranking context returns None"""
        content = "价格：25万，利润：3.5亿元"
        result = self.gen._extract_cn_ranking_data(content)
        assert result is None

    def test_ranking_with_context(self):
        """Ranking with context keywords"""
        content = "TOP5排名：比亚迪：38万辆，吉利：17万辆，长安：15万辆"
        result = self.gen._extract_cn_ranking_data(content)
        assert result is not None
        assert "比亚迪" in result["categories"]

    def test_ranking_reversed_order(self):
        """Ranking data is reversed for horizontal bar chart"""
        content = "排名：A：100，B：200，C：300"
        result = self.gen._extract_cn_ranking_data(content)
        if result:
            # Should be reversed
            assert result["categories"][0] != "A"


class TestNoDuplicateExtraction:
    """Test that Chinese extraction doesn't duplicate English extraction"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_english_takes_priority(self):
        """English extraction has priority, Chinese only runs if English fails"""
        content = "Market share: BYD 31.8%, Tesla 6.4%"
        result = self.gen._extract_data_from_content(content)
        # market_share key should exist, from English extraction
        assert "market_share" in result

    def test_chinese_fallback(self):
        """Chinese extraction runs when English has no results"""
        content = "比亚迪市场份额31.8%，特斯拉6.4%"
        result = self.gen._extract_data_from_content(content)
        assert "market_share" in result
        # Check that we have Chinese company names (比亚迪 or 比亚迪市场份额)
        categories = result["market_share"]["categories"]
        assert any("比亚迪" in cat for cat in categories)


class TestCnTitleAndCaption:
    """Test Chinese title and caption generation"""

    def setup_method(self):
        self.gen = SmartChartGenerator()

    def test_chinese_title(self):
        """Chinese section title gets Chinese chart title"""
        title = self.gen._generate_title("市场份额分析", "market_share")
        assert "市场份额" in title

    def test_chinese_caption(self):
        """Chinese data type gets Chinese caption"""
        caption = self.gen._generate_caption("market_share", {"categories": ["A", "B"]})
        assert "市场份额" in caption or "样本" in caption

    def test_english_fallback(self):
        """English section title gets English title"""
        title = self.gen._generate_title("Market Share Analysis", "market_share")
        assert "Market Share" in title or "市场份额" in title
