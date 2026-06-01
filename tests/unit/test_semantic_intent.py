# -*- coding: utf-8 -*-
"""
SemanticIntentAnalyzer 单元测试
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.core.semantic_intent import (
    SemanticIntentAnalyzer,
    DeepIntentResult,
)
# Phase 4: 更新导入
from src.core.intent_types import IntentType, TaskComplexity
from src.core.research_type import ResearchType


class TestDeepIntentResult:
    """DeepIntentResult 数据类测试"""
    
    def test_to_dict(self):
        """测试序列化"""
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="测试推理",
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            primary_research_type=ResearchType.INDUSTRY_RESEARCH,
            complexity=TaskComplexity.MULTI,
            aspect_count=3,
        )
        
        d = result.to_dict()
        
        assert d["primary_intent"] == "research"
        assert d["intent_confidence"] == 0.9
        assert d["research_types"] == ["industry_research"]
        assert d["complexity"] == "multi"
        assert d["aspect_count"] == 3
    
    def test_to_intent_analysis_result(self):
        """测试转换为兼容格式"""
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.85,
            intent_reasoning="用户明确要求分析市场",
            complexity=TaskComplexity.MULTI,
            aspect_count=3,
            recommended_skills=["search_skill", "llm_skill"],
        )
        
        intent_result = result.to_intent_analysis_result()
        
        assert intent_result.intent == IntentType.RESEARCH
        assert intent_result.confidence == 0.85
        assert intent_result.complexity == TaskComplexity.MULTI
        assert "search_skill" in intent_result.strategy.skill_requirements
    
    def test_infer_recommended_agents(self):
        """测试推断推荐 Agent"""
        # 研究型任务
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="测试",
            requires_secondary_data=True,
            aspect_count=2,
        )
        agents = result._infer_recommended_agents()
        assert "data-collection" in agents
        assert "market-analysis" in agents
        
        # 修复型任务
        result = DeepIntentResult(
            primary_intent=IntentType.FIX,
            intent_confidence=0.9,
            intent_reasoning="测试",
            requires_secondary_data=False,
        )
        agents = result._infer_recommended_agents()
        assert "quality-check" in agents
    
    def test_estimate_agent_count(self):
        """测试估算 Agent 数量"""
        # 基础情况
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="测试",
            aspect_count=3,
        )
        assert result._estimate_agent_count() == 3
        
        # 需要一手数据
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="测试",
            aspect_count=2,
            requires_primary_data=True,
        )
        assert result._estimate_agent_count() == 4  # 2 + 2


class TestSemanticIntentAnalyzer:
    """SemanticIntentAnalyzer 测试"""
    
    def test_init_default(self):
        """测试默认初始化"""
        analyzer = SemanticIntentAnalyzer()
        assert analyzer._use_llm is True
        assert analyzer._fallback_to_keyword is True
        assert analyzer._temperature == 0.1
    
    def test_init_custom(self):
        """测试自定义参数初始化"""
        analyzer = SemanticIntentAnalyzer(
            use_llm=False,
            fallback_to_keyword=True,
            temperature=0.3,
            enable_self_consistency=True,
        )
        assert analyzer._use_llm is False
        assert analyzer._temperature == 0.3
        assert analyzer._enable_self_consistency is True
    
    def test_parse_llm_json(self):
        """测试 JSON 解析"""
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        
        # 正常 JSON
        json_str = '{"primary_intent": "research", "confidence": 0.9}'
        result = analyzer._parse_llm_json(json_str)
        assert result["primary_intent"] == "research"
        assert result["confidence"] == 0.9
        
        # 带 markdown 代码块
        json_str = '```json\n{"primary_intent": "evaluation"}\n```'
        result = analyzer._parse_llm_json(json_str)
        assert result["primary_intent"] == "evaluation"
    
    def test_infer_skills_from_intent(self):
        """测试从意图推断技能"""
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        
        # 研究型
        skills = analyzer._infer_skills_from_intent(IntentType.RESEARCH, [])
        assert "search_skill" in skills
        assert "llm_skill" in skills
        
        # 带隐含需求
        skills = analyzer._infer_skills_from_intent(
            IntentType.RESEARCH,
            ["需要收集市场数据", "生成报告文档"]
        )
        assert "search_skill" in skills
        assert "docx_skill" in skills
    
    def test_analyze_with_keyword_fallback(self):
        """测试关键词匹配 fallback"""
        analyzer = SemanticIntentAnalyzer(use_llm=False, fallback_to_keyword=True)
        
        result = analyzer.analyze(
            user_request="分析新能源汽车市场",
            requirement={"topic": "新能源汽车", "aspects": ["市场规模", "竞争格局"]}
        )
        
        assert isinstance(result, DeepIntentResult)
        assert result.used_fallback is True
        assert result.llm_model_used == "keyword_matching"
        assert result.primary_intent == IntentType.RESEARCH
    
    @pytest.mark.asyncio
    async def test_analyze_async_with_keyword(self):
        """测试异步分析（关键词模式）"""
        analyzer = SemanticIntentAnalyzer(use_llm=False, fallback_to_keyword=True)
        
        result = await analyzer.analyze_async(
            user_request="帮我做一个行业研究报告",
            requirement={"topic": "行业研究"}
        )
        
        assert isinstance(result, DeepIntentResult)
        assert result.used_fallback is True
    
    @pytest.mark.asyncio
    async def test_analyze_with_mock_llm(self):
        """测试 LLM 分析（mock）"""
        analyzer = SemanticIntentAnalyzer(use_llm=True, fallback_to_keyword=False)
        
        # Mock LLM Skill
        mock_llm_skill = AsyncMock()
        mock_llm_skill.execute.return_value = {
            "success": True,
            "content": json.dumps({
                "primary_intent": "research",
                "confidence": 0.92,
                "complexity": "multi",
                "reasoning": "用户请求明确包含市场分析意图",
                "research_types": ["industry_research"],
                "task_scope": "broad",
                "requires_primary_data": False,
                "requires_secondary_data": True,
                "hidden_requirements": ["收集行业规模数据", "分析竞争格局"],
                "aspect_count": 3,
                "execution_preference": "parallel",
                "recommended_skills": ["search_skill", "llm_skill"],
            }),
            "model": "gpt-4o",
        }
        
        analyzer._llm_skill = mock_llm_skill
        
        result = await analyzer.analyze_async(
            user_request="分析新能源汽车市场规模和竞争格局",
            requirement={"topic": "新能源汽车", "aspects": ["市场规模", "竞争格局"]}
        )
        
        assert isinstance(result, DeepIntentResult)
        assert result.used_fallback is False
        assert result.primary_intent == IntentType.RESEARCH
        assert result.intent_confidence == 0.92
        assert result.complexity == TaskComplexity.MULTI
        assert len(result.hidden_requirements) == 2
        assert result.llm_model_used == "gpt-4o"


import json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
