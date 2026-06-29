"""
TDD tests for akshare data format fixes (BUG-1 through BUG-7).
RED phase: tests should FAIL before implementation.
"""

import pytest
import json


class TestBUG1ListDataNotDropped:
    """BUG-1: price_history returns list data, must not be silently dropped by _fetch_structured_data."""

    def test_list_data_creates_data_point(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug1", agent_type="dynamic", config={"skills": [], "context": {}})

        async def mock_execute(**kwargs):
            return {
                "success": True,
                "data": [{"日期": "2024-01-02", "开盘": 1700.0, "收盘": 1720.0}],
                "content": "Retrieved price data for 600519",
                "symbol": "600519",
            }

        mock_skill = MagicMock()
        mock_skill.execute = mock_execute

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            agent._fetch_structured_data(mock_skill, "600519", "股价走势")
        )
        assert len(result["data_points"]) > 0, "list data must not be silently dropped"


class TestBUG2ContentUsesSkillResultContent:
    """BUG-2: content should use skill_result['content'] instead of str(data)."""

    def test_prefers_skill_result_content(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug2a", agent_type="dynamic", config={"skills": [], "context": {}})

        async def mock_execute(**kwargs):
            return {
                "success": True,
                "data": {"revenue": 99999999999.0, "profit": 88888888888.0},
                "content": "Revenue: 999.99 billion | Profit: 888.89 billion | This is a very detailed and long content that should be preferred over the auto-formatted version because it contains more useful information for the LLM analysis agent to process and understand",
                "symbol": "600519",
            }

        mock_skill = MagicMock()
        mock_skill.execute = mock_execute

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            agent._fetch_structured_data(mock_skill, "600519", "公司分析")
        )
        dp = result["data_points"][0]
        assert "Revenue" in dp["content"] or "revenue" in dp["content"].lower(), f"should use longer skill_result['content'], got: {dp['content'][:100]}"

    def test_fallback_to_json_dumps_when_no_content(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug2b", agent_type="dynamic", config={"skills": [], "context": {}})

        async def mock_execute(**kwargs):
            return {
                "success": True,
                "data": {"metric_a": 100, "metric_b": 200},
                "symbol": "600519",
            }

        mock_skill = MagicMock()
        mock_skill.execute = mock_execute

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            agent._fetch_structured_data(mock_skill, "600519", "公司分析")
        )
        dp = result["data_points"][0]
        assert "metric_a" in dp["content"], "should fallback to json.dumps(data)"
        assert "\n" in dp["content"] or dp["content"].startswith("{"), "should be formatted JSON not str(dict)"

    def test_financials_content_not_just_summary(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug2c", agent_type="dynamic", config={"skills": [], "context": {}})

        async def mock_execute(**kwargs):
            return {
                "success": True,
                "data": {
                    "income_statement": [
                        {"REPORT_DATE": "2024-09-30", "OPERATE_INCOME": 12000000000.0},
                    ],
                },
                "content": "Retrieved three financial statements for 600519",
                "symbol": "600519",
            }

        mock_skill = MagicMock()
        mock_skill.execute = mock_execute

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            agent._fetch_structured_data(mock_skill, "600519", "盈利分析")
        )
        dp = result["data_points"][0]
        assert "利润表" in dp["content"] or "income_statement" in dp["content"], "financials content should be formatted"


