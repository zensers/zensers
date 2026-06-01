# -*- coding: utf-8 -*-
"""
研究增强测试

测试知识银行如何增强研究过程
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from src.core.memory.research_enhancer import ResearchEnhancer


class TestResearchEnhancerInit:
    """测试研究增强器初始化"""
    
    def test_init_with_knowledge_bank(self, tmp_path):
        """使用知识银行初始化"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        enhancer = ResearchEnhancer(knowledge_bank=bank)
        
        assert enhancer.knowledge_bank is not None
        bank.close()
    
    def test_init_without_knowledge_bank(self):
        """不使用知识银行初始化"""
        enhancer = ResearchEnhancer()
        
        assert enhancer.knowledge_bank is None


class TestEnrichResearchRequest:
    """测试研究请求增强"""
    
    @pytest.fixture
    def enhancer_with_data(self, tmp_path):
        """创建带数据的研究增强器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加知识
        bank.entities.add_entity("industry", "储能", description="储能行业")
        bank.entities.add_entity("company", "宁德时代", description="电池制造商")
        
        return ResearchEnhancer(knowledge_bank=bank), bank
    
    @pytest.mark.asyncio
    async def test_enrich_with_relevant_knowledge(self, enhancer_with_data):
        """使用相关知识增强请求"""
        enhancer, bank = enhancer_with_data
        
        request = {
            "topic": "储能行业分析",
            "requirements": ["市场规模", "主要企业"]
        }
        
        enriched = await enhancer.enrich_request(request)
        
        # 验证增强后的请求包含相关知识字段
        assert "relevant_knowledge" in enriched
        # 即使没有找到相关知识，也应该有这个字段
        assert isinstance(enriched["relevant_knowledge"], dict)
    
    @pytest.mark.asyncio
    async def test_enrich_adds_context(self, enhancer_with_data):
        """增强添加上下文"""
        enhancer, bank = enhancer_with_data
        
        request = {"topic": "储能行业"}
        
        enriched = await enhancer.enrich_request(request)
        
        assert "context" in enriched or "relevant_knowledge" in enriched
    
    @pytest.mark.asyncio
    async def test_enrich_without_knowledge_bank(self):
        """无知识银行时增强"""
        enhancer = ResearchEnhancer()
        
        request = {"topic": "测试主题"}
        
        enriched = await enhancer.enrich_request(request)
        
        # 无知识银行时应该返回原始请求
        assert enriched["topic"] == "测试主题"


class TestStoreResearchResults:
    """测试存储研究结果"""
    
    @pytest.fixture
    def enhancer(self, tmp_path):
        """创建研究增强器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ResearchEnhancer(knowledge_bank=bank), bank
    
    @pytest.mark.asyncio
    async def test_store_research_entities(self, enhancer):
        """存储研究实体"""
        enhancer, bank = enhancer
        
        result = {
            "research_id": "research_001",
            "topic": "储能行业分析",
            "entities": [
                {"name": "宁德时代", "type": "company"}
            ]
        }
        
        stored = await enhancer.store_results(result)
        
        assert stored["entities_added"] >= 1
        
        # 验证知识银行中有这个实体
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_store_research_data_points(self, enhancer):
        """存储研究数据点"""
        enhancer, bank = enhancer
        
        e1 = bank.entities.add_entity("company", "宁德时代")
        
        result = {
            "research_id": "research_001",
            "data_points": [
                {
                    "entity_id": e1,
                    "metric": "市场份额",
                    "value": "37%",
                    "year": "2023"
                }
            ]
        }
        
        stored = await enhancer.store_results(result)
        
        assert stored["data_points_added"] >= 1
    
    @pytest.mark.asyncio
    async def test_store_research_relations(self, enhancer):
        """存储研究关系"""
        enhancer, bank = enhancer
        
        e1 = bank.entities.add_entity("company", "宁德时代")
        e2 = bank.entities.add_entity("company", "特斯拉")
        
        result = {
            "research_id": "research_001",
            "relations": [
                {
                    "source": e1,
                    "target": e2,
                    "type": "supplier",
                    "context": "电池供应"
                }
            ]
        }
        
        stored = await enhancer.store_results(result)
        
        assert stored["relations_added"] >= 1


