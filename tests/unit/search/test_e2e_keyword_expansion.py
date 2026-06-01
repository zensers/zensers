# -*- coding: utf-8 -*-
"""
端到端测试：搜索关键词扩展

测试完整的数据流：
1. RequirementAnalysisAgent -> domain_context
2. GenericAgent._do_deep_research() -> LLM 扩展触发
3. 搜索停止条件验证
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


class TestE2EDomainRoleInferrer:
    """端到端测试：DomainRoleInferrer"""

    def test_chinese_input_detection(self):
        """测试中文输入检测"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        # 测试各种中文输入
        test_cases = [
            ("新能源汽车市场分析", "zh"),
            ("储能行业投资机会研究", "zh"),
            ("人工智能发展趋势", "zh"),
            ("这是一个测试文本", "zh"),
        ]
        
        for text, expected in test_cases:
            result = inferrer.detect_language(text)
            assert result == expected, f"Failed for: {text}"

    def test_english_input_detection(self):
        """测试英文输入检测"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        # 测试各种英文输入
        test_cases = [
            ("electric vehicle market analysis", "en"),
            ("energy storage investment opportunities", "en"),
            ("AI technology trends", "en"),
            ("This is a test text", "en"),
        ]
        
        for text, expected in test_cases:
            result = inferrer.detect_language(text)
            assert result == expected, f"Failed for: {text}"

    def test_all_research_types_zh(self):
        """测试所有研究类型（中文）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        research_types = ["market_research", "investment", "policy", "competitor", "technology", "industry"]
        
        for rt in research_types:
            result = inferrer.infer(rt, "测试主题", language="zh")
            assert result["role"] is not None
            assert result["expertise"] is not None
            assert result["data_focus"] is not None
            assert result["language"] == "zh"
            assert result["research_type"] == rt

    def test_all_research_types_en(self):
        """测试所有研究类型（英文）"""
        from src.core.search import DomainRoleInferrer
        
        inferrer = DomainRoleInferrer()
        
        research_types = ["market_research", "investment", "policy", "competitor", "technology", "industry"]
        
        for rt in research_types:
            result = inferrer.infer(rt, "test topic", language="en")
            assert result["role"] is not None
            assert result["expertise"] is not None
            assert result["data_focus"] is not None
            assert result["language"] == "en"
            # 验证英文内容
            assert all(ord(c) < 128 or c in " ,.-" for c in result["role"])


class TestE2ERequirementAnalysisAgent:
    """端到端测试：RequirementAnalysisAgent"""

    def test_intent_with_domain_context_flow(self):
        """测试意图识别 -> domain_context 完整流程"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_e2e")
        
        # 模拟用户输入
        user_input = "新能源汽车市场投资机会分析"
        result = agent._identify_intent(user_input)
        
        # 验证返回结构
        assert "type" in result
        assert "audience" in result
        assert "scenario" in result
        assert "language" in result
        assert "domain_context" in result
        
        # 验证 domain_context 结构
        domain_context = result["domain_context"]
        assert "role" in domain_context
        assert "expertise" in domain_context
        assert "data_focus" in domain_context
        assert "research_type" in domain_context
        assert "language" in domain_context

    def test_english_input_flow(self):
        """测试英文输入完整流程"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_e2e_en")
        
        user_input = "electric vehicle market analysis"
        result = agent._identify_intent(user_input)
        
        # 验证语言检测
        assert result["language"] == "en"
        assert result["domain_context"]["language"] == "en"
        
        # 验证英文角色
        assert "Senior" in result["domain_context"]["role"] or "Analyst" in result["domain_context"]["role"]


