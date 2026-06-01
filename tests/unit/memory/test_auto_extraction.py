# -*- coding: utf-8 -*-
"""
自动知识提取测试

测试从研究过程中自动提取知识
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from src.core.memory.auto_extraction import KnowledgeExtractor


class TestKnowledgeExtractorInit:
    """测试知识提取器初始化"""
    
    def test_init_with_knowledge_bank(self, tmp_path):
        """使用知识银行初始化"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        extractor = KnowledgeExtractor(knowledge_bank=bank)
        
        assert extractor.knowledge_bank is not None
        bank.close()
    
    def test_init_without_knowledge_bank(self):
        """不使用知识银行初始化"""
        extractor = KnowledgeExtractor()
        
        assert extractor.knowledge_bank is None


class TestExtractEntities:
    """测试实体提取"""
    
    @pytest.fixture
    def extractor(self, tmp_path):
        """创建提取器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return KnowledgeExtractor(knowledge_bank=bank)
    
    def test_extract_company_entities(self, extractor):
        """提取公司实体"""
        text = "阿里巴巴和腾讯是中国最大的电商平台竞争者"
        
        entities = extractor.extract_entities(text)
        
        assert len(entities) >= 2
        entity_names = [e["name"] for e in entities]
        assert "阿里巴巴" in entity_names or "腾讯" in entity_names
    
    def test_extract_with_entity_types(self, extractor):
        """提取并分类实体"""
        text = "宁德时代为特斯拉供应电池"
        
        entities = extractor.extract_entities(text)
        
        # 应该识别出公司实体
        assert len(entities) >= 1
    
    def test_extract_empty_text(self, extractor):
        """提取空文本"""
        entities = extractor.extract_entities("")
        
        assert len(entities) == 0


class TestExtractRelations:
    """测试关系提取"""
    
    @pytest.fixture
    def extractor(self, tmp_path):
        """创建提取器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return KnowledgeExtractor(knowledge_bank=bank)
    
    def test_extract_competition_relation(self, extractor):
        """提取竞争关系"""
        text = "阿里巴巴和腾讯在电商市场竞争激烈"
        entities = [
            {"name": "阿里巴巴", "entity_type": "company"},
            {"name": "腾讯", "entity_type": "company"}
        ]
        
        relations = extractor.extract_relations(text, entities)
        
        assert len(relations) >= 1
        # 应该识别出竞争关系
        relation_types = [r["relation_type"] for r in relations]
        assert "competitor" in relation_types or "竞争" in str(relation_types)
    
    def test_extract_supply_relation(self, extractor):
        """提取供应关系"""
        text = "宁德时代为特斯拉供应动力电池"
        entities = [
            {"name": "宁德时代", "entity_type": "company"},
            {"name": "特斯拉", "entity_type": "company"}
        ]
        
        relations = extractor.extract_relations(text, entities)
        
        assert len(relations) >= 1


