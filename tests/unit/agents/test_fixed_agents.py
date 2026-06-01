"""
固定Agent团队测试
================

测试固定Agent的核心功能。
"""

import pytest
import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from agents.fixed_agents import (
    RequirementAnalysisAgent,
    ReportGenerationAgent,
    LayoutDesignAgent,
    QualityCheckAgent,
    DataCollectionAgent,
)


class TestRequirementAnalysisAgent:
    """测试需求分析Agent."""
    
    def test_initialization(self):
        """测试Agent初始化."""
        agent = RequirementAnalysisAgent(
            agent_id="test_req_001",
            name="测试需求分析师",
        )
        
        assert agent.agent_id == "test_req_001"
        assert agent.name == "测试需求分析师"
        assert agent.status == "idle"
        assert "意图识别" in agent.capabilities
    
    def test_validate_input_missing_user_input(self):
        """测试输入验证 - 缺少user_input."""
        agent = RequirementAnalysisAgent("test_001", "测试")
        
        valid, error = agent.validate_input({})
        
        assert valid is False
        assert "user_input" in error
    
    def test_validate_input_valid(self):
        """测试输入验证 - 有效输入."""
        agent = RequirementAnalysisAgent("test_001", "测试")
        
        valid, error = agent.validate_input({
            "user_input": "分析储能行业",
        })
        
        assert valid is True
        assert error == ""
    
    def test_identify_intent_market_research(self):
        """测试意图识别 - 市场研究."""
        agent = RequirementAnalysisAgent("test_001", "测试")
        
        intent = agent._identify_intent("分析储能行业市场规模")
        
        assert intent["type"] == "market_research"
        assert intent["audience"] in ["investor", "executive", "researcher"]
    
    def test_identify_intent_investment(self):
        """测试意图识别 - 投资研究."""
        agent = RequirementAnalysisAgent("test_001", "测试")
        
        intent = agent._identify_intent("储能行业投资机会分析")
        
        assert intent["type"] == "investment"
    
    def test_extract_entities(self):
        """测试实体提取."""
        agent = RequirementAnalysisAgent("test_001", "测试")
        
        entities = agent._extract_entities(
            "分析中国储能行业，关注宁德时代",
            {}
        )
        
        assert entities["industry"] == "储能"
        assert entities["region"] == "中国"
        assert "宁德时代" in entities["companies"]
    
    def test_execute_full_flow(self):
        """测试完整执行流程."""
        agent = RequirementAnalysisAgent("test_001", "测试分析师")
        
        result = agent.run({
            "user_input": "分析中国储能行业投资机会",
            "context": {},
        })
        
        assert result["success"] is True
        assert "intent" in result
        assert "entities" in result
        assert "framework" in result
        assert result["agent_id"] == "test_001"


class TestReportGenerationAgent:
    """测试报告生成Agent."""
    
    def test_initialization(self):
        """测试Agent初始化."""
        agent = ReportGenerationAgent(
            agent_id="test_report_001",
            name="测试报告撰写员",
        )
        
        assert agent.agent_id == "test_report_001"
        assert "内容整合" in agent.capabilities
    
    def test_validate_input_missing_title(self):
        """测试输入验证 - 缺少title."""
        agent = ReportGenerationAgent("test_001", "测试")
        
        valid, error = agent.validate_input({
            "sections": [],
        })
        
        assert valid is False
        assert "title" in error
    
    def test_generate_cover(self):
        """测试封面生成."""
        agent = ReportGenerationAgent("test_001", "测试")
        
        cover = agent._generate_cover("测试报告", "market_research")
        
        assert "测试报告" in cover
        assert "研究报告" in cover
    
    def test_execute(self):
        """测试报告生成."""
        agent = ReportGenerationAgent("test_001", "测试")
        
        result = agent.run({
            "title": "储能行业研究报告",
            "sections": [
                {"id": "sec1", "title": "市场规模", "content": "市场规模内容..."},
                {"id": "sec2", "title": "竞争格局", "content": "竞争格局内容..."},
            ],
            "template_type": "market_research",
        })
        
        assert result["success"] is True
        assert "report" in result
        assert result["report"]["title"] == "储能行业研究报告"
        assert result["report"]["word_count"] > 0


