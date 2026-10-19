# -*- coding: utf-8 -*-
"""
搜索关键词扩展单元测试

测试覆盖：
1. DomainRoleInferrer 类
2. GenericAgent._validate_query()
3. GenericAgent._parse_llm_queries()
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


class TestDomainRoleInferrer:
    """DomainRoleInferrer 单元测试"""

    def test_import(self):
        """测试模块导入"""
        from src.core.search import DomainRoleInferrer
        assert DomainRoleInferrer is not None

    def test_infer_market_research_zh(self):
        """测试市场研究类型（中文）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        result = inferrer.infer("market_research", "新能源汽车", language="zh")
        
        assert result["role"] == "资深市场研究分析师"
        assert "市场定量分析" in result["expertise"]
        assert "市场规模" in result["data_focus"]
        assert result["language"] == "zh"
        assert result["research_type"] == "market_research"

    def test_infer_market_research_en(self):
        """测试市场研究类型（英文）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        result = inferrer.infer("market_research", "electric vehicles", language="en")
        
        assert result["role"] == "Senior Market Research Analyst"
        assert "Quantitative Market Analysis" in result["expertise"]
        assert "market size" in result["data_focus"]
        assert result["language"] == "en"

    def test_infer_investment_type(self):
        """测试投资研究类型"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        result = inferrer.infer("investment", "储能行业投资", language="zh")
        
        assert result["role"] == "资深投资分析师"
        assert "财务分析" in result["expertise"]
        assert "财务数据" in result["data_focus"]

    def test_infer_unknown_type(self):
        """测试未知研究类型（使用默认模板）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        result = inferrer.infer("unknown_type", "测试主题", language="zh")
        
        # 应该返回默认模板
        assert result["role"] == "资深研究分析师"
        assert result["research_type"] == "unknown_type"

    def test_infer_invalid_language(self):
        """测试无效语言参数（回退到中文）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        result = inferrer.infer("market_research", "测试", language="fr")
        
        # 应该回退到中文
        assert result["language"] == "zh"

    def test_detect_language_chinese(self):
        """测试中文检测"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        assert inferrer.detect_language("新能源汽车市场分析") == "zh"
        assert inferrer.detect_language("储能行业投资机会") == "zh"
        assert inferrer.detect_language("这是一个中文测试") == "zh"

    def test_detect_language_english(self):
        """测试英文检测"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        assert inferrer.detect_language("electric vehicle market analysis") == "en"
        assert inferrer.detect_language("energy storage investment") == "en"

    def test_get_supported_types(self):
        """测试获取支持的研究类型"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        types = inferrer.get_supported_types()
        
        assert "market_research" in types
        assert "investment" in types
        assert "policy" in types
        assert "competitor" in types
        assert "technology" in types
        assert "industry" in types

    def test_get_supported_languages(self):
        """测试获取支持的语言"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        languages = inferrer.get_supported_languages()
        
        assert "zh" in languages
        assert "en" in languages


class TestValidateQuery:
    """_validate_query 单元测试"""

    def test_valid_query(self):
        """测试有效查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        assert agent._validate_query("新能源汽车 销量 2024")
        assert agent._validate_query("储能 政策文件")
        assert agent._validate_query("AI芯片 企业排名")

    def test_invalid_query_too_short(self):
        """测试过短的查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        assert not agent._validate_query("ab")
        assert not agent._validate_query("test")

    def test_invalid_query_too_long(self):
        """测试过长的查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        long_query = "a" * 150
        assert not agent._validate_query(long_query)

    def test_invalid_query_forbidden_words(self):
        """测试包含禁止词汇的查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        assert not agent._validate_query("新能源汽车 市场分析报告")
        assert not agent._validate_query("储能行业 研究报告")
        assert not agent._validate_query("AI芯片 预测分析")
        assert not agent._validate_query("market research report")

    def test_invalid_query_duplicate(self):
        """测试重复的查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        existing = ["新能源汽车 销量 2024", "储能 政策"]
        
        assert not agent._validate_query("新能源汽车 销量 2024", existing)
        assert agent._validate_query("新能源汽车 产量 2024", existing)

    def test_invalid_query_pure_digits(self):
        """测试纯数字查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        assert not agent._validate_query("12345")


class TestParseLlmQueries:
    """_parse_llm_queries 单元测试"""

    def test_parse_simple_list(self):
        """测试解析简单列表"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        content = """新能源汽车 销量 2024
新能源汽车 企业排名
新能源汽车 政策文件
新能源汽车 融资动态"""
        
        queries = agent._parse_llm_queries(content)
        
        assert len(queries) == 4
        assert "新能源汽车 销量 2024" in queries
        assert "新能源汽车 政策文件" in queries

    def test_parse_numbered_list(self):
        """测试解析编号列表"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        content = """1. 新能源汽车 销量 2024
2. 新能源汽车 企业排名
3. 新能源汽车 政策文件"""
        
        queries = agent._parse_llm_queries(content)
        
        assert len(queries) == 3
        assert "新能源汽车 销量 2024" in queries

    def test_parse_with_empty_lines(self):
        """测试解析包含空行的内容"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        content = """新能源汽车 销量 2024

新能源汽车 企业排名

新能源汽车 政策文件"""
        
        queries = agent._parse_llm_queries(content)
        
        assert len(queries) == 3

    def test_parse_with_comments(self):
        """测试解析包含注释的内容"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        content = """# 这是注释
新能源汽车 销量 2024
新能源汽车 企业排名"""
        
        queries = agent._parse_llm_queries(content)
        
        assert len(queries) == 2

    def test_parse_max_limit(self):
        """测试解析结果数量限制（最多 8 个）"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        
        content = "\n".join([f"查询{i} 数据 2024" for i in range(15)])
        
        queries = agent._parse_llm_queries(content)
        
        assert len(queries) == 8

    def test_parse_with_existing_queries(self):
        """测试解析时排除已存在的查询"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test", config={})
        existing = ["新能源汽车 销量 2024", "储能 政策"]
        
        content = """新能源汽车 销量 2024
新能源汽车 企业排名
储能 政策
新能源汽车 融资动态"""
        
        queries = agent._parse_llm_queries(content, existing)
        
        assert len(queries) == 2
        assert "新能源汽车 销量 2024" not in queries
        assert "储能 政策" not in queries


class TestRequirementAnalysisAgent:
    """RequirementAnalysisAgent 单元测试"""

    def test_identify_intent_with_domain_context(self):
        """测试 _identify_intent 返回 domain_context"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_agent")
        result = agent._identify_intent("新能源汽车市场分析")
        
        assert "domain_context" in result
        assert "language" in result
        assert result["domain_context"]["role"] == "资深市场研究分析师"

    def test_identify_intent_investment(self):
        """测试投资类型识别"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_agent")
        result = agent._identify_intent("储能行业投资机会分析")
        
        assert result["type"] == "investment"
        assert result["domain_context"]["role"] == "资深投资分析师"

    def test_identify_intent_english(self):
        """测试英文输入识别"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_agent")
        result = agent._identify_intent("electric vehicle market analysis")
        
        assert result["language"] == "en"
        assert result["domain_context"]["language"] == "en"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
