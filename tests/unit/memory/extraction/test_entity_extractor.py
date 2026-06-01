# -*- coding: utf-8 -*-
"""
实体提取器测试

测试 EntityExtractor 的核心功能：
- 实体类型识别（公司、人物、产品、指标、时间）
- 实体去重与合并
- 别名识别
- 提取配置
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
import re


class TestEntityExtractorInit:
    """测试 EntityExtractor 初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        assert extractor is not None
        
    def test_init_with_config(self):
        """测试带配置初始化"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        config = {
            "company_patterns": ["公司", "集团", "企业"],
            "person_patterns": ["先生", "女士", "CEO"],
            "confidence_threshold": 0.8
        }
        
        extractor = EntityExtractor(config=config)
        
        assert extractor.config is not None


class TestEntityExtraction:
    """测试实体提取"""
    
    def test_extract_company(self):
        """测试公司实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代是全球领先的电池制造商，比亚迪也是重要参与者。"
        
        entities = extractor.extract(text)
        
        # 应该提取出公司实体
        companies = [e for e in entities if e["entity_type"] == "company"]
        assert len(companies) >= 2
        assert any("宁德时代" in e["name"] for e in companies)
        assert any("比亚迪" in e["name"] for e in companies)
        
    def test_extract_person(self):
        """测试人物实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "马斯克是特斯拉的CEO，王传福领导比亚迪。"
        
        entities = extractor.extract(text)
        
        # 应该提取出人物实体
        persons = [e for e in entities if e["entity_type"] == "person"]
        assert len(persons) >= 2
        
    def test_extract_product(self):
        """测试产品实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "Model 3是特斯拉的主力车型，刀片电池是比亚迪的核心技术。"
        
        entities = extractor.extract(text)
        
        # 应该提取出产品实体
        products = [e for e in entities if e["entity_type"] == "product"]
        assert len(products) >= 2
        
    def test_extract_metric(self):
        """测试指标实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "市场份额达到35%，营收增长25%，市值超过1.2万亿。"
        
        entities = extractor.extract(text)
        
        # 应该提取出指标实体
        metrics = [e for e in entities if e["entity_type"] == "metric"]
        assert len(metrics) >= 1
        
    def test_extract_time(self):
        """测试时间实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "2024年第一季度，去年上半年，今年Q3业绩优秀。"
        
        entities = extractor.extract(text)
        
        # 应该提取出时间实体
        times = [e for e in entities if e["entity_type"] == "time"]
        assert len(times) >= 1
        
    def test_extract_multiple_types(self):
        """测试多类型实体提取"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = """
        2024年，宁德时代的市场份额达到35%。
        公司CEO曾毓群表示，将继续扩大产能。
        主要竞争对手比亚迪的刀片电池技术领先。
        """
        
        entities = extractor.extract(text)
        
        # 应该提取出多种类型
        types = set(e["entity_type"] for e in entities)
        assert len(types) >= 2


class TestEntityDeduplication:
    """测试实体去重"""
    
    def test_deduplicate_same_name(self):
        """测试同名实体去重"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代是电池龙头。宁德时代的市场份额很高。"
        
        entities = extractor.extract(text)
        
        # 同名实体应该合并
        catl_entities = [e for e in entities if "宁德时代" in e["name"]]
        assert len(catl_entities) == 1
        
    def test_deduplicate_aliases(self):
        """测试别名实体合并"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "CATL是电池龙头，宁德时代在福建。"
        
        entities = extractor.extract(text)
        
        # CATL和宁德时代应该合并
        catl_entities = [e for e in entities if "宁德" in e["name"] or "CATL" in e["name"]]
        # 合并后应该只有一个或带有别名
        assert len(catl_entities) <= 2
        
    def test_merge_entity_mentions(self):
        """测试实体提及合并"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "比亚迪。比亚迪。比亚迪。"  # 提及3次
        
        entities = extractor.extract(text)
        
        # 应该合并并记录提及次数
        byd_entities = [e for e in entities if "比亚迪" in e["name"]]
        assert len(byd_entities) == 1
        assert byd_entities[0].get("mention_count", 1) >= 1