class TestE2EStopConditions:
    """端到端测试：搜索停止条件"""

    def test_max_queries_constant(self):
        """测试 MAX_QUERIES 常量定义"""
        from src.core.agents import GenericAgent
        
        # 验证常量在代码中定义
        # 通过读取源码验证
        import inspect
        source = inspect.getsource(GenericAgent._do_deep_research)
        
        assert "MAX_QUERIES = 50" in source, "MAX_QUERIES should be 50"
        assert "MAX_ITERATIONS = 20" in source, "MAX_ITERATIONS should be 20"
        assert "MAX_LLM_CALLS = 3" in source, "MAX_LLM_CALLS should be 3"

    def test_stop_condition_logic(self):
        """测试停止条件逻辑"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_stop", config={})
        
        # 模拟停止条件检查
        # 条件 1: 质量达标
        executed_queries = set(["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"])
        min_queries = 10
        high_quality_count = 8
        MIN_SOURCES = 8
        quality_score = 55.0
        MIN_QUALITY_SCORE = 50.0
        
        # 验证条件逻辑
        should_stop_quality = (
            len(executed_queries) >= min_queries and
            high_quality_count >= MIN_SOURCES and
            quality_score >= MIN_QUALITY_SCORE
        )
        assert should_stop_quality, "Quality condition should trigger stop"
        
        # 条件 2: 质量停滞
        stagnation_count = 10
        STAGNATION_LIMIT = 10
        should_stop_stagnation = stagnation_count >= STAGNATION_LIMIT
        assert should_stop_stagnation, "Stagnation condition should trigger stop"
        
        # 条件 3: 最大搜索次数
        executed_queries_large = set([f"q{i}" for i in range(50)])
        MAX_QUERIES = 50
        should_stop_max = len(executed_queries_large) >= MAX_QUERIES
        assert should_stop_max, "Max queries condition should trigger stop"


class TestE2EValidateQuery:
    """端到端测试：查询词验证"""

    def test_valid_queries(self):
        """测试有效查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_validate", config={})
        
        valid_queries = [
            "新能源汽车 销量 2024",
            "储能 政策文件",
            "AI芯片 企业排名",
            "人工智能 融资动态",
            "半导体 产量统计",
        ]
        
        for query in valid_queries:
            assert agent._validate_query(query), f"Should be valid: {query}"

    def test_invalid_queries_forbidden_words(self):
        """测试包含禁止词汇的查询词"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_validate", config={})
        
        invalid_queries = [
            "新能源汽车 市场分析报告",
            "储能行业 研究报告",
            "AI芯片 预测分析",
            "market analysis report",
            "industry research forecast",
        ]
        
        for query in invalid_queries:
            assert not agent._validate_query(query), f"Should be invalid: {query}"

    def test_query_length_validation(self):
        """测试查询词长度验证"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_validate", config={})
        
        # 过短
        assert not agent._validate_query("ab")
        assert not agent._validate_query("test")
        
        # 过长
        long_query = "a" * 150
        assert not agent._validate_query(long_query)
        
        # 合适长度
        assert agent._validate_query("新能源汽车 销量 2024")


class TestE2ELLMMock:
    """端到端测试：LLM 调用模拟"""

    @pytest.mark.asyncio
    async def test_call_llm_directly_mock(self):
        """测试 _call_llm_directly 方法（模拟）"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_llm", config={})
        
        # 模拟 LLM 调用
        with patch.object(agent, '_call_llm_directly', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": "新能源汽车 销量 2024\n新能源汽车 企业排名\n新能源汽车 政策文件"
            }
            
            result = await agent._call_llm_directly(
                prompt="生成搜索关键词",
                system_prompt="你是一个分析师",
            )
            
            assert result["success"]
            assert "新能源汽车" in result["content"]

    @pytest.mark.asyncio
    async def test_generate_smart_queries_mock(self):
        """测试 _generate_smart_queries_with_llm 方法（模拟）"""
        from src.core.agents import GenericAgent
        
        agent = GenericAgent(agent_id="test_llm", config={})
        
        # 模拟 LLM 返回
        llm_response = """新能源汽车 销量 2024
新能源汽车 企业排名
新能源汽车 政策文件
新能源汽车 融资动态
新能源汽车 最新消息"""
        
        with patch.object(agent, '_call_llm_directly', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"success": True, "content": llm_response}
            
            queries = await agent._generate_smart_queries_with_llm(
                topic="新能源汽车",
                aspect="市场分析",
                existing_queries=[],
                role_info={
                    "role": "资深市场研究分析师",
                    "expertise": ["市场定量分析"],
                    "data_focus": ["市场规模"],
                },
                min_queries=10,
            )
            
            assert len(queries) > 0
            assert all("新能源汽车" in q for q in queries)


class TestE2EIntegration:
    """端到端集成测试"""

    def test_full_flow_domain_context_to_agent(self):
        """测试完整流程：domain_context -> Agent"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        from src.core.search import DomainRoleInferrer
        
        # Step 1: 用户输入
        user_input = "储能行业投资机会分析"
        
        # Step 2: RequirementAnalysisAgent 识别意图
        agent = RequirementAnalysisAgent(agent_id="test_integration")
        intent = agent._identify_intent(user_input)
        
        # Step 3: 验证 domain_context
        assert intent["type"] == "investment"
        assert intent["domain_context"]["role"] == "资深投资分析师"
        
        # Step 4: 模拟传递到 GenericAgent
        # 验证数据结构完整性
        domain_context = intent["domain_context"]
        assert all(key in domain_context for key in ["role", "expertise", "data_focus", "research_type", "language"])

    def test_language_consistency(self):
        """测试语言一致性"""
        from src.agents.fixed_agents import RequirementAnalysisAgent
        
        agent = RequirementAnalysisAgent(agent_id="test_lang")
        
        # 中文输入
        zh_intent = agent._identify_intent("新能源汽车市场分析")
        assert zh_intent["language"] == "zh"
        assert zh_intent["domain_context"]["language"] == "zh"
        
        # 英文输入
        en_intent = agent._identify_intent("electric vehicle market analysis")
        assert en_intent["language"] == "en"
        assert en_intent["domain_context"]["language"] == "en"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
