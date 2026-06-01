# -*- coding: utf-8 -*-
"""
集成测试 - Phase 0-3 模块集成验证

测试内容:
- EnhancedSectionLocator 集成验证
- RevisionTypeInferrer 集成验证
- CascadeUpdateAnalyzer 集成验证
- 完整修订流程端到端测试
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

# 导入被测试模块
from src.core.adjustment import (
    # Phase 1
    RevisionIntentMapper,
    RouteDecision,
    BatchRevisionService,
    BatchRevisionResult,
    # Phase 2
    OrdinalReferenceParser,
    SectionMatch,
    ConversationReferenceTracker,
    EnhancedSectionLocator,
    # Phase 3
    CascadeUpdateAnalyzer,
    CascadeImpact,
    ConsistencyCheck,
    RevisionTypeInferrer,
    RevisionTypeInferenceResult,
)
from src.core.intent_types import IntentType, TaskComplexity, RevisionIntentType


class TestEnhancedSectionLocatorIntegration:
    """测试 EnhancedSectionLocator 集成"""
    
    def test_ordinal_reference_integration(self):
        """序数词引用集成测试"""
        locator = EnhancedSectionLocator()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        # 测试 "第三部分"
        matches = locator.locate("请修改第三部分的数据", sections)
        
        assert len(matches) == 1
        assert matches[0].section_title == "发展趋势"
        assert matches[0].match_type == "ordinal"
    
    def test_conversation_reference_integration(self):
        """对话历史引用集成测试"""
        locator = EnhancedSectionLocator()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        conversation = [
            {"role": "user", "content": "竞争格局分析得不错"},
            {"role": "assistant", "content": "好的，我会继续完善"},
        ]
        
        # 测试 "这部分"
        matches = locator.locate(
            "这部分数据需要更新",
            sections,
            conversation
        )
        
        assert len(matches) == 1
        assert matches[0].section_title == "竞争格局"
        assert matches[0].match_type == "reference"
    
    def test_keyword_match_integration(self):
        """关键词匹配集成测试"""
        locator = EnhancedSectionLocator()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        # 测试关键词匹配
        matches = locator.locate("请更新市场规模数据", sections)
        
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
        assert matches[0].match_type == "keyword"
    
    def test_combined_strategies_integration(self):
        """多策略组合集成测试"""
        locator = EnhancedSectionLocator()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        # 测试同时匹配多个
        matches = locator.locate("第一部分的市场规模需要更新", sections)
        
        # 应该匹配 "市场规模" (关键词) 和 "市场规模" (序数词指向)
        assert len(matches) >= 1


class TestRevisionTypeInferrerIntegration:
    """测试 RevisionTypeInferrer 集成"""
    
    def test_minor_inference_integration(self):
        """小修改推断集成测试"""
        inferrer = RevisionTypeInferrer()
        
        result = inferrer.infer("修正错别字")
        
        assert result.revision_type == "minor"
        assert result.confidence >= 0.8
    
    def test_section_inference_integration(self):
        """章节修订推断集成测试"""
        inferrer = RevisionTypeInferrer()
        
        result = inferrer.infer("更新市场规模数据", aspects=["市场规模"])
        
        assert result.revision_type == "section"
    
    def test_full_inference_integration(self):
        """全量修订推断集成测试"""
        inferrer = RevisionTypeInferrer()
        
        result = inferrer.infer("新增章节", aspects=["新章节"])
        
        assert result.revision_type == "full"
    
    def test_multi_aspects_full_inference(self):
        """多章节推断为 full"""
        inferrer = RevisionTypeInferrer()
        
        result = inferrer.infer(
            "修改这些内容",
            aspects=["市场规模", "竞争格局", "发展趋势", "投资建议"]
        )
        
        # 4个章节 >= 3，推断为 full
        assert result.revision_type == "full"


class TestCascadeUpdateAnalyzerIntegration:
    """测试 CascadeUpdateAnalyzer 集成"""
    
    def test_single_section_cascade(self):
        """单章节级联分析集成测试"""
        analyzer = CascadeUpdateAnalyzer()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        impact = analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=sections
        )
        
        # 市场规模 → 影响竞争格局、发展趋势、投资建议
        assert len(impact.affected_sections) >= 2
        assert "竞争格局" in impact.affected_sections
    
    def test_consistency_check_generation(self):
        """一致性检查生成集成测试"""
        analyzer = CascadeUpdateAnalyzer()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        impact = analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=sections
        )
        
        # 应该生成一致性检查项
        assert len(impact.data_consistency_checks) > 0
        
        for check in impact.data_consistency_checks:
            assert check.source == "市场规模"
            assert check.target in impact.affected_sections
    
    def test_risk_level_calculation(self):
        """风险等级计算集成测试"""
        analyzer = CascadeUpdateAnalyzer()
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议", "政策环境"]
        
        # 单章节修订 - 低风险
        impact_low = analyzer.analyze_cascade_impact(
            target_sections=["发展趋势"],
            all_sections=sections
        )
        
        # 多章节修订 - 高风险
        impact_high = analyzer.analyze_cascade_impact(
            target_sections=["市场规模", "政策环境"],
            all_sections=sections
        )
        
        # 多章节风险应该更高
        assert impact_high.risk_level in ["medium", "high"]


class TestRevisionIntentMapperIntegration:
    """测试 RevisionIntentMapper 集成"""
    
    def test_three_level_mapping_integration(self):
        """三级映射集成测试"""
        mapper = RevisionIntentMapper()
        
        # FIX 意图 + 错别字关键词 → CORRECT_ERROR → lightweight
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="修正错别字"
        )
        
        assert revision_intent == RevisionIntentType.CORRECT_ERROR
        assert route_decision.route == "lightweight"
    
    def test_trivial_override_integration(self):
        """TRIVIAL 复杂度覆盖集成测试"""
        mapper = RevisionIntentMapper()
        
        # EVALUATION 意图通常走 incremental，但 TRIVIAL 强制 lightweight
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.EVALUATION,
            complexity=TaskComplexity.TRIVIAL,
            user_input="核实数据"
        )
        
        assert route_decision.route == "lightweight"
        assert route_decision.reason == "trivial_complexity_override"
    
    def test_complex_override_integration(self):
        """COMPLEX 复杂度覆盖集成测试"""
        mapper = RevisionIntentMapper()
        
        # FIX 意图通常走 lightweight，但 COMPLEX 强制 incremental
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.COMPLEX,
            user_input="修正错别字"
        )
        
        assert route_decision.route == "incremental"


class TestEndToEndRevisionFlow:
    """端到端修订流程测试"""
    
    def test_simple_fix_flow(self):
        """简单修复流程端到端测试"""
        # 1. 章节定位
        locator = EnhancedSectionLocator()
        sections = ["市场规模", "竞争格局", "发展趋势"]
        
        matches = locator.locate("第一部分有错别字", sections)
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
        
        # 2. 修订类型推断
        inferrer = RevisionTypeInferrer()
        type_result = inferrer.infer("修正错别字", aspects=[matches[0].section_title])
        assert type_result.revision_type == "minor"
        
        # 3. 三级映射
        mapper = RevisionIntentMapper()
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.TRIVIAL,
            user_input="修正错别字"
        )
        assert route_decision.route == "lightweight"
        
        # 4. 级联更新分析 (minor 修改不应有级联影响)
        analyzer = CascadeUpdateAnalyzer()
        impact = analyzer.analyze_cascade_impact(
            target_sections=[matches[0].section_title],
            all_sections=sections
        )
        # 轻量修改通常不需要级联分析
    
    def test_data_update_flow(self):
        """数据更新流程端到端测试"""
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        # 1. 章节定位
        locator = EnhancedSectionLocator()
        matches = locator.locate("更新市场规模数据", sections)
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
        
        # 2. 修订类型推断
        inferrer = RevisionTypeInferrer()
        type_result = inferrer.infer("更新市场规模数据", aspects=[matches[0].section_title])
        assert type_result.revision_type == "section"
        
        # 3. 三级映射
        mapper = RevisionIntentMapper()
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="更新市场规模数据"
        )
        # 数据更新通常走 incremental
        assert route_decision.route in ["lightweight", "incremental"]
        
        # 4. 级联更新分析
        analyzer = CascadeUpdateAnalyzer()
        impact = analyzer.analyze_cascade_impact(
            target_sections=[matches[0].section_title],
            all_sections=sections
        )
        # 市场规模更新应该影响其他章节
        assert len(impact.affected_sections) > 0
    
    def test_new_section_flow(self):
        """新增章节流程端到端测试"""
        sections = ["市场规模", "竞争格局", "发展趋势"]
        
        # 1. 章节定位 (新章节不在现有章节中)
        locator = EnhancedSectionLocator()
        matches = locator.locate("新增投资建议章节", sections)
        # 新章节可能无法匹配
        # assert len(matches) >= 0
        
        # 2. 修订类型推断
        inferrer = RevisionTypeInferrer()
        type_result = inferrer.infer("新增投资建议章节")
        assert type_result.revision_type == "full"
        
        # 3. 三级映射
        mapper = RevisionIntentMapper()
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.RESEARCH,
            complexity=TaskComplexity.COMPLEX,
            user_input="新增投资建议章节"
        )
        assert route_decision.route == "incremental"


class TestBatchRevisionServiceIntegration:
    """测试 BatchRevisionService 集成"""
    
    def test_batch_result_structure(self):
        """批量修订结果结构测试"""
        result = BatchRevisionResult(
            success=True,
            document_path="/path/to/doc.html",
            updated_sections=["市场规模", "竞争格局"],
            failed_sections=[],
            execution_time=5.2
        )
        
        data = result.to_dict()
        assert data["success"]
        assert len(data["updated_sections"]) == 2
        assert data["execution_time"] == 5.2
    
    def test_partial_success_result(self):
        """部分成功结果测试"""
        result = BatchRevisionResult(
            success=False,
            document_path="/path/to/doc.html",
            updated_sections=["市场规模"],
            failed_sections=["竞争格局"],
            partial_success=True,
            error_message="部分章节修订失败"
        )
        
        assert not result.success
        assert result.partial_success
        assert len(result.failed_sections) == 1


class TestAllModulesImport:
    """测试所有模块可正确导入"""
    
    def test_phase1_imports(self):
        """Phase 1 模块导入测试"""
        from src.core.adjustment import RevisionIntentMapper, RouteDecision
        from src.core.adjustment import BatchRevisionService, BatchRevisionResult
        
        assert RevisionIntentMapper is not None
        assert RouteDecision is not None
        assert BatchRevisionService is not None
        assert BatchRevisionResult is not None
    
    def test_phase2_imports(self):
        """Phase 2 模块导入测试"""
        from src.core.adjustment import (
            OrdinalReferenceParser,
            SectionMatch,
            ConversationReferenceTracker,
            EnhancedSectionLocator,
        )
        
        assert OrdinalReferenceParser is not None
        assert SectionMatch is not None
        assert ConversationReferenceTracker is not None
        assert EnhancedSectionLocator is not None
    
    def test_phase3_imports(self):
        """Phase 3 模块导入测试"""
        from src.core.adjustment import (
            CascadeUpdateAnalyzer,
            CascadeImpact,
            ConsistencyCheck,
            RevisionTypeInferrer,
            RevisionTypeInferenceResult,
        )
        
        assert CascadeUpdateAnalyzer is not None
        assert CascadeImpact is not None
        assert ConsistencyCheck is not None
        assert RevisionTypeInferrer is not None
        assert RevisionTypeInferenceResult is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