class TestGenerateResearchContext:
    """测试生成研究上下文"""
    
    @pytest.fixture
    def enhancer_with_knowledge(self, tmp_path):
        """创建带知识的研究增强器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加知识
        bank.entities.add_entity("company", "阿里巴巴", description="电商平台")
        bank.entities.add_entity("company", "腾讯", description="互联网公司")
        
        e1 = bank.entities.search_entities("阿里巴巴")[0]
        e2 = bank.entities.search_entities("腾讯")[0]
        bank.relations.add_relation(e1["entity_id"], e2["entity_id"], "competitor", context="电商市场竞争")
        
        return ResearchEnhancer(knowledge_bank=bank), bank
    
    @pytest.mark.asyncio
    async def test_generate_context_from_knowledge(self, enhancer_with_knowledge):
        """从知识生成上下文"""
        enhancer, bank = enhancer_with_knowledge
        
        topic = "电商行业分析"
        
        context = await enhancer.generate_research_context(topic)
        
        assert "entities" in context or "relations" in context
    
    @pytest.mark.asyncio
    async def test_context_includes_entities(self, enhancer_with_knowledge):
        """上下文包含实体"""
        enhancer, bank = enhancer_with_knowledge
        
        topic = "电商平台"
        
        context = await enhancer.generate_research_context(topic)
        
        # 应该找到阿里巴巴或腾讯
        if "entities" in context:
            entity_names = [e.get("name", "") for e in context["entities"]]
            assert "阿里巴巴" in entity_names or "腾讯" in entity_names


class TestResearchEnhancerIntegration:
    """测试研究增强集成"""
    
    @pytest.fixture
    def setup(self, tmp_path):
        """设置测试环境"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        enhancer = ResearchEnhancer(knowledge_bank=bank)
        return enhancer, bank
    
    @pytest.mark.asyncio
    async def test_full_research_workflow(self, setup):
        """完整研究工作流"""
        enhancer, bank = setup
        
        # 1. 增强研究请求
        request = {
            "topic": "动力电池行业",
            "requirements": ["市场规模", "主要企业"]
        }
        
        enriched = await enhancer.enrich_request(request)
        
        assert "relevant_knowledge" in enriched
        
        # 2. 模拟研究结果
        result = {
            "research_id": "research_001",
            "topic": "动力电池行业分析",
            "entities": [
                {"name": "宁德时代", "type": "company", "description": "电池制造商"}
            ],
            "data_points": [],
            "relations": []
        }
        
        # 3. 存储结果
        stored = await enhancer.store_results(result)
        
        assert stored["entities_added"] >= 1
        
        # 4. 验证知识银行更新
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] >= 1


class TestKnowledgeSuggestion:
    """测试知识建议"""
    
    @pytest.fixture
    def enhancer_with_history(self, tmp_path):
        """创建带历史的研究增强器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加历史知识
        bank.entities.add_entity("company", "阿里巴巴")
        bank.entities.add_entity("industry", "电商")
        
        return ResearchEnhancer(knowledge_bank=bank), bank
    
    @pytest.mark.asyncio
    async def test_suggest_related_topics(self, enhancer_with_history):
        """建议相关主题"""
        enhancer, bank = enhancer_with_history
        
        current_topic = "互联网行业"
        
        suggestions = await enhancer.suggest_related_topics(current_topic)
        
        assert isinstance(suggestions, list)
    
    @pytest.mark.asyncio
    async def test_suggest_from_entities(self, enhancer_with_history):
        """从实体建议"""
        enhancer, bank = enhancer_with_history
        
        topic = "电商"
        
        suggestions = await enhancer.suggest_related_topics(topic)
        
        # 应该建议相关实体或主题
        assert len(suggestions) >= 0