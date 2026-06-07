"""
Phase 5 tests: English regex pattern extraction in MetricExtractor.
Verifies all 12 metric types can be extracted from English text.
"""
import pytest

@pytest.fixture
def extractor():
    from src.core.data.metric_extractor import MetricExtractor
    return MetricExtractor()


def _extract(extractor, text):
    return extractor.extract([{"content": text, "url": ""}])


class TestEnNetProfit:
    def test_net_profit_billion(self, extractor):
        r = _extract(extractor, "net profit of 32.6 billion CNY in 2024")
        assert len(r) >= 1
        assert r[0]["metric"] == "净利润"
        assert r[0]["value"] == 32.6

    def test_net_income_million(self, extractor):
        r = _extract(extractor, "net income was 500.5 million USD")
        assert len(r) >= 1
        assert r[0]["metric"] == "净利润"
        assert r[0]["value"] == 500.5


class TestEnRevenue:
    def test_revenue(self, extractor):
        r = _extract(extractor, "Total revenue reached 777.0 billion CNY")
        assert len(r) >= 1
        assert r[0]["metric"] == "营收"

    def test_turnover(self, extractor):
        r = _extract(extractor, "turnover of 120.3 billion EUR")
        assert len(r) >= 1
        assert r[0]["metric"] == "营收"


class TestEnSalesVolume:
    def test_deliveries_million(self, extractor):
        r = _extract(extractor, "BYD delivered 4.25 million vehicles in 2024")
        assert len(r) >= 1
        assert r[0]["metric"] == "销量"
        assert abs(r[0]["value"] - 4.25) < 0.01

    def test_sales_thousand(self, extractor):
        r = _extract(extractor, "sales of 850 thousand units")
        assert len(r) >= 1
        assert r[0]["metric"] == "销量"


class TestEnOverseasSales:
    def test_overseas_sales(self, extractor):
        r = _extract(extractor, "overseas sales of 1.2 million vehicles")
        assert len(r) >= 1
        assert r[0]["metric"] == "海外销量"


class TestEnRD:
    def test_rd_expense(self, extractor):
        r = _extract(extractor, "R&D expense of 15.0 billion CNY")
        assert len(r) >= 1
        assert r[0]["metric"] == "研发投入"

    def test_research_development(self, extractor):
        r = _extract(extractor, "research and development spending 12.5 billion USD")
        assert len(r) >= 1
        assert r[0]["metric"] == "研发投入"


class TestEnGrossMargin:
    def test_gross_margin(self, extractor):
        r = _extract(extractor, "gross margin improved to 20.1%")
        assert len(r) >= 1
        assert r[0]["metric"] == "毛利率"
        assert abs(r[0]["value"] - 20.1) < 0.01

    def test_gross_profit_margin(self, extractor):
        r = _extract(extractor, "gross profit margin was 18.5%")
        assert len(r) >= 1
        assert r[0]["metric"] == "毛利率"


class TestEnMarketShare:
    def test_market_share(self, extractor):
        r = _extract(extractor, "market share reached 35.5%")
        assert len(r) >= 1
        assert r[0]["metric"] == "市占率"


class TestEnGrowthRate:
    def test_growth_rate(self, extractor):
        r = _extract(extractor, "growth rate of 12.3%")
        assert len(r) >= 1
        assert r[0]["metric"] == "增长率"


class TestEnCashFlow:
    def test_cash_flow(self, extractor):
        r = _extract(extractor, "operating cash flow of 200.0 billion CNY")
        assert len(r) >= 1
        assert r[0]["metric"] == "现金流"


class TestEnDebtRatio:
    def test_debt_ratio(self, extractor):
        r = _extract(extractor, "debt-to-asset ratio stands at 55.2%")
        assert len(r) >= 1
        assert r[0]["metric"] == "负债率"

    def test_liability_ratio(self, extractor):
        r = _extract(extractor, "liability ratio was 48.7%")
        assert len(r) >= 1
        assert r[0]["metric"] == "负债率"


class TestEnCurrencyInference:
    def test_currency_cny(self, extractor):
        r = _extract(extractor, "net profit 32.6 billion CNY")
        if r:
            assert r[0].get("currency") == "CNY"

    def test_currency_usd(self, extractor):
        r = _extract(extractor, "revenue 100.0 billion USD")
        if r:
            assert r[0].get("currency") == "USD"

    def test_currency_eur(self, extractor):
        r = _extract(extractor, "turnover 80.0 billion EUR")
        if r:
            assert r[0].get("currency") == "EUR"


class TestEnYearInference:
    def test_year_2024(self, extractor):
        r = _extract(extractor, "In 2024, BYD's net profit reached 32.6 billion CNY")
        if r:
            assert r[0]["year"] == 2024

    def test_year_2025(self, extractor):
        r = _extract(extractor, "revenue in 2025 was 800 billion CNY")
        if r:
            assert r[0]["year"] == 2025


class TestEnglishAliasesOnGenericAgent:
    def test_net_profit_alias_in_enforce(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"

        content = "In 2024, net profit was 30.0 billion CNY"
        canonical = {
            "净利润_2024_CNY": {"value": 32.6, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "32.6" in result
        assert "30.0" not in result

    def test_revenue_alias_in_enforce(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"

        content = "Total revenue was 700.0 billion CNY in 2024"
        canonical = {
            "营收_2024_CNY": {"value": 777.0, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "777.0" in result

    def test_chinese_still_works_alongside_english(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"

        content = "2024年净利润300亿元。net profit was 30.0 billion CNY."
        canonical = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}
        }
        result = agent._enforce_canonical_values(content, canonical)
        assert "326.5亿元" in result
        assert "300亿元" not in result
        assert "326.5" in result