class TestQualityCheckAgent:
    """测试质量检查Agent."""
    
    def test_initialization(self):
        """测试Agent初始化."""
        agent = QualityCheckAgent("test_001", "测试质检员")
        
        assert "完整性检查" in agent.capabilities
    
    def test_check_completeness_pass(self):
        """测试完整性检查 - 通过."""
        agent = QualityCheckAgent("test_001", "测试")
        
        report = {
            "word_count": 2000,
            "sections": [
                {"title": "执行摘要"},
                {"title": "市场规模"},
                {"title": "竞争格局"},
            ],
        }
        
        result = agent._check_completeness(report, agent.DEFAULT_STANDARDS)
        
        assert result["passed"] is True
        assert result["word_count"] == 2000
    
    def test_check_completeness_fail(self):
        """测试完整性检查 - 失败."""
        agent = QualityCheckAgent("test_001", "测试")
        
        report = {
            "word_count": 500,  # 字数不足
            "sections": [],  # 章节不足
        }
        
        result = agent._check_completeness(report, agent.DEFAULT_STANDARDS)
        
        assert result["passed"] is False
        assert len(result["issues"]) > 0
    
    def test_calculate_score(self):
        """测试质量评分计算."""
        agent = QualityCheckAgent("test_001", "测试")
        
        check_details = {
            "completeness": {"passed": True},
            "accuracy": {"passed": True},
        }
        
        score = agent._calculate_score(check_details, 0)
        
        assert score > 80  # 全部通过应该高分
    
    def test_execute(self):
        """测试质量检查执行."""
        agent = QualityCheckAgent("test_001", "测试")
        
        result = agent.run({
            "report": {
                "title": "测试报告",
                "content": "测试内容...",
                "sections": [{"title": "执行摘要"}, {"title": "第一章"}],
                "word_count": 1500,
            },
        })
        
        assert result["success"] is True
        assert "quality_score" in result
        assert "passed" in result


class TestDataCollectionAgent:
    """测试数据收集Agent."""
    
    def test_initialization(self):
        """测试Agent初始化."""
        agent = DataCollectionAgent("test_001", "测试数据员")
        
        assert "网页搜索" in agent.capabilities
    
    def test_execute(self):
        """测试数据收集."""
        agent = DataCollectionAgent("test_001", "测试")
        
        result = agent.run({
            "query": "储能行业市场规模",
            "max_results": 5,
        })
        
        assert result["success"] is True
        assert "data" in result
        assert "statistics" in result
    
    def test_deduplicate_data(self):
        """测试数据去重."""
        agent = DataCollectionAgent("test_001", "测试")
        
        data = [
            {"title": "文章1", "url": "http://example.com/1"},
            {"title": "文章1", "url": "http://example.com/1"},  # 重复
            {"title": "文章2", "url": "http://example.com/2"},
        ]
        
        result = agent._deduplicate_data(data)
        
        assert len(result) == 2


class TestLayoutDesignAgent:
    """测试排版设计Agent."""
    
    def test_initialization(self):
        """测试Agent初始化."""
        agent = LayoutDesignAgent("test_001", "测试排版员")
        
        assert "Word文档生成" in agent.capabilities
    
    def test_validate_input_unsupported_format(self):
        """测试输入验证 - 不支持的格式."""
        agent = LayoutDesignAgent("test_001", "测试")
        
        valid, error = agent.validate_input({
            "content": "测试",
            "output_format": "pptx",  # 不支持的格式
        })
        
        assert valid is False
        assert "pptx" in error
    
    def test_markdown_to_html(self):
        """测试Markdown转HTML."""
        agent = LayoutDesignAgent("test_001", "测试")
        
        markdown = "# 标题\n\n正文内容"
        html = agent._markdown_to_html(markdown)
        
        assert "<h1>" in html
        assert "标题" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
