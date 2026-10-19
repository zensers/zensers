# -*- coding: utf-8 -*-
"""
AdjustmentHandler 测试
=======================

测试文档调整功能：
1. 全局调整
2. 章节调整
3. 元素调整
4. 调整历史
"""

import pytest
import tempfile
import os
from datetime import datetime


class TestAdjustmentHandlerInit:
    """测试 AdjustmentHandler 初始化"""
    
    def test_handler_initialization(self):
        """测试处理器初始化"""
        from src.core.adjustment.adjustment_handler import AdjustmentHandler
        
        handler = AdjustmentHandler()
        
        assert handler is not None


class TestAdjustmentHandlerTypes:
    """测试调整类型"""
    
    @pytest.fixture
    def handler(self):
        from src.core.adjustment.adjustment_handler import AdjustmentHandler
        return AdjustmentHandler()
    
    def test_global_adjustment(self, handler):
        """测试全局调整"""
        result = handler.apply_adjustment(
            document_content={"title": "报告", "sections": []},
            adjustment_type="global",
            adjustment={"style": {"font": "Arial", "size": 12}}
        )
        
        assert result is not None
        assert result.success is True
    
    def test_section_adjustment(self, handler):
        """测试章节调整"""
        document = {
            "title": "报告",
            "sections": [
                {"id": "s1", "title": "第一章", "content": "内容"}
            ]
        }
        
        result = handler.apply_adjustment(
            document_content=document,
            adjustment_type="section",
            target="s1",
            adjustment={"title": "第一章（修订）"}
        )
        
        assert result is not None
    
    def test_element_adjustment(self, handler):
        """测试元素调整"""
        document = {
            "title": "报告",
            "sections": [
                {"id": "s1", "tables": [{"id": "t1", "data": []}]}
            ]
        }
        
        result = handler.apply_adjustment(
            document_content=document,
            adjustment_type="element",
            target="t1",
            adjustment={"style": {"border": "solid"}}
        )
        
        assert result is not None


class TestAdjustmentHandlerValidation:
    """测试调整验证"""
    
    @pytest.fixture
    def handler(self):
        from src.core.adjustment.adjustment_handler import AdjustmentHandler
        return AdjustmentHandler()
    
    def test_invalid_adjustment_type(self, handler):
        """测试无效调整类型"""
        result = handler.apply_adjustment(
            document_content={"title": "报告"},
            adjustment_type="invalid_type",
            adjustment={}
        )
        
        assert result.success is False
    
    def test_missing_target(self, handler):
        """测试缺少目标"""
        result = handler.apply_adjustment(
            document_content={"sections": []},
            adjustment_type="section",
            adjustment={"title": "新标题"}
        )
        
        # section类型需要target
        assert result.success is False or result.error is not None


class TestAdjustmentHandlerHistory:
    """测试调整历史"""
    
    @pytest.fixture
    def handler(self):
        from src.core.adjustment.adjustment_handler import AdjustmentHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            yield AdjustmentHandler(history_dir=tmpdir)
    
    def test_adjustment_history(self, handler):
        """测试调整历史记录"""
        handler.apply_adjustment(
            document_content={"title": "报告"},
            adjustment_type="global",
            adjustment={"style": {}},
            task_id="research_001"
        )
        
        history = handler.get_adjustment_history("research_001")
        
        assert len(history) == 1
    
    def test_multiple_adjustments(self, handler):
        """测试多次调整"""
        for i in range(3):
            handler.apply_adjustment(
                document_content={"title": f"报告{i}"},
                adjustment_type="global",
                adjustment={"style": {}},
                task_id="research_001"
            )
        
        history = handler.get_adjustment_history("research_001")
        
        assert len(history) == 3


class TestAdjustmentHandlerResult:
    """测试调整结果"""
    
    @pytest.fixture
    def handler(self):
        from src.core.adjustment.adjustment_handler import AdjustmentHandler
        return AdjustmentHandler()
    
    def test_result_has_content(self, handler):
        """测试结果包含内容"""
        result = handler.apply_adjustment(
            document_content={"title": "报告", "sections": []},
            adjustment_type="global",
            adjustment={"style": {"font": "Arial"}}
        )
        
        if result.success:
            assert result.adjusted_content is not None
    
    def test_result_has_adjustment_id(self, handler):
        """测试结果包含调整ID"""
        result = handler.apply_adjustment(
            document_content={"title": "报告"},
            adjustment_type="global",
            adjustment={}
        )
        
        if result.success:
            assert result.adjustment_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