class TestEntityConfidence:
    """测试实体置信度"""
    
    def test_high_confidence_entity(self):
        """测试高置信度实体"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        # 明确的公司名称
        text = "宁德时代股份有限公司"
        
        entities = extractor.extract(text)
        
        assert len(entities) >= 1
        assert entities[0]["confidence"] >= 0.8
        
    def test_low_confidence_entity(self):
        """测试低置信度实体"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        # 模糊的名称
        text = "某公司表示..."
        
        entities = extractor.extract(text)
        
        # 如果提取到，置信度应该较低
        if entities:
            assert entities[0]["confidence"] < 0.8


class TestEntityMetadata:
    """测试实体元数据"""
    
    def test_entity_has_position(self):
        """测试实体位置信息"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代是全球领先的电池制造商"
        
        entities = extractor.extract(text)
        
        assert len(entities) >= 1
        # 应该有位置信息
        assert "start" in entities[0] or "position" in entities[0]
        
    def test_entity_has_context(self):
        """测试实体上下文"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代是全球领先的电池制造商"
        
        entities = extractor.extract(text)
        
        assert len(entities) >= 1
        # 应该有上下文信息
        assert "context" in entities[0] or entities[0].get("properties") is not None
        
    def test_entity_has_source_info(self):
        """测试实体来源信息"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代是全球领先的电池制造商"
        source = {"url": "https://example.com/news", "tier": "tier1"}
        
        entities = extractor.extract(text, source=source)
        
        assert len(entities) >= 1
        # 应该有来源信息
        assert "source" in entities[0] or "provenance" in entities[0]


class TestEntityPatterns:
    """测试实体识别模式"""
    
    def test_custom_patterns(self):
        """测试自定义模式"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        config = {
            "company_patterns": ["公司", "集团", "企业", "科技"],
            "company_suffixes": ["Inc", "Corp", "Ltd"]
        }
        
        extractor = EntityExtractor(config=config)
        
        text = "某某科技是家创新企业"
        
        entities = extractor.extract(text)
        
        # 应该使用自定义模式
        assert len(entities) >= 1
        
    def test_chinese_company_patterns(self):
        """测试中文公司模式"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代新能源科技股份有限公司，比亚迪股份有限公司"
        
        entities = extractor.extract(text)
        
        companies = [e for e in entities if e["entity_type"] == "company"]
        assert len(companies) >= 2
        
    def test_english_company_patterns(self):
        """测试英文公司模式"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "Tesla Inc. and Apple Corp. are competitors."
        
        entities = extractor.extract(text)
        
        companies = [e for e in entities if e["entity_type"] == "company"]
        assert len(companies) >= 2


class TestEntityExtractionEdgeCases:
    """测试边缘情况"""
    
    def test_empty_text(self):
        """测试空文本"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        entities = extractor.extract("")
        
        assert entities == []
        
    def test_no_entities(self):
        """测试无实体文本"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "今天是晴天，天气很好。"
        
        entities = extractor.extract(text)
        
        # 不应该提取出实体
        assert len(entities) == 0 or all(e["confidence"] < 0.5 for e in entities)
        
    def test_special_characters(self):
        """测试特殊字符处理"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        text = "宁德时代（CATL）是电池龙头【官方】"
        
        entities = extractor.extract(text)
        
        # 应该正确处理特殊字符
        assert len(entities) >= 1
        
    def test_long_text(self):
        """测试长文本"""
        from src.core.memory.extraction.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        
        # 生成重复的长文本
        text = "宁德时代。比亚迪。特斯拉。" * 100
        
        entities = extractor.extract(text)
        
        # 应该正确处理并去重
        assert len(entities) <= 10  # 去重后不应该太多