class TestExtractDataPoints:
    """测试数据点提取"""
    
    @pytest.fixture
    def extractor(self, tmp_path):
        """创建提取器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return KnowledgeExtractor(knowledge_bank=bank)
    
    def test_extract_revenue_data(self, extractor):
        """提取营收数据"""
        text = "阿里巴巴2023年营收达到5000亿元"
        
        data_points = extractor.extract_data_points(text)
        
        assert len(data_points) >= 1
        # 应该识别出营收数据
        metrics = [dp["metric_name"] for dp in data_points]
        assert "营收" in metrics or "revenue" in str(metrics).lower()
    
    def test_extract_market_share_data(self, extractor):
        """提取市场份额数据"""
        text = "宁德时代动力电池市场份额达到37%"
        
        data_points = extractor.extract_data_points(text)
        
        assert len(data_points) >= 1
    
    def test_extract_with_entity_context(self, extractor):
        """提取带实体上下文的数据"""
        text = "阿里巴巴2023年营收5000亿元，同比增长10%"
        entities = [{"name": "阿里巴巴", "entity_type": "company"}]
        
        data_points = extractor.extract_data_points(text, entities=entities)
        
        assert len(data_points) >= 1


class TestExtractFromResearchResult:
    """测试从研究结果提取"""
    
    @pytest.fixture
    def extractor(self, tmp_path):
        """创建提取器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return KnowledgeExtractor(knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_extract_from_simple_result(self, extractor):
        """从简单结果提取"""
        research_result = {
            "topic": "储能行业分析",
            "content": "宁德时代是全球最大的动力电池制造商，市场份额达37%。",
            "entities": ["宁德时代"],
            "data": {"市场份额": "37%"}
        }
        
        extracted = await extractor.extract_from_research(research_result)
        
        assert "entities" in extracted
        assert "data_points" in extracted
        assert len(extracted["entities"]) >= 1 or len(extracted["data_points"]) >= 1
    
    @pytest.mark.asyncio
    async def test_extract_from_structured_result(self, extractor):
        """从结构化结果提取"""
        research_result = {
            "topic": "电商竞争分析",
            "sections": [
                {
                    "title": "市场格局",
                    "content": "阿里巴巴和腾讯是中国电商市场的两大巨头，竞争激烈。阿里巴巴2023年营收5000亿元。"
                }
            ]
        }
        
        extracted = await extractor.extract_from_research(research_result)
        
        assert "entities" in extracted


class TestDepositToKnowledgeBank:
    """测试存入知识银行"""
    
    @pytest.fixture
    def extractor_with_bank(self, tmp_path):
        """创建带知识银行的提取器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return KnowledgeExtractor(knowledge_bank=bank), bank
    
    @pytest.mark.asyncio
    async def test_deposit_entities(self, extractor_with_bank):
        """存入实体"""
        extractor, bank = extractor_with_bank
        
        entities = [
            {"name": "阿里巴巴", "entity_type": "company", "description": "电商平台"}
        ]
        
        result = await extractor.deposit_entities(entities)
        
        assert result["added"] >= 1
        # 验证知识银行中有这个实体
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_deposit_relations(self, extractor_with_bank):
        """存入关系"""
        extractor, bank = extractor_with_bank
        
        # 先添加实体
        e1 = bank.entities.add_entity("company", "阿里巴巴")
        e2 = bank.entities.add_entity("company", "腾讯")
        
        relations = [
            {
                "source_entity": e1,
                "target_entity": e2,
                "relation_type": "competitor",
                "context": "电商市场竞争"
            }
        ]
        
        result = await extractor.deposit_relations(relations)
        
        assert result["added"] >= 1
    
    @pytest.mark.asyncio
    async def test_deposit_data_points(self, extractor_with_bank):
        """存入数据点"""
        extractor, bank = extractor_with_bank
        
        e1 = bank.entities.add_entity("company", "阿里巴巴")
        
        data_points = [
            {
                "entity_id": e1,
                "metric_name": "营收",
                "metric_value": "5000亿元",
                "time_period": "2023"
            }
        ]
        
        result = await extractor.deposit_data_points(data_points)
        
        assert result["added"] >= 1


class TestKnowledgeExtractionIntegration:
    """测试知识提取集成"""
    
    @pytest.fixture
    def setup(self, tmp_path):
        """设置测试环境"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        extractor = KnowledgeExtractor(knowledge_bank=bank)
        return extractor, bank
    
    @pytest.mark.asyncio
    async def test_full_extraction_workflow(self, setup):
        """完整提取工作流"""
        extractor, bank = setup
        
        # 模拟研究结果
        research_result = {
            "research_id": "research_001",
            "topic": "动力电池行业分析",
            "content": "宁德时代是全球最大的动力电池制造商，市场份额达37%，2023年营收超过4000亿元。主要客户包括特斯拉、宝马等车企。"
        }
        
        # 提取知识
        extracted = await extractor.extract_from_research(research_result)
        
        # 验证提取结果
        assert extracted is not None
        
        # 手动存入实体以验证工作流
        if extracted.get("entities"):
            result = await extractor.deposit_entities(extracted["entities"])
            assert result["added"] >= 1
            
            stats = bank.get_knowledge_stats()
            assert stats["entity_count"] >= 1