# -*- coding: utf-8 -*-
"""
语义检索测试

测试 SemanticSearch 的核心功能：
- 语义搜索
- 关键词扩展
- 结果排序
"""

import pytest
from typing import List, Dict, Any
import tempfile
from pathlib import Path


class TestSemanticSearchInit:
    """测试 SemanticSearch 初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        search = SemanticSearch()
        
        assert search is not None
        
    def test_init_with_vector_store(self):
        """测试带向量存储初始化"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        search = SemanticSearch(vector_store=store)
        
        assert search.vector_store is not None
        
    def test_init_with_config(self):
        """测试带配置初始化"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        search = SemanticSearch(
            top_k=20,
            similarity_threshold=0.8
        )
        
        assert search.top_k == 20
        assert search.similarity_threshold == 0.8


class TestSemanticSearchBasic:
    """测试基本语义搜索"""
    
    def test_search_single_query(self):
        """测试单个查询"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加测试向量
        test_data = [
            ([0.1] * 128, {"name": "宁德时代", "type": "company"}),
            ([0.5] * 128, {"name": "比亚迪", "type": "company"}),
            ([0.9] * 128, {"name": "特斯拉", "type": "company"}),
        ]
        
        for vector, metadata in test_data:
            store.add(vector, metadata)
        
        search = SemanticSearch(vector_store=store)
        
        # 搜索
        query_vector = [0.5] * 128
        results = search.search(query_vector)
        
        assert len(results) > 0
        
    def test_search_with_text_query(self):
        """测试文本查询（需要嵌入）"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加测试数据
        for i in range(5):
            vector = [float(i) / 5.0] * 128
            store.add(vector, {"name": f"entity_{i}"})
        
        # 使用模拟嵌入器
        search = SemanticSearch(
            vector_store=store,
            embedder=MockEmbedder()
        )
        
        results = search.search_text("test query")
        
        assert len(results) > 0
        
    def test_search_with_filters(self):
        """测试带过滤器的搜索"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加不同类型的向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            entity_type = "company" if i < 5 else "person"
            store.add(vector, {"id": f"e_{i}", "type": entity_type})
        
        search = SemanticSearch(vector_store=store)
        
        query = [0.5] * 128
        results = search.search(query, filters={"type": "company"})
        
        # 应该只返回公司类型
        for result in results:
            assert result["metadata"]["type"] == "company"


class TestSemanticSearchRanking:
    """测试搜索结果排序"""
    
    def test_ranking_by_similarity(self):
        """测试按相似度排序"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            store.add(vector, {"id": f"e_{i}"})
        
        search = SemanticSearch(vector_store=store, top_k=5)
        
        query = [0.5] * 128
        results = search.search(query)
        
        # 结果应该按相似度降序排列
        for i in range(len(results) - 1):
            assert results[i]["similarity"] >= results[i + 1]["similarity"]
            
    def test_ranking_with_boost(self):
        """测试带加权的排序"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            store.add(vector, {
                "id": f"e_{i}",
                "importance": 10 - i  # 重要性递减
            })
        
        search = SemanticSearch(
            vector_store=store,
            boost_field="importance"
        )
        
        query = [0.5] * 128
        results = search.search(query)
        
        # 结果应该考虑重要性加权
        assert len(results) > 0


class TestSemanticSearchKeywordExpansion:
    """测试关键词扩展"""
    
    def test_keyword_expansion_simple(self):
        """测试简单关键词扩展"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        search = SemanticSearch()
        
        # 扩展关键词
        expanded = search.expand_keywords("新能源汽车")
        
        # 应该包含相关词
        assert len(expanded) >= 1
        assert "新能源汽车" in expanded
        
    def test_keyword_expansion_with_synonyms(self):
        """测试同义词扩展"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        search = SemanticSearch(enable_synonym_expansion=True)
        
        expanded = search.expand_keywords("电动汽车")
        
        # 应该包含同义词
        assert len(expanded) >= 1
        
    def test_keyword_expansion_with_abbreviations(self):
        """测试缩写扩展"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        search = SemanticSearch(enable_abbreviation_expansion=True)
        
        expanded = search.expand_keywords("CATL")
        
        # 应该展开缩写
        assert len(expanded) >= 1


class TestSemanticSearchConfig:
    """测试搜索配置"""
    
    def test_search_config_top_k(self):
        """测试 Top-K 配置"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(20):
            vector = [float(i) / 20.0] * 128
            store.add(vector, {"id": f"e_{i}"})
        
        search = SemanticSearch(vector_store=store, top_k=10)
        
        query = [0.5] * 128
        results = search.search(query)
        
        assert len(results) == 10
        
    def test_search_config_threshold(self):
        """测试相似度阈值配置"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            store.add(vector, {"id": f"e_{i}"})
        
        search = SemanticSearch(
            vector_store=store,
            similarity_threshold=0.99  # 高阈值
        )
        
        query = [0.5] * 128
        results = search.search(query)
        
        # 所有结果应该满足阈值
        for result in results:
            assert result["similarity"] >= 0.99


class TestSemanticSearchIntegration:
    """集成测试"""
    
    def test_full_search_cycle(self):
        """测试完整搜索周期"""
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 创建向量存储
            store = VectorStore(
                dimension=128,
                storage_path=tmp_dir
            )
            
            # 添加实体向量
            entities = [
                ([0.1] * 128, {"name": "宁德时代", "type": "company", "industry": "电池"}),
                ([0.2] * 128, {"name": "比亚迪", "type": "company", "industry": "汽车"}),
                ([0.3] * 128, {"name": "特斯拉", "type": "company", "industry": "汽车"}),
                ([0.4] * 128, {"name": "马斯克", "type": "person", "industry": "科技"}),
                ([0.5] * 128, {"name": "王传福", "type": "person", "industry": "汽车"}),
            ]
            
            for vector, metadata in entities:
                store.add(vector, metadata)
            
            # 创建搜索器
            search = SemanticSearch(
                vector_store=store,
                top_k=3
            )
            
            # 搜索公司
            query = [0.15] * 128  # 接近宁德时代
            results = search.search(
                query,
                filters={"type": "company"}
            )
            
            # 验证
            assert len(results) <= 3
            for result in results:
                assert result["metadata"]["type"] == "company"


# 辅助类

class MockEmbedder:
    """模拟嵌入器"""
    
    def embed(self, text: str) -> List[float]:
        """生成模拟嵌入向量"""
        # 简单的模拟：基于文本长度生成向量
        dimension = 128
        base = len(text) % 10 / 10.0
        return [base] * dimension
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量"""
        return [self.embed(text) for text in texts]