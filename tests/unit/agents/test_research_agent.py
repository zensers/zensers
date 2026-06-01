"""
ResearchAgent 研究Agent基类测试

为市场分析、竞争分析等研究类Agent提供基础功能
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from src.core.agents.base import BaseAgent, AgentState
from src.agents.research import ResearchAgent, Finding


class TestResearchAgentInitialization:
    """测试ResearchAgent初始化"""
    
    def test_research_agent_init(self):
        """测试基本初始化"""
        agent = ResearchAgent(
            agent_id="research_001",
            name="MarketAnalyst",
            research_domain="market_analysis"
        )
        assert agent.agent_id == "research_001"
        assert agent.research_domain == "market_analysis"
        assert agent.status == "idle"
    
    def test_research_agent_default_values(self):
        """测试默认值"""
        agent = ResearchAgent(agent_id="research_002")
        assert agent.data_sources == []
        assert agent.findings == []


class TestDataCollection:
    """测试数据收集功能"""
    
    def test_collect_data_from_sources(self):
        """测试从数据源收集数据"""
        agent = ResearchAgent(agent_id="research_001")
        agent.add_data_source({"id": "source_001", "name": "TestSource"})
        
        with patch.object(agent, '_fetch_from_source') as mock_fetch:
            mock_fetch.return_value = [{"data": "test"}]
            result = agent.collect_data({"query": "test"})
        
        assert len(result) > 0
    
    def test_collect_data_with_filters(self):
        """测试带过滤条件的数据收集"""
        agent = ResearchAgent(agent_id="research_001")
        
        filters = {
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "region": "中国"
        }
        
        with patch.object(agent, '_fetch_from_source') as mock_fetch:
            mock_fetch.return_value = [{"date": "2024-06-01", "region": "中国"}]
            result = agent.collect_data({"query": "test"}, filters=filters)
        
        assert all(r["region"] == "中国" for r in result)


class TestDataAnalysis:
    """测试数据分析功能"""
    
    def test_analyze_data_structure(self):
        """测试数据结构分析"""
        agent = ResearchAgent(agent_id="research_001")
        
        raw_data = [
            {"company": "A", "revenue": 100},
            {"company": "B", "revenue": 200}
        ]
        
        analysis = agent.analyze_data(raw_data)
        
        assert "summary" in analysis
        assert "metrics" in analysis
    
    def test_extract_key_findings(self):
        """测试提取关键发现"""
        agent = ResearchAgent(agent_id="research_001")
        
        analysis = {
            "summary": {"total_items": 2, "fields": {"company": 2, "revenue": 2}},
            "metrics": {
                "revenue": {"count": 2, "min": 100, "max": 200, "avg": 150}
            }
        }
        
        findings = agent.extract_findings(analysis)
        
        assert len(findings) > 0
        assert all(f.confidence > 0 for f in findings)


class TestFindingManagement:
    """测试发现管理"""
    
    def test_add_finding(self):
        """测试添加发现"""
        agent = ResearchAgent(agent_id="research_001")
        
        finding = {
            "type": "market_size",
            "value": "1000亿",
            "confidence": 0.9,
            "source": "report_001"
        }
        
        agent.add_finding(finding)
        
        assert len(agent.findings) == 1
        assert agent.findings[0].value == "1000亿"
    
    def test_get_findings_by_type(self):
        """测试按类型获取发现"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_finding({"type": "market_size", "value": "1000亿"})
        agent.add_finding({"type": "growth_rate", "value": "15%"})
        agent.add_finding({"type": "market_size", "value": "1200亿"})
        
        market_findings = agent.get_findings_by_type("market_size")
        
        assert len(market_findings) == 2
    
    def test_validate_findings(self):
        """测试验证发现"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_finding({
            "type": "market_size",
            "value": "1000亿",
            "confidence": 0.9,
            "source": "official_report"
        })
        
        validation = agent.validate_findings()
        
        assert validation["total"] == 1
        assert validation["valid"] == 1


class TestSourceManagement:
    """测试数据源管理"""
    
    def test_add_data_source(self):
        """测试添加数据源"""
        agent = ResearchAgent(agent_id="research_001")
        
        source = {
            "id": "source_001",
            "name": "Wind",
            "type": "financial_data",
            "priority": 1
        }
        
        agent.add_data_source(source)
        
        assert len(agent.data_sources) == 1
    
    def test_get_sources_by_priority(self):
        """测试按优先级获取数据源"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_data_source({"id": "s1", "priority": 2})
        agent.add_data_source({"id": "s2", "priority": 1})
        agent.add_data_source({"id": "s3", "priority": 3})
        
        sources = agent.get_sources_by_priority()
        
        assert sources[0].source_id == "s2"  # priority 1 first


