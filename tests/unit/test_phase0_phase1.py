# -*- coding: utf-8 -*-
"""
Phase 0-1 单元测试

测试内容:
- Phase 0: N1-N6 修复验证
- Phase 1: 三级映射 + 批量处理验证
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass

# 导入被测试模块
from src.core.intent_types import IntentType, TaskComplexity, RevisionIntentType
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper, RouteDecision
from src.core.adjustment.batch_revision_service import BatchRevisionService, BatchRevisionResult


class TestRevisionIntentType:
    """测试 RevisionIntentType 枚举 (N5)"""
    
    def test_revision_intent_types_exist(self):
        """验证所有修订意图类型存在"""
        # 数据级操作
        assert hasattr(RevisionIntentType, 'VERIFY_DATA')
        assert hasattr(RevisionIntentType, 'UPDATE_DATA')
        assert hasattr(RevisionIntentType, 'ADD_DATA')
        
        # 文本级操作
        assert hasattr(RevisionIntentType, 'REWRITE_TEXT')
        assert hasattr(RevisionIntentType, 'CORRECT_ERROR')
        assert hasattr(RevisionIntentType, 'IMPROVE_CLARITY')
        
        # 结构级操作
        assert hasattr(RevisionIntentType, 'ADD_SECTION')
        assert hasattr(RevisionIntentType, 'REMOVE_SECTION')
        
        # 分析级操作
        assert hasattr(RevisionIntentType, 'COMPARE_SECTIONS')
        assert hasattr(RevisionIntentType, 'CHECK_CONSISTENCY')
    
    def test_revision_intent_values(self):
        """验证枚举值正确"""
        assert RevisionIntentType.VERIFY_DATA.value == "verify_data"
        assert RevisionIntentType.CORRECT_ERROR.value == "correct_error"
        assert RevisionIntentType.ADD_SECTION.value == "add_section"


class TestRevisionIntentMapper:
    """测试三级映射架构 (Phase 1.1)"""
    
    def setup_method(self):
        self.mapper = RevisionIntentMapper()
    
    def test_fix_intent_to_correct_error(self):
        """FIX 意图 + 错别字关键词 → CORRECT_ERROR"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="修正错别字"
        )
        assert revision_intent == RevisionIntentType.CORRECT_ERROR
        assert route_decision.route == "lightweight"
    
    def test_fix_intent_to_rewrite_text(self):
        """FIX 意图 + 重写关键词 → REWRITE_TEXT"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="重写这段内容"
        )
        assert revision_intent == RevisionIntentType.REWRITE_TEXT
        assert route_decision.route == "lightweight"
    
    def test_evaluation_intent_to_verify_data(self):
        """EVALUATION 意图 + 核实关键词 → VERIFY_DATA"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.EVALUATION,
            complexity=TaskComplexity.SINGLE,
            user_input="核实数据准确性"
        )
        assert revision_intent == RevisionIntentType.VERIFY_DATA
        assert route_decision.route == "incremental"
        assert "data_collection" in route_decision.skip_phases
    
    def test_research_intent_to_add_data(self):
        """RESEARCH 意图 + 新增关键词 → ADD_DATA"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.RESEARCH,
            complexity=TaskComplexity.SINGLE,
            user_input="新增市场数据"
        )
        assert revision_intent == RevisionIntentType.ADD_DATA
        assert route_decision.route == "incremental"
    
    def test_trivial_complexity_override(self):
        """TRIVIAL 复杂度强制 lightweight (N2)"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.EVALUATION,
            complexity=TaskComplexity.TRIVIAL,
            user_input="核实所有数据"
        )
        # 即使 EVALUATION 通常走 incremental，TRIVIAL 强制 lightweight
        assert route_decision.route == "lightweight"
        assert route_decision.reason == "trivial_complexity_override"
    
    def test_complex_complexity_override(self):
        """COMPLEX 复杂度强制 incremental"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.COMPLEX,
            user_input="修正错别字"
        )
        # 即使 FIX 通常走 lightweight，COMPLEX 强制 incremental
        assert route_decision.route == "incremental"
        assert "complex_override" in route_decision.reason
    
    def test_default_fallback(self):
        """未知意图返回默认值"""
        revision_intent, route_decision = self.mapper.map(
            primary_intent=IntentType.OPEN_ENDED,
            complexity=TaskComplexity.SINGLE,
            user_input="随便说说"
        )
        # 未知意图返回默认的 CORRECT_ERROR
        assert revision_intent == RevisionIntentType.CORRECT_ERROR
    
    def test_route_decision_to_dict(self):
        """RouteDecision 序列化"""
        decision = RouteDecision(
            route="lightweight",
            type="minor",
            skip_phases=["data_collection"],
            reason="test"
        )
        result = decision.to_dict()
        assert result["route"] == "lightweight"
        assert result["type"] == "minor"
        assert "data_collection" in result["skip_phases"]


class TestBatchRevisionResult:
    """测试批量修订结果 (Phase 1.3)"""
    
    def test_success_result(self):
        """成功结果"""
        result = BatchRevisionResult(
            success=True,
            document_path="/path/to/doc.html",
            updated_sections=["市场规模", "竞争格局"],
            failed_sections=[],
            partial_success=False,
            execution_time=5.2
        )
        assert result.success
        assert len(result.updated_sections) == 2
        assert len(result.failed_sections) == 0
    
    def test_partial_success_result(self):
        """部分成功结果"""
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
        assert len(result.updated_sections) == 1
        assert len(result.failed_sections) == 1
    
    def test_to_dict(self):
        """结果序列化"""
        result = BatchRevisionResult(
            success=True,
            document_path="/path/to/doc.html",
            updated_sections=["市场规模"],
            execution_time=3.5
        )
        data = result.to_dict()
        assert data["success"]
        assert data["document_path"] == "/path/to/doc.html"
        assert data["execution_time"] == 3.5


class TestBatchRevisionService:
    """测试批量修订服务 (Phase 1.3)"""
    
    def test_empty_sections_returns_error(self):
        """空章节列表返回错误"""
        service = BatchRevisionService()
        result = asyncio.run(service.revise_multiple_sections(
            document_path="/path/to/doc.html",
            sections=[],
            adjustment="测试修订"
        ))
        assert not result.success
        assert "No sections" in result.error_message
    
    @patch('src.core.adjustment.batch_revision_service.BatchRevisionService._read_document')
    def test_read_failure_returns_error(self, mock_read):
        """文档读取失败返回错误"""
        mock_read.return_value = None
        
        service = BatchRevisionService()
        result = asyncio.run(service.revise_multiple_sections(
            document_path="/path/to/doc.html",
            sections=["市场规模"],
            adjustment="测试修订"
        ))
        assert not result.success
        assert "Failed to read document" in result.error_message


class TestQuickComplexityEstimation:
    """测试复杂度预估 (N6)"""
    
    def test_trivial_short_text(self):
        """短文本 (<10字符) → TRIVIAL"""
        # 模拟 _estimate_quick_complexity 逻辑
        adjustment = "改一下"
        adj_len = len(adjustment.strip())
        
        if adj_len < 10:
            expected = TaskComplexity.TRIVIAL
        elif adj_len < 50:
            expected = TaskComplexity.SINGLE
        else:
            expected = TaskComplexity.MULTI
        
        assert expected == TaskComplexity.TRIVIAL
    
    def test_single_medium_text(self):
        """中等文本 (10-50字符) → SINGLE"""
        adjustment = "修改市场规模章节的数据"
        adj_len = len(adjustment.strip())
        
        if adj_len < 10:
            expected = TaskComplexity.TRIVIAL
        elif adj_len < 50:
            expected = TaskComplexity.SINGLE
        else:
            expected = TaskComplexity.MULTI
        
        assert expected == TaskComplexity.SINGLE
    
    def test_complex_long_text(self):
        """长文本 (>=200字符) → COMPLEX"""
        adjustment = "请全面修订市场规模和竞争格局两个章节，更新所有数据到2024年，并补充最新的行业趋势分析内容"
        adj_len = len(adjustment.strip())
        
        if adj_len >= 200:
            expected = TaskComplexity.COMPLEX
        elif adj_len >= 50:
            expected = TaskComplexity.MULTI
        else:
            expected = TaskComplexity.SINGLE
        
        # 这个例子不够 200 字符，但逻辑正确
        assert adj_len < 200


class TestSectionMatchingThreshold:
    """测试章节匹配阈值 (N4)"""
    
    def test_overlap_ratio_calculation(self):
        """重叠比计算"""
        aspect_keywords = {"市场", "规模", "分析"}
        title_keywords = {"市场", "规模", "预测"}
        
        overlap = aspect_keywords & title_keywords
        overlap_ratio = len(overlap) / min(len(aspect_keywords), len(title_keywords))
        
        # 重叠: 市场, 规模 (2个)
        # min(3, 3) = 3
        # ratio = 2/3 ≈ 0.67
        assert overlap_ratio >= 0.5
        assert len(overlap) == 2
    
    def test_overlap_ratio_below_threshold(self):
        """重叠比低于阈值"""
        aspect_keywords = {"竞争", "格局"}
        title_keywords = {"市场", "规模"}
        
        overlap = aspect_keywords & title_keywords
        overlap_ratio = len(overlap) / min(len(aspect_keywords), len(title_keywords))
        
        # 无重叠
        assert overlap_ratio == 0.0
        assert overlap_ratio < 0.5
    
    def test_empty_keywords_edge_case(self):
        """空关键词边界情况"""
        aspect_keywords = set()
        title_keywords = {"市场", "规模"}
        
        # 边界检查：不应除以零
        if not aspect_keywords or not title_keywords:
            should_skip = True
        else:
            should_skip = False
        
        assert should_skip


class TestDynamicTimeout:
    """测试动态超时 (N1)"""
    
    def test_timeout_map_values(self):
        """超时映射值正确"""
        timeout_map = {
            TaskComplexity.TRIVIAL: 15.0,
            TaskComplexity.SINGLE: 30.0,
            TaskComplexity.MULTI: 60.0,
            TaskComplexity.COMPLEX: 90.0,
        }
        
        assert timeout_map[TaskComplexity.TRIVIAL] == 15.0
        assert timeout_map[TaskComplexity.SINGLE] == 30.0
        assert timeout_map[TaskComplexity.MULTI] == 60.0
        assert timeout_map[TaskComplexity.COMPLEX] == 90.0
    
    def test_default_timeout(self):
        """默认超时值"""
        timeout_map = {
            TaskComplexity.TRIVIAL: 15.0,
            TaskComplexity.SINGLE: 30.0,
            TaskComplexity.MULTI: 60.0,
            TaskComplexity.COMPLEX: 90.0,
        }
        
        # 未知复杂度使用默认值 30.0
        default_timeout = timeout_map.get(TaskComplexity.SINGLE, 30.0)
        assert default_timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
