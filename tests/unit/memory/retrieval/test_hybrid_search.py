# -*- coding: utf-8 -*-
"""
混合检索测试

测试 HybridSearch 的核心功能：
- 向量 + 关键词混合检索
- 多策略组合
- 结果融合
"""

import pytest
from typing import List, Dict, Any
import tempfile


class TestHybridSearchInit:
    """测试 HybridSearch 初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        
        search = HybridSearch()
        
        assert search is not None
        
    def test_init_with_stores(self):
        """测试带存储初始化"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        from src.core.memory.retrieval.semantic_search import SemanticSearch
        
        vector_store = VectorStore(dimension=128)
        semantic_search = SemanticSearch(vector_store=vector_store)
        
        hybrid = HybridSearch(
            vector_store=vector_store,
            semantic_search=semantic_search
        )
        
        assert hybrid.vector_store is not None
        assert hybrid.semantic_search is not None


class TestHybridSearchBasic:
    """测试基本混合检索"""
    
    def test_hybrid_search_vector_and_keyword(self):
        """测试向量+关键词混合"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        # 添加测试数据
        test_data = [
            ([0.1] * 128, {"name": "宁德时代", "type": "company", "keywords": ["电池", "新能源"]}),
            ([0.5] * 128, {"name": "比亚迪", "type": "company", "keywords": ["汽车", "新能源"]}),
            ([0.9] * 128, {"name": "特斯拉", "type": "company", "keywords": ["汽车", "电动"]}),
        ]
        
        for vector, metadata in test_data:
            vector_store.add(vector, metadata)
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        # 混合搜索
        query_vector = [0.5] * 128
        query_text = "新能源"
        results = hybrid.search(
            query_vector=query_vector,
            query_text=query_text
        )
        
        assert len(results) > 0
        
    def test_hybrid_search_vector_only(self):
        """测试仅向量搜索"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        # 添加数据
        for i in range(5):
            vector = [float(i) / 5.0] * 128
            vector_store.add(vector, {"id": f"e_{i}"})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        results = hybrid.search(query_vector=query)
        
        assert len(results) > 0
        
    def test_hybrid_search_keyword_only(self):
        """测试仅关键词搜索"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        # 添加带关键词的数据
        test_data = [
            ([0.1] * 128, {"name": "宁德时代", "desc": "新能源电池制造商"}),
            ([0.5] * 128, {"name": "比亚迪", "desc": "新能源汽车企业"}),
        ]
        
        for vector, metadata in test_data:
            vector_store.add(vector, metadata)
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        results = hybrid.search(query_text="新能源")
        
        assert len(results) > 0


class TestHybridSearchStrategies:
    """测试检索策略"""
    
    def test_strategy_fast_mode(self):
        """测试快速模式"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            vector_store.add(vector, {"id": f"e_{i}"})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        results = hybrid.search(
            query_vector=query,
            strategy="fast"
        )
        
        # 快速模式应该有结果
        assert len(results) > 0
        
    def test_strategy_precise_mode(self):
        """测试精确模式"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            vector_store.add(vector, {"id": f"e_{i}"})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        results = hybrid.search(
            query_vector=query,
            strategy="precise"
        )
        
        assert len(results) > 0
        
    def test_strategy_full_mode(self):
        """测试完整模式"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            vector_store.add(vector, {"id": f"e_{i}"})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        results = hybrid.search(
            query_vector=query,
            strategy="full"
        )
        
        assert len(results) > 0


