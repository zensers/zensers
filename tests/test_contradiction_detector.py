# -*- coding: utf-8 -*-
"""
测试矛盾检测器

测试范围：
- ContradictionDetector: 检测知识图谱中的矛盾
- 数值矛盾检测
- 关系矛盾检测
- 解决策略
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from src.core.memory.knowledge.contradiction_detector import (
    ContradictionDetector,
    Contradiction,
    ContradictionType,
    ResolutionStatus
)


class TestContradictionDataClass:
    """测试矛盾数据结构"""
    
    def test_contradiction_creation(self):
        """测试矛盾创建"""
        c = Contradiction(
            contradiction_id="contrad_001",
            entity_name="宁德时代",
            attribute="市场份额",
            contradiction_type=ContradictionType.NUMERIC,
            value_1="37%",
            source_1="财报A",
            value_2="45%",
            source_2="报告B"
        )
        
        assert c.contradiction_id == "contrad_001"
        assert c.entity_name == "宁德时代"
        assert c.attribute == "市场份额"
        assert c.contradiction_type == ContradictionType.NUMERIC
        assert c.resolution_status == ResolutionStatus.PENDING
    
    def test_contradiction_to_dict(self):
        """测试转换为字典"""
        c = Contradiction(
            contradiction_id="contrad_002",
            entity_name="比亚迪",
            attribute="营收",
            contradiction_type=ContradictionType.NUMERIC,
            value_1="5000亿",
            source_1="年报",
            value_2="4500亿",
            source_2="预估"
        )
        
        d = c.to_dict()
        
        assert d["contradiction_id"] == "contrad_002"
        assert d["entity_name"] == "比亚迪"
        assert d["contradiction_type"] == "numeric"
        assert d["resolution_status"] == "pending"


class TestContradictionDetector:
    """测试矛盾检测器"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def detector(self, temp_db):
        """创建检测器实例"""
        d = ContradictionDetector(temp_db, "test_user")
        yield d
        d.close()
    
    def test_init(self, detector, temp_db):
        """测试初始化"""
        assert Path(temp_db).exists()
        stats = detector.get_stats()
        assert stats["total"] == 0
    
    def test_parse_numeric_value_percentage(self, detector):
        """测试解析百分比数值"""
        assert detector._parse_numeric_value("37%") == 37.0
        assert detector._parse_numeric_value("15.5%") == 15.5
    
    def test_parse_numeric_value_billion(self, detector):
        """测试解析亿/万亿单位"""
        assert detector._parse_numeric_value("1.2万亿") == 12000.0
        assert detector._parse_numeric_value("500亿") == 500.0
    
    def test_parse_numeric_value_range(self, detector):
        """测试解析范围"""
        assert detector._parse_numeric_value("100-150") == 125.0
        assert detector._parse_numeric_value("10-20") == 15.0
    
    def test_parse_numeric_value_plain(self, detector):
        """测试解析纯数字"""
        assert detector._parse_numeric_value("123") == 123.0
        assert detector._parse_numeric_value("45.67") == 45.67
    
    def test_is_numeric_contradiction_within_tolerance(self, detector):
        """测试数值矛盾（容差内）"""
        fact1 = {"value": "100亿", "confidence": 0.8}
        fact2 = {"value": "105亿", "confidence": 0.8}
        
        # 5% 差异，在 10% 容差内，不是矛盾
        assert not detector._is_numeric_contradiction(fact1, fact2)
    
    def test_is_numeric_contradiction_exceeds_tolerance(self, detector):
        """测试数值矛盾（超出容差）"""
        fact1 = {"value": "100亿", "confidence": 0.8}
        fact2 = {"value": "120亿", "confidence": 0.8}
        
        # 20% 差异，超出 10% 容差，是矛盾
        assert detector._is_numeric_contradiction(fact1, fact2)
    
    def test_is_numeric_contradiction_different_units(self, detector):
        """测试不同单位的数值"""
        fact1 = {"value": "1.2万亿", "confidence": 0.8}
        fact2 = {"value": "12000亿", "confidence": 0.8}
        
        # 相同值，不是矛盾
        assert not detector._is_numeric_contradiction(fact1, fact2)
    
    def test_create_contradiction(self, detector):
        """测试创建矛盾记录"""
        fact1 = {
            "entity_name": "宁德时代",
            "attribute": "市场份额",
            "value": "37%",
            "source": "财报A",
            "as_of": "2024-Q3",
            "confidence": 0.9
        }
        fact2 = {
            "entity_name": "宁德时代",
            "attribute": "市场份额",
            "value": "45%",
            "source": "报告B",
            "as_of": "2024-Q3",
            "confidence": 0.7
        }
        
        c = detector._create_contradiction(fact1, fact2, ContradictionType.NUMERIC)
        
        assert c.entity_name == "宁德时代"
        assert c.attribute == "市场份额"
        assert c.value_1 == "37%"
        assert c.value_2 == "45%"
        assert c.confidence_diff == 0.2
    
    def test_save_and_retrieve_contradiction(self, detector):
        """测试保存和检索矛盾"""
        c = Contradiction(
            contradiction_id="contrad_test",
            entity_name="测试公司",
            attribute="营收",
            contradiction_type=ContradictionType.NUMERIC,
            value_1="100亿",
            source_1="来源A",
            value_2="150亿",
            source_2="来源B"
        )
        
        detector._save_contradiction(c)
        
        # 检索待解决的矛盾
        pending = detector._get_pending_contradictions()
        
        assert len(pending) == 1
        assert pending[0].contradiction_id == "contrad_test"
    
    def test_resolve_contradiction(self, detector):
        """测试解决矛盾"""
        c = Contradiction(
            contradiction_id="contrad_resolve",
            entity_name="测试公司",
            attribute="利润",
            contradiction_type=ContradictionType.NUMERIC,
            value_1="10亿",
            source_1="来源A",
            value_2="15亿",
            source_2="来源B"
        )
        
        detector._save_contradiction(c)
        
        # 解决矛盾
        detector.resolve_contradiction(
            "contrad_resolve",
            ResolutionStatus.RESOLVED,
            "采用来源A的数据"
        )
        
        # 检查已解决
        pending = detector._get_pending_contradictions()
        assert len(pending) == 0
        
        stats = detector.get_stats()
        assert stats["resolved"] == 1
    
    def test_get_resolution_suggestion(self, detector):
        """测试获取解决建议"""
        c = Contradiction(
            contradiction_id="contrad_suggest",
            entity_name="测试公司",
            attribute="增长率",
            contradiction_type=ContradictionType.NUMERIC,
            value_1="20%",
            source_1="官方数据",
            value_2="35%",
            source_2="第三方报告",
            as_of_1="2024-Q3",
            as_of_2="2024-Q2",
            confidence_diff=0.3
        )
        
        suggestion = detector.get_resolution_suggestion(c)
        
        assert suggestion["contradiction_id"] == "contrad_suggest"
        assert suggestion["type"] == "numeric"
        assert suggestion["recommendation"] is not None
        assert len(suggestion["options"]) == 4
    
    def test_get_stats(self, detector):
        """测试统计信息"""
        # 创建多个矛盾
        for i in range(3):
            c = Contradiction(
                contradiction_id=f"contrad_stat_{i}",
                entity_name=f"公司{i}",
                attribute="营收",
                contradiction_type=ContradictionType.NUMERIC,
                value_1=f"{100+i*10}亿",
                source_1="来源A",
                value_2=f"{150+i*10}亿",
                source_2="来源B"
            )
            detector._save_contradiction(c)
        
        stats = detector.get_stats()
        
        assert stats["total"] == 3
        assert stats["pending"] == 3


class TestContradictionDetectionIntegration:
    """集成测试"""
    
    def test_detect_from_temporal_db(self):
        """测试从时间知识库检测矛盾"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建时间知识库
            temporal_db_path = Path(tmpdir) / "temporal.db"
            contradiction_db_path = Path(tmpdir) / "contradictions.db"
            
            # 初始化时间知识库
            from src.core.memory.knowledge import TemporalKnowledge
            temporal = TemporalKnowledge(str(temporal_db_path), "test_user")
            
            # 存储有矛盾的事实
            temporal.store_fact(
                entity_name="宁德时代",
                attribute="市场份额",
                value="37%",
                as_of="2024-Q3",
                source="财报A",
                confidence=0.9
            )
            
            temporal.store_fact(
                entity_name="宁德时代",
                attribute="市场份额",
                value="45%",
                as_of="2024-Q3",
                source="报告B",
                confidence=0.7
            )
            
            # 检测矛盾
            detector = ContradictionDetector(
                str(contradiction_db_path),
                "test_user"
            )
            
            contradictions = detector.detect_contradictions(str(temporal_db_path))
            
            # 应该检测到矛盾
            assert len(contradictions) >= 1
            
            temporal.close()
            detector.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])