# -*- coding: utf-8 -*-
"""
测试时间有效性追踪和来源追溯

测试范围：
- TemporalKnowledge: 时间有效性追踪
- ProvenanceStore: 来源追溯
- KnowledgeBank v2.0 集成
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta

from src.core.memory.knowledge import (
    TemporalKnowledge,
    TemporalFact,
    TemporalQuery,
    FactStatus,
    ProvenanceStore,
    SourceTrustLevel
)


class TestTemporalKnowledge:
    """测试时间有效性追踪"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def temporal(self, temp_db):
        """创建 TemporalKnowledge 实例"""
        tk = TemporalKnowledge(temp_db, "test_user")
        yield tk
        tk.close()
    
    def test_init(self, temporal):
        """测试初始化"""
        stats = temporal.get_stats()
        assert stats["total_facts"] == 0
        assert stats["total_entities"] == 0
    
    def test_store_fact(self, temporal):
        """测试存储事实"""
        fact_id = temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            as_of="2024-Q3",
            source="2024Q3财报"
        )
        
        assert fact_id.startswith("fact_")
        
        stats = temporal.get_stats()
        assert stats["total_facts"] == 1
        assert stats["total_entities"] == 1
    
    def test_get_value_latest(self, temporal):
        """测试获取最新值"""
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            as_of="2024-Q3",
            source="2024Q3财报"
        )
        
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="35%",
            as_of="2024-Q2",
            source="2024Q2财报"
        )
        
        # 获取最新值
        result = temporal.get_value("宁德时代", "市场份额")
        assert result is not None
        assert result["value"] == "37%"
        assert result["as_of"] == "2024-Q3"
    
    def test_get_value_at_time(self, temporal):
        """测试获取特定时间点的值"""
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            as_of="2024-Q3",
            source="2024Q3财报"
        )
        
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="35%",
            as_of="2024-Q2",
            source="2024Q2财报"
        )
        
        # 查询 Q2 的值
        result = temporal.get_value("宁德时代", "市场份额", as_of="2024-Q2")
        assert result is not None
        assert result["value"] == "35%"
    
    def test_get_history(self, temporal):
        """测试获取历史版本"""
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            as_of="2024-Q3",
            source="2024Q3财报"
        )
        
        temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="35%",
            as_of="2024-Q2",
            source="2024Q2财报"
        )
        
        history = temporal.get_history("宁德时代", "市场份额")
        assert len(history) == 2
        assert history[0]["as_of"] == "2024-Q3"  # 最新在前
    
    def test_auto_supersede(self, temporal):
        """测试自动取代旧值"""
        fact_id_1 = temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="35%",
            as_of="2024-Q2",
            source="2024Q2财报",
            auto_supersede=True
        )
        
        fact_id_2 = temporal.store_fact(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            as_of="2024-Q3",
            source="2024Q3财报",
            auto_supersede=True
        )
        
        # 检查旧事实被标记为 superseded
        history = temporal.get_history("宁德时代", "市场份额")
        assert len(history) == 2
        # 旧值应该被标记为 superseded
        old_fact = [f for f in history if f["fact_id"] == fact_id_1][0]
        assert old_fact["status"] == "superseded"
    
    def test_valid_from_until(self, temporal):
        """测试时间范围"""
        temporal.store_fact(
            entity_name="特斯拉",
            attribute="CEO",
            value="马斯克",
            as_of="2008",
            source="维基百科",
            valid_from="2008-01-01",
            valid_until="2024-01-01"
        )
        
        # 在有效期内
        result = temporal.get_value("特斯拉", "CEO", as_of="2020-01-01")
        assert result is not None
        assert result["value"] == "马斯克"
        
        # 超出有效期
        result = temporal.get_value("特斯拉", "CEO", as_of="2025-01-01")
        assert result is None
    
    def test_check_expired(self, temporal):
        """测试过期检测"""
        # 存储一个已经过期的事实
        past_date = (datetime.now() - timedelta(days=10)).isoformat()
        temporal.store_fact(
            entity_name="测试公司",
            attribute="状态",
            value="正常",
            as_of=past_date,
            source="测试",
            valid_until=past_date,
            auto_supersede=False
        )
        
        # 检测过期
        expired = temporal.check_expired()
        assert len(expired) == 1
        assert expired[0]["entity_name"] == "测试公司"