class TestBUG3CanonicalMetricsExtractsNumbers:
    """BUG-3: canonical_metrics should extract numeric values from strings and nested structures."""

    def test_extracts_string_numbers(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3a", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"基本每股收益": "41.75", "每股净资产": "168.28"})
        has_eps = any("基本每股收益" in k for k in cm)
        assert has_eps, f"should extract string numbers, got: {cm}"

    def test_extracts_nested_numbers(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3b", agent_type="dynamic", config={"skills": [], "context": {}})
        data = {
            "income_statement": [
                {"REPORT_DATE": "2024-09-30", "OPERATE_INCOME": 12000000000.0, "NET_PROFIT": 3000000000.0},
            ],
        }
        cm = agent._extract_numeric_metrics(data)
        has_income = any("OPERATE_INCOME" in k for k in cm)
        assert has_income, f"should extract nested numeric values, got: {cm}"

    def test_skips_unit_strings(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3c", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"行业": "白酒"})
        assert "行业" not in cm, "non-numeric strings should be skipped"

    def test_extracts_chinese_unit_yi(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3e", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"净利润": "1.47亿", "营业总收入": "6.28亿"})
        assert "净利润" in cm, f"should parse '1.47亿', got: {cm}"
        assert cm["净利润"] == 1.47e8, f"'1.47亿' should be 1.47e8, got {cm['净利润']}"

    def test_extracts_chinese_unit_wan(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3f", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"注册资本": "5000万"})
        assert "注册资本" in cm, f"should parse '5000万', got: {cm}"
        assert cm["注册资本"] == 5e7, f"'5000万' should be 5e7, got {cm['注册资本']}"

    def test_extracts_percentage(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3g", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"销售毛利率": "87.79%", "资产负债率": "68.44%"})
        assert "销售毛利率" in cm, f"should parse '87.79%', got: {cm}"
        assert abs(cm["销售毛利率"] - 0.8779) < 1e-6, f"'87.79%' should be 0.8779, got {cm['销售毛利率']}"

    def test_skips_bool_values(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3h", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"扣非净利润": False, "valid": True})
        assert "扣非净利润" not in cm, "bool False should not be extracted as 0.0"
        assert "valid" not in cm, "bool True should not be extracted as 1.0"

    def test_extracts_int_and_float_directly(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug3d", agent_type="dynamic", config={"skills": [], "context": {}})
        cm = agent._extract_numeric_metrics({"count": 42, "ratio": 3.14})
        assert cm.get("count") == 42
        assert cm.get("ratio") == 3.14


class TestBUG4ValidationPreservesStructuredQuality:
    """BUG-4: _validate_collected_data should preserve quality_score for structured data sources."""

    def test_structured_source_gets_high_quality(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug4", agent_type="dynamic", config={"skills": [], "context": {}})

        data_points = [{
            "title": "600519 financials",
            "content": "some content with 2024 year ref",
            "url": "stock_data://600519/financials",
            "quality_score": 95,
            "credibility": "structured_source",
        }]

        result = agent._validate_collected_data(data_points, [])
        validated = result.get("validated_data_points", [])
        assert len(validated) > 0
        assert validated[0]["quality_score"] >= 90, f"structured source should keep quality >= 90, got {validated[0]['quality_score']}"
        assert validated[0]["credibility_score"] >= 0.9, f"structured source should have high credibility, got {validated[0]['credibility_score']}"

    def test_normal_web_source_keeps_normal_quality(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug4b", agent_type="dynamic", config={"skills": [], "context": {}})

        data_points = [{
            "title": "Some blog post",
            "content": "some content",
            "url": "https://example.com/article",
            "quality_score": 50,
            "credibility": "tier4_general",
        }]

        result = agent._validate_collected_data(data_points, [])
        validated = result.get("validated_data_points", [])
        assert validated[0]["quality_score"] < 90, "normal source should not get structured quality boost"


class TestBUG5StructuredTruncation:
    """BUG-5: structured data should use longer truncation (800) vs normal (300)."""

    def test_analysis_prompt_longer_truncation_for_structured(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug5a", agent_type="dynamic", config={"skills": [], "context": {}})

        long_content = "A" * 500
        data_points = [{
            "title": "600519 financials",
            "content": long_content,
            "url": "stock_data://600519/financials",
            "quality_score": 95,
            "credibility": "structured_source",
        }]

        prompt = agent._build_analysis_prompt_with_data(
            topic="贵州茅台", aspect="财务分析", aspects=["财务分析"],
            data_points=data_points, sources=[],
        )
        assert "AAAA" in prompt, "structured data > 300 chars should not be truncated at 300"

    def test_analysis_prompt_normal_truncation(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug5b", agent_type="dynamic", config={"skills": [], "context": {}})

        long_content = "B" * 500
        data_points = [{
            "title": "Some article",
            "content": long_content,
            "url": "https://example.com/article",
            "quality_score": 50,
        }]

        prompt = agent._build_analysis_prompt_with_data(
            topic="贵州茅台", aspect="财务分析", aspects=["财务分析"],
            data_points=data_points, sources=[],
        )
        content_section = prompt[prompt.find("Content:"):prompt.find("Content:") + 320] if "Content:" in prompt else ""
        assert "B" * 310 not in content_section, "normal data > 300 chars should be truncated at 300 in Content section"

    def test_synthesis_prompt_longer_truncation_for_structured(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug5c", agent_type="dynamic", config={"skills": [], "context": {}})

        long_content = "C" * 400
        data_points = [{
            "title": "600519 financials",
            "content": long_content,
            "url": "stock_data://600519/financials",
            "quality_score": 95,
        }]

        prompt = agent._build_synthesis_prompt_with_data(
            topic="贵州茅台", aspect="财务分析", aspects=["财务分析"],
            data_points=data_points, sources=[], previous_content=[],
            target_aspect="财务分析",
        )
        assert "CCCC" in prompt, "structured data > 200 chars should not be truncated at 200"


class TestBUG6InferStockActionsIncludesPriceHistory:
    """BUG-6: _infer_stock_actions should return price_history for price-related aspects."""

    def test_price_keyword(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug6a", agent_type="dynamic", config={"skills": [], "context": {}})
        actions = agent._infer_stock_actions("股价分析")
        assert "price_history" in actions, f"'股价' should trigger price_history, got: {actions}"

    def test_market_performance_keyword(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug6b", agent_type="dynamic", config={"skills": [], "context": {}})
        actions = agent._infer_stock_actions("行情走势")
        assert "price_history" in actions, f"'行情' should trigger price_history, got: {actions}"


class TestBUG7StructuredSourceCredibilityLabel:
    """BUG-7: 'structured_source' should get a credibility label in analysis prompt."""

    def test_structured_source_label_in_prompt(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_bug7", agent_type="dynamic", config={"skills": [], "context": {}})

        data_points = [{
            "title": "600519 financials",
            "content": "key data here",
            "url": "stock_data://600519/financials",
            "quality_score": 95,
            "credibility": "structured_source",
        }]

        prompt = agent._build_analysis_prompt_with_data(
            topic="贵州茅台", aspect="财务分析", aspects=["财务分析"],
            data_points=data_points, sources=[],
        )
        assert "STRUCTURED" in prompt.upper(), "structured_source should have a credibility label"


class TestRealDataFormatKeyMetrics:
    """BUG-R2/R3: key_metrics data from akshare is per-period rows, not per-metric dict."""

    def test_format_key_metrics(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_real1", agent_type="dynamic", config={"skills": [], "context": {}})
        data = {
            "periods": [
                {"报告期": "2024-09-30", "净利润": "580.00亿", "营业总收入": "1200.00亿", "销售毛利率": "91.53%"},
                {"报告期": "2024-06-30", "净利润": "416.00亿", "营业总收入": "819.00亿"},
            ],
            "columns": ["报告期", "净利润", "营业总收入", "销售毛利率"],
        }
        result = agent._format_structured_data(data, "key_metrics", "600519")
        assert "关键财务指标" in result, f"should have key metrics header, got: {result[:100]}"
        assert "580.00亿" in result or "580" in result, f"should include numeric values, got: {result}"
        assert "2024-09-30" in result, f"should include period, got: {result}"

    def test_format_company_info(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_real2", agent_type="dynamic", config={"skills": [], "context": {}})
        data = {"股票简称": "贵州茅台", "行业": "白酒", "总股本": "12.56亿", "主营业务": "茅台酒生产"}
        result = agent._format_structured_data(data, "company_info", "600519")
        assert "公司信息" in result, f"should have company info header, got: {result[:100]}"
        assert "贵州茅台" in result, f"should include stock name, got: {result}"

    def test_extract_metrics_from_real_key_metrics_format(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent(agent_id="test_real3", agent_type="dynamic", config={"skills": [], "context": {}})
        data = {
            "periods": [
                {"报告期": "2024-09-30", "净利润": "580.00亿", "营业总收入": "1200.00亿", "销售毛利率": "91.53%"},
            ],
        }
        cm = agent._extract_numeric_metrics(data)
        assert any("净利润" in k for k in cm), f"should extract 净利润 from periods, got: {cm}"
        assert any("销售毛利率" in k for k in cm), f"should extract 销售毛利率, got: {cm}"

    def test_key_metrics_skill_result_format(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        assert skill.name == "stock_data"


from unittest.mock import MagicMock
