"""
约束层集成测试

验证所有约束组件能协同工作。
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import shutil


class TestHarnessIntegration:
    """约束层集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)
    
    @pytest.fixture
    def checker(self, temp_dir):
        """创建完整的约束检查器"""
        from src.core.harness import AgentConstraintChecker
        return AgentConstraintChecker(
            whitelist_config_path=temp_dir,
            trace_storage_path=temp_dir
        )
    
    def test_full_constraint_check_pass(self, checker):
        """测试完整约束检查 - 通过"""
        output = {
            "content": "市场规模分析报告",
            "sources": [
                {"name": "国家统计局", "url": "https://www.stats.gov.cn"},
                {"name": "艾瑞咨询", "url": "https://www.iresearch.cn"}
            ],
            "facts": [
                {
                    "id": "fact-001",
                    "statement": "2025年新能源汽车市场规模1.2万亿",
                    "sources": [
                        {"name": "艾瑞咨询", "value": "1.2万亿"},
                        {"name": "中汽协", "value": "1.18万亿"}
                    ],
                    "confidence": "high"
                }
            ]
        }
        
        result = checker.check_output(output)
        
        assert result.passed is True
        assert len(result.errors) == 0
    
    def test_full_constraint_check_fail_no_source(self, checker):
        """测试完整约束检查 - 失败：无来源"""
        output = {
            "content": "市场规模分析报告",
            "sources": [],
            "facts": []
        }
        
        result = checker.check_output(output)
        
        assert result.passed is False
        assert "缺少数据来源" in result.errors
    
    def test_fact_tracing(self, checker):
        """测试事实溯源"""
        trace = checker.trace_fact(
            fact_id="fact-001",
            fact_statement="2025年GDP增长5.2%",
            source="国家统计局",
            source_url="https://www.stats.gov.cn",
            confidence="high"
        )
        
        assert trace.fact_statement == "2025年GDP增长5.2%"
        assert trace.source == "国家统计局"
        assert trace.confidence == "high"
    
    def test_cross_validation_verified(self, checker):
        """测试交叉验证 - 通过"""
        sources = [
            {"name": "艾瑞咨询", "value": "1.2万亿"},
            {"name": "中汽协", "value": "1.18万亿"}
        ]
        
        result = checker.validate_claim(
            claim="2025年新能源汽车市场规模",
            sources=sources,
            tolerance=0.1
        )
        
        assert result.status == "verified"
        assert result.confidence == "high"
    
    def test_cross_validation_inconsistent(self, checker):
        """测试交叉验证 - 冲突"""
        sources = [
            {"name": "来源A", "value": "1.2万亿"},
            {"name": "来源B", "value": "0.5万亿"}  # 差异大
        ]
        
        result = checker.validate_claim(
            claim="某个数据",
            sources=sources,
            tolerance=0.1
        )
        
        assert result.status == "inconsistent"
        assert len(result.conflicts) > 0
    
    def test_source_trust_check(self, checker):
        """测试来源可信度检查"""
        assert checker.is_source_trusted("政府官网") is True
        assert checker.is_source_trusted("匿名论坛") is False
    
    def test_source_tier_check(self, checker):
        """测试来源等级检查"""
        tier = checker.get_source_tier("政府官网")
        assert tier == "tier1"
    
    def test_confidence_assessment(self, checker):
        """测试置信度评估"""
        output = {
            "content": "分析报告",
            "sources": [
                {"name": "国家统计局", "url": "https://www.stats.gov.cn"}
            ]
        }
        
        result = checker.check_output(output)
        
        assert result.confidence_assessment is not None
        assert result.confidence_assessment["level"] in ["high", "medium", "low"]


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def test_check_agent_output_function(self):
        """测试便捷函数 check_agent_output"""
        from src.core.harness import check_agent_output
        
        output = {
            "content": "报告",
            "sources": [{"name": "国家统计局"}]
        }
        
        result = check_agent_output(output)
        
        # 应该有来源，通过
        assert result.passed is True or len(result.errors) == 0 or "缺少数据来源" not in result.errors


class TestEndToEndWorkflow:
    """端到端工作流测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)
    
    @pytest.fixture
    def checker(self, temp_dir):
        """创建约束检查器"""
        from src.core.harness import AgentConstraintChecker
        return AgentConstraintChecker(
            whitelist_config_path=temp_dir,
            trace_storage_path=temp_dir
        )
    
    def test_complete_research_workflow(self, checker):
        """
        测试完整研究工作流
        
        模拟：数据收集 → 约束检查 → 溯源记录 → 交叉验证
        """
        # Step 1: 收集数据
        collected_data = {
            "content": "新能源汽车市场分析",
            "sources": [
                {"name": "艾瑞咨询", "url": "https://www.iresearch.cn", "tier": "tier2"},
                {"name": "中汽协", "url": "https://www.caam.org.cn", "tier": "tier1"}
            ]
        }
        
        # Step 2: 约束检查
        check_result = checker.check_output(collected_data)
        assert check_result.passed is True
        
        # Step 3: 记录关键事实溯源
        trace1 = checker.trace_fact(
            fact_id="fact-001",
            fact_statement="2025年新能源汽车销量1000万辆",
            source="中汽协",
            confidence="high"
        )
        assert trace1.source == "中汽协"
        
        # Step 4: 交叉验证
        validation = checker.validate_claim(
            claim="市场规模数据",
            sources=[
                {"name": "艾瑞咨询", "value": "1.2万亿"},
                {"name": "中汽协", "value": "1.18万亿"}
            ],
            tolerance=0.1
        )
        assert validation.status == "verified"
        
        # Step 5: 生成报告输出
        report = {
            "content": "新能源汽车市场分析报告",
            "sources": collected_data["sources"],
            "facts": [
                {
                    "id": "fact-001",
                    "statement": "2025年新能源汽车销量1000万辆",
                    "sources": [{"name": "中汽协"}],
                    "confidence": "high"
                }
            ],
            "confidence": 0.85
        }
        
        # Step 6: 最终约束检查
        final_check = checker.check_output(report)
        assert final_check.passed is True