class TestProvenanceStore:
    """测试来源追溯"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def provenance(self, temp_db):
        """创建 ProvenanceStore 实例"""
        ps = ProvenanceStore(temp_db, "test_user")
        yield ps
        ps.close()
    
    def test_init(self, provenance):
        """测试初始化"""
        stats = provenance.get_stats()
        assert stats["total_provenance"] == 0
    
    def test_record_source(self, provenance):
        """测试记录来源"""
        prov_id = provenance.record_source(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            source_type="financial_report",
            source_ref="research/2024Q3_report.md",
            line_number=45,
            context="宁德时代2024Q3市场份额达到37%"
        )
        
        assert prov_id.startswith("prov_")
        
        stats = provenance.get_stats()
        assert stats["total_provenance"] == 1
    
    def test_get_sources(self, provenance):
        """测试获取来源"""
        provenance.record_source(
            entity_name="宁德时代",
            attribute="市场份额",
            value="37%",
            source_type="financial_report",
            source_ref="report_1.md"
        )
        
        provenance.record_source(
            entity_name="宁德时代",
            attribute="营收",
            value="1000亿",
            source_type="financial_report",
            source_ref="report_2.md"
        )
        
        # 获取特定属性的来源
        sources = provenance.get_sources("宁德时代", "市场份额")
        assert len(sources) == 1
        assert sources[0]["source_ref"] == "report_1.md"
        
        # 获取所有来源
        all_sources = provenance.get_sources("宁德时代")
        assert len(all_sources) == 2
    
    def test_trust_level(self, provenance):
        """测试信任等级"""
        # 官方来源
        prov_id_1 = provenance.record_source(
            entity_name="公司A",
            attribute="营收",
            value="100亿",
            source_type="official_report",
            source_ref="财报.pdf"
        )
        
        # 一般来源
        prov_id_2 = provenance.record_source(
            entity_name="公司B",
            attribute="营收",
            value="200亿",
            source_type="news_article",
            source_ref="新闻.html"
        )
        
        sources_1 = provenance.get_sources("公司A")
        assert sources_1[0]["trust_level"] == SourceTrustLevel.TIER1_OFFICIAL.value
        
        sources_2 = provenance.get_sources("公司B")
        assert sources_2[0]["trust_level"] == SourceTrustLevel.TIER3_GENERAL.value
    
    def test_verify_source(self, provenance):
        """测试验证来源"""
        prov_id = provenance.record_source(
            entity_name="测试",
            attribute="值",
            value="100",
            source_type="research",
            source_ref="test.md"
        )
        
        # 验证前
        sources = provenance.get_sources("测试")
        assert sources[0]["verified_at"] is None
        
        # 验证
        provenance.verify_source(prov_id, verified_by="user")
        
        # 验证后
        stats = provenance.get_stats()
        assert stats["verified_count"] == 1
    
    def test_get_trust_summary(self, provenance):
        """测试信任摘要"""
        provenance.record_source(
            entity_name="公司",
            attribute="营收",
            value="100亿",
            source_type="official_report",
            source_ref="财报.pdf"
        )
        
        provenance.record_source(
            entity_name="公司",
            attribute="利润",
            value="10亿",
            source_type="news_article",
            source_ref="新闻.html"
        )
        
        summary = provenance.get_trust_summary("公司")
        assert summary["total_sources"] == 2
        assert "tier1" in summary["trust_distribution"]
        assert "tier3" in summary["trust_distribution"]
    
    def test_audit_trail(self, provenance):
        """测试审计追踪"""
        provenance.record_source(
            entity_name="公司",
            attribute="营收",
            value="100亿",
            source_type="research",
            source_ref="test.md"
        )
        
        trail = provenance.get_audit_trail("公司")
        assert len(trail) == 1
        assert trail[0]["action"] == "create"
        assert trail[0]["entity_name"] == "公司"


class TestKnowledgeBankV2:
    """测试 KnowledgeBank v2.0 集成"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield d
    
    def test_store_temporal_fact(self, temp_dir):
        """测试存储时间事实"""
        from src.core.memory import UserKnowledgeBank
        
        db_path = os.path.join(temp_dir, "test_knowledge.db")
        kb = UserKnowledgeBank("test_user", db_path)
        
        try:
            result = kb.store_temporal_fact(
                entity_name="宁德时代",
                attribute="市场份额",
                value="37%",
                as_of="2024-Q3",
                source="2024Q3财报",
                source_type="financial_report"
            )
            
            assert "fact_id" in result
            assert "provenance_id" in result
        finally:
            kb.close()
    
    def test_get_temporal_value(self, temp_dir):
        """测试获取时间值"""
        from src.core.memory import UserKnowledgeBank
        
        db_path = os.path.join(temp_dir, "test_knowledge.db")
        kb = UserKnowledgeBank("test_user", db_path)
        
        try:
            kb.store_temporal_fact(
                entity_name="宁德时代",
                attribute="市场份额",
                value="37%",
                as_of="2024-Q3",
                source="2024Q3财报"
            )
            
            value = kb.get_temporal_value("宁德时代", "市场份额")
            assert value is not None
            assert value["value"] == "37%"
        finally:
            kb.close()
    
    def test_get_knowledge_stats(self, temp_dir):
        """测试获取知识统计"""
        from src.core.memory import UserKnowledgeBank
        
        db_path = os.path.join(temp_dir, "test_knowledge.db")
        kb = UserKnowledgeBank("test_user", db_path)
        
        try:
            kb.store_temporal_fact(
                entity_name="宁德时代",
                attribute="市场份额",
                value="37%",
                as_of="2024-Q3",
                source="2024Q3财报"
            )
            
            stats = kb.get_knowledge_stats()
            assert "base" in stats
            assert "temporal" in stats
            assert "provenance" in stats
            assert stats["temporal"]["total_facts"] == 1
        finally:
            kb.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])