class TestReportGeneration:
    """测试报告生成"""
    
    def test_generate_section(self):
        """测试生成章节内容"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_finding({"type": "market_size", "value": "1000亿", "confidence": 0.9})
        agent.add_finding({"type": "growth_rate", "value": "15%", "confidence": 0.85})
        
        section = agent.generate_section("市场规模分析")
        
        assert "title" in section
        assert "content" in section
        assert "findings" in section
    
    def test_generate_summary(self):
        """测试生成摘要"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_finding({"type": "key_point", "value": "市场规模达1000亿", "confidence": 0.9})
        
        summary = agent.generate_summary()
        
        assert len(summary) > 0


class TestConfidenceScoring:
    """测试置信度评分"""
    
    def test_calculate_confidence_with_source_tier(self):
        """测试基于数据源等级的置信度计算"""
        agent = ResearchAgent(agent_id="research_001")
        
        # Tier 1 source (government)
        finding1 = {"source_tier": 1, "cross_verified": True}
        
        # Tier 3 source (blog)
        finding2 = {"source_tier": 3, "cross_verified": False}
        
        conf1 = agent.calculate_confidence(finding1)
        conf2 = agent.calculate_confidence(finding2)
        
        assert conf1 > conf2
    
    def test_confidence_threshold_filtering(self):
        """测试置信度阈值过滤"""
        agent = ResearchAgent(agent_id="research_001")
        
        agent.add_finding({"type": "test", "confidence": 0.9})
        agent.add_finding({"type": "test", "confidence": 0.5})
        agent.add_finding({"type": "test", "confidence": 0.3})
        
        high_conf = agent.get_findings_with_min_confidence(0.8)
        
        assert len(high_conf) == 1


class TestErrorHandling:
    """测试错误处理"""
    
    def test_handle_source_failure(self):
        """测试数据源失败处理"""
        agent = ResearchAgent(agent_id="research_001")
        agent.add_data_source({"id": "s1", "name": "Test"})
        
        with patch.object(agent, '_fetch_from_source') as mock_fetch:
            mock_fetch.side_effect = Exception("Source unavailable")
            result = agent.collect_data({"query": "test"})
        
        # Should return empty list or partial results
        assert isinstance(result, list)
    
    def test_handle_invalid_data(self):
        """测试无效数据处理"""
        agent = ResearchAgent(agent_id="research_001")
        
        invalid_data = [
            {"name": "A", "revenue": -100},  # Invalid negative revenue
            {"name": "B", "revenue": 200}
        ]
        
        cleaned = agent.clean_data(invalid_data)
        
        assert len(cleaned) == 1  # Invalid entry removed


class TestIntegration:
    """测试完整流程"""
    
    def test_full_research_workflow(self):
        """测试完整研究流程"""
        agent = ResearchAgent(agent_id="research_001")
        
        # 1. 设置数据源
        agent.add_data_source({"id": "s1", "priority": 1, "name": "TestSource"})
        
        # 2. 收集数据
        with patch.object(agent, '_fetch_from_source') as mock_fetch:
            mock_fetch.return_value = [{"value": 100, "name": "test"}]
            raw_data = agent.collect_data({"query": "test"})
        
        # 3. 分析数据
        analysis = agent.analyze_data(raw_data)
        
        # 4. 提取发现
        findings = agent.extract_findings(analysis)
        for f in findings:
            agent.add_finding(f.to_dict())
        
        # 5. 生成报告
        section = agent.generate_section("分析结果")
        
        assert section is not None
        assert len(agent.findings) >= 0