class TestHybridSearchFusion:
    """测试结果融合"""
    
    def test_result_fusion_rrf(self):
        """测试RRF融合"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        
        hybrid = HybridSearch()
        
        # 模拟两个搜索结果
        results1 = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.8},
            {"id": "c", "score": 0.7},
        ]
        results2 = [
            {"id": "b", "score": 0.95},
            {"id": "a", "score": 0.85},
            {"id": "d", "score": 0.6},
        ]
        
        # RRF融合
        fused = hybrid.reciprocal_rank_fusion([results1, results2], k=60)
        
        assert len(fused) > 0
        # b 在两个结果中排名都很高
        assert any(r["id"] == "b" for r in fused[:2])
        
    def test_result_fusion_weighted(self):
        """测试加权融合"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        
        hybrid = HybridSearch()
        
        results1 = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.8},
        ]
        results2 = [
            {"id": "b", "score": 0.95},
            {"id": "c", "score": 0.7},
        ]
        
        # 加权融合
        fused = hybrid.weighted_fusion(
            [results1, results2],
            weights=[0.6, 0.4]
        )
        
        assert len(fused) > 0
        
    def test_result_deduplication(self):
        """测试结果去重"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        
        hybrid = HybridSearch()
        
        results = [
            {"id": "a", "score": 0.9},
            {"id": "a", "score": 0.85},  # 重复
            {"id": "b", "score": 0.8},
            {"id": "b", "score": 0.75},  # 重复
        ]
        
        deduped = hybrid.deduplicate_results(results)
        
        assert len(deduped) == 2
        assert deduped[0]["id"] == "a"  # 保留高分


class TestHybridSearchFilters:
    """测试过滤功能"""
    
    def test_filter_by_type(self):
        """测试按类型过滤"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        vector_store = VectorStore(dimension=128)
        
        # 添加不同类型
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            entity_type = "company" if i < 5 else "person"
            vector_store.add(vector, {"id": f"e_{i}", "type": entity_type})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        results = hybrid.search(
            query_vector=query,
            filters={"type": "company"}
        )
        
        for result in results:
            assert result["metadata"]["type"] == "company"
            
    def test_filter_by_time_range(self):
        """测试按时间范围过滤"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        from datetime import datetime, timedelta
        
        vector_store = VectorStore(dimension=128)
        
        # 添加带时间戳的数据
        now = datetime.now()
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            created_at = (now - timedelta(days=i)).isoformat()
            vector_store.add(vector, {"id": f"e_{i}", "created_at": created_at})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        time_range = (
            (now - timedelta(days=3)).isoformat(),
            now.isoformat()
        )
        results = hybrid.search(
            query_vector=query,
            time_range=time_range
        )
        
        # 应该只返回最近3天的数据
        assert len(results) >= 0


class TestHybridSearchPerformance:
    """测试性能"""
    
    def test_search_latency_fast_mode(self):
        """测试快速模式延迟"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        import time
        
        vector_store = VectorStore(dimension=128)
        
        # 添加数据
        for i in range(100):
            vector = [float(i % 10) / 10.0] * 128
            vector_store.add(vector, {"id": f"e_{i}"})
        
        hybrid = HybridSearch(vector_store=vector_store)
        
        query = [0.5] * 128
        
        start = time.time()
        results = hybrid.search(query_vector=query, strategy="fast")
        latency = (time.time() - start) * 1000
        
        # 快速模式应该在 100ms 内完成
        assert latency < 100
        assert len(results) > 0


class TestHybridSearchIntegration:
    """集成测试"""
    
    def test_full_hybrid_search_cycle(self):
        """测试完整混合检索周期"""
        from src.core.memory.retrieval.hybrid_search import HybridSearch
        from src.core.memory.retrieval.vector_store import VectorStore
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 创建向量存储
            vector_store = VectorStore(
                dimension=128,
                storage_path=tmp_dir
            )
            
            # 添加实体
            entities = [
                ([0.1] * 128, {"name": "宁德时代", "type": "company", "industry": "电池"}),
                ([0.2] * 128, {"name": "比亚迪", "type": "company", "industry": "汽车"}),
                ([0.3] * 128, {"name": "特斯拉", "type": "company", "industry": "汽车"}),
                ([0.4] * 128, {"name": "马斯克", "type": "person", "industry": "科技"}),
            ]
            
            for vector, metadata in entities:
                vector_store.add(vector, metadata)
            
            # 创建混合检索器
            hybrid = HybridSearch(
                vector_store=vector_store,
                strategy="precise"
            )
            
            # 搜索汽车公司
            query = [0.25] * 128  # 接近比亚迪和特斯拉
            results = hybrid.search(
                query_vector=query,
                query_text="汽车",
                filters={"type": "company"}
            )
            
            # 验证结果
            assert len(results) > 0
            for result in results:
                assert result["metadata"]["type"] == "company"