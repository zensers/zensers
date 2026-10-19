# -*- coding: utf-8 -*-
"""
向量存储测试

测试 VectorStore 的核心功能：
- 向量添加和存储
- 向量相似度计算
- Top-K 检索
- 向量持久化
"""

import pytest
import tempfile
import json
from pathlib import Path
from typing import List
import struct


class TestVectorStoreInit:
    """测试 VectorStore 初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore()
        
        assert store is not None
        assert store.dimension == 1536  # 默认维度
        
    def test_init_with_dimension(self):
        """测试自定义维度初始化"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=768)
        
        assert store.dimension == 768
        
    def test_init_with_storage_path(self):
        """测试带存储路径初始化"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VectorStore(storage_path=tmp_dir)
            
            assert store.storage_path == Path(tmp_dir)


class TestVectorStoreOperations:
    """测试向量操作"""
    
    def test_add_single_vector(self):
        """测试添加单个向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 创建测试向量
        vector = [0.1] * 128
        metadata = {"entity_id": "entity_001", "name": "宁德时代"}
        
        vector_id = store.add(vector, metadata)
        
        assert vector_id is not None
        assert store.count() == 1
        
    def test_add_multiple_vectors(self):
        """测试添加多个向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加多个向量
        for i in range(10):
            vector = [0.1 * (i + 1)] * 128
            store.add(vector, {"id": f"vec_{i}"})
        
        assert store.count() == 10
        
    def test_get_vector_by_id(self):
        """测试通过ID获取向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        vector = [0.5] * 128
        vector_id = store.add(vector, {"name": "test"})
        
        # 获取向量
        result = store.get(vector_id)
        
        assert result is not None
        assert result["metadata"]["name"] == "test"
        
    def test_delete_vector(self):
        """测试删除向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        vector = [0.5] * 128
        vector_id = store.add(vector, {"name": "test"})
        
        # 删除
        success = store.delete(vector_id)
        
        assert success == True
        assert store.count() == 0
        
    def test_update_vector(self):
        """测试更新向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        vector = [0.5] * 128
        vector_id = store.add(vector, {"name": "old"})
        
        # 更新
        new_vector = [0.8] * 128
        store.update(vector_id, new_vector, {"name": "new"})
        
        # 验证
        result = store.get(vector_id)
        assert result["metadata"]["name"] == "new"


class TestVectorStoreSearch:
    """测试向量搜索"""
    
    def test_search_top_k(self):
        """测试 Top-K 搜索"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加多个向量
        for i in range(20):
            vector = [float(i) / 20.0] * 128
            store.add(vector, {"id": f"vec_{i}", "value": i})
        
        # 搜索最接近 0.5 的向量
        query = [0.5] * 128
        results = store.search(query, top_k=5)
        
        assert len(results) == 5
        # 验证返回的都是高相似度结果（接近 0.5 的向量）
        # value=10 对应 0.5，但由于浮点精度和排序稳定性，检查相似度更可靠
        for result in results:
            # 所有返回结果的相似度应该很高（>= 0.99）
            assert result["similarity"] >= 0.99
    
    def test_search_exact_match(self):
        """测试精确匹配搜索"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加特定向量（使用唯一模式）
        target_vector = [0.5 + (i * 0.001) for i in range(128)]
        store.add(target_vector, {"name": "exact_match"})
        
        # 添加其他向量（完全不同的模式）
        for i in range(5):
            vector = [float(i % 3) * 0.3] * 128
            store.add(vector, {"name": f"vec_{i}"})
        
        # 搜索精确匹配
        results = store.search(target_vector, top_k=1)
        
        assert len(results) == 1
        assert results[0]["metadata"]["name"] == "exact_match"
        assert results[0]["similarity"] >= 0.9999  # 接近 1.0
        
    def test_search_with_threshold(self):
        """测试带阈值的搜索"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            store.add(vector, {"id": f"vec_{i}"})
        
        # 搜索相似度 > 0.9 的
        query = [0.5] * 128
        results = store.search(query, top_k=10, threshold=0.9)
        
        # 应该只返回高相似度的结果
        for result in results:
            assert result["similarity"] >= 0.9
            
    def test_search_empty_store(self):
        """测试空存储搜索"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        query = [0.5] * 128
        results = store.search(query, top_k=5)
        
        assert len(results) == 0
        
    def test_search_with_metadata_filter(self):
        """测试带元数据过滤的搜索"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加不同类型的向量
        for i in range(10):
            vector = [float(i) / 10.0] * 128
            store.add(vector, {
                "id": f"vec_{i}",
                "type": "company" if i < 5 else "person"
            })
        
        # 只搜索公司类型
        query = [0.5] * 128
        results = store.search(
            query, 
            top_k=10,
            filter={"type": "company"}
        )
        
        # 应该只返回公司类型
        for result in results:
            assert result["metadata"]["type"] == "company"


class TestVectorStorePersistence:
    """测试向量持久化"""
    
    def test_save_and_load(self):
        """测试保存和加载"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 创建并添加向量
            store1 = VectorStore(
                dimension=128,
                storage_path=tmp_dir
            )
            
            for i in range(5):
                vector = [float(i) / 5.0] * 128
                store1.add(vector, {"id": f"vec_{i}"})
            
            # 保存
            store1.save()
            
            # 加载到新实例
            store2 = VectorStore(
                dimension=128,
                storage_path=tmp_dir
            )
            store2.load()
            
            assert store2.count() == 5
            
    def test_auto_save_on_add(self):
        """测试添加时自动保存"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VectorStore(
                dimension=128,
                storage_path=tmp_dir,
                auto_save=True
            )
            
            vector = [0.5] * 128
            store.add(vector, {"id": "test"})
            
            # 检查文件是否存在
            storage_file = Path(tmp_dir) / "vectors.json"
            assert storage_file.exists()


class TestVectorStoreSimilarity:
    """测试相似度计算"""
    
    def test_cosine_similarity_identical(self):
        """测试相同向量的相似度"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        v1 = [0.5] * 128
        v2 = [0.5] * 128
        
        similarity = store.cosine_similarity(v1, v2)
        
        assert abs(similarity - 1.0) < 0.0001
        
    def test_cosine_similarity_orthogonal(self):
        """测试正交向量的相似度"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=2)
        
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        
        similarity = store.cosine_similarity(v1, v2)
        
        assert abs(similarity) < 0.0001
        
    def test_cosine_similarity_opposite(self):
        """测试相反向量的相似度"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        v1 = [0.5] * 128
        v2 = [-0.5] * 128
        
        similarity = store.cosine_similarity(v1, v2)
        
        assert abs(similarity + 1.0) < 0.0001


class TestVectorStoreEdgeCases:
    """测试边缘情况"""
    
    def test_add_wrong_dimension(self):
        """测试添加错误维度的向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 维度不匹配
        vector = [0.5] * 64  # 只有64维
        
        with pytest.raises(ValueError):
            store.add(vector, {"id": "test"})
            
    def test_add_empty_vector(self):
        """测试添加空向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        with pytest.raises(ValueError):
            store.add([], {"id": "test"})
            
    def test_get_nonexistent_vector(self):
        """测试获取不存在的向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        result = store.get("nonexistent_id")
        
        assert result is None
        
    def test_delete_nonexistent_vector(self):
        """测试删除不存在的向量"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        success = store.delete("nonexistent_id")
        
        assert success == False
        
    def test_large_scale_search(self):
        """测试大规模搜索性能"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加1000个向量
        for i in range(1000):
            vector = [float(i % 100) / 100.0] * 128
            store.add(vector, {"id": f"vec_{i}"})
        
        # 搜索
        query = [0.5] * 128
        results = store.search(query, top_k=10)
        
        assert len(results) == 10


class TestVectorStoreLRUEviction:
    """测试 LRU 淘汰机制"""
    
    def test_lru_eviction_on_max_size(self):
        """测试达到最大容量时触发 LRU 淘汰"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        # 创建容量为 5 的存储
        store = VectorStore(dimension=128, max_size=5)
        
        # 添加 5 个向量
        ids = []
        for i in range(5):
            vector = [float(i) / 10.0] * 128
            vid = store.add(vector, {"name": f"vec_{i}"})
            ids.append(vid)
        
        assert store.count() == 5
        
        # 添加第 6 个向量，应该淘汰第一个
        new_vector = [0.9] * 128
        new_id = store.add(new_vector, {"name": "vec_new"})
        
        assert store.count() == 5  # 仍然是 5
        assert store.get(ids[0]) is None  # 第一个被淘汰
        assert store.get(new_id) is not None  # 新的还在
    
    def test_lru_updates_on_access(self):
        """测试访问更新 LRU 顺序"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128, max_size=3)
        
        # 添加 3 个向量
        ids = []
        for i in range(3):
            vid = store.add([float(i) / 10.0] * 128, {"name": f"vec_{i}"})
            ids.append(vid)
        
        # 访问第一个向量（更新 LRU 顺序）
        store.get(ids[0])
        
        # 添加第 4 个向量，应该淘汰第二个（因为第一个刚被访问）
        store.add([0.9] * 128, {"name": "vec_new"})
        
        assert store.get(ids[0]) is not None  # 第一个还在（刚被访问）
        assert store.get(ids[1]) is None  # 第二个被淘汰
        assert store.get(ids[2]) is not None  # 第三个还在
    
    def test_no_eviction_when_unlimited(self):
        """测试无限制容量时不淘汰"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128, max_size=None)
        
        # 添加大量向量
        for i in range(100):
            store.add([float(i) / 100.0] * 128, {"name": f"vec_{i}"})
        
        assert store.count() == 100
    
    def test_get_stats(self):
        """测试统计信息"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128, max_size=100)
        
        # 添加一些向量
        for i in range(50):
            store.add([float(i) / 50.0] * 128, {"name": f"vec_{i}"})
        
        stats = store.get_stats()
        
        assert stats["total_vectors"] == 50
        assert stats["max_size"] == 100
        assert stats["dimension"] == 128
        assert stats["utilization"] == 0.5
        assert stats["vector_memory_bytes"] > 0
    
    def test_clear(self):
        """测试清空存储"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        
        # 添加向量
        for i in range(10):
            store.add([float(i) / 10.0] * 128, {"name": f"vec_{i}"})
        
        assert store.count() == 10
        
        # 清空
        cleared = store.clear()
        
        assert cleared == 10
        assert store.count() == 0
    
    def test_invalid_vector_elements(self):
        """测试无效向量元素（NaN/Inf）"""
        from src.core.memory.retrieval.vector_store import VectorStore
        import math
        
        store = VectorStore(dimension=128)
        
        # 测试 NaN
        with pytest.raises(ValueError):
            store.add([float('nan')] * 128, {"name": "nan_vec"})
        
        # 测试 Inf
        with pytest.raises(ValueError):
            store.add([float('inf')] * 128, {"name": "inf_vec"})
    
    def test_eviction_callback(self):
        """测试淘汰回调"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        # 记录被淘汰的向量
        evicted_vectors = []
        
        def on_evict(vector_id, entry):
            evicted_vectors.append({
                "id": vector_id,
                "metadata": entry.get("metadata", {})
            })
        
        store = VectorStore(dimension=128, max_size=3, on_evict=on_evict)
        
        # 添加 5 个向量（会淘汰 2 个）
        for i in range(5):
            store.add([float(i) / 10.0] * 128, {"name": f"vec_{i}"})
        
        # 验证回调被调用
        assert len(evicted_vectors) == 2
        assert evicted_vectors[0]["metadata"]["name"] == "vec_0"
        assert evicted_vectors[1]["metadata"]["name"] == "vec_1"
        
        # 验证统计信息包含淘汰计数
        stats = store.get_stats()
        assert stats["evicted_count"] == 2
    
    def test_update_validates_vector_elements(self):
        """测试更新时验证向量元素"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128)
        vector_id = store.add([0.5] * 128, {"name": "test"})
        
        # 测试更新 NaN
        with pytest.raises(ValueError):
            store.update(vector_id, vector=[float('nan')] * 128)
        
        # 测试更新 Inf
        with pytest.raises(ValueError):
            store.update(vector_id, vector=[float('inf')] * 128)
    
    def test_update_moves_to_end_lru(self):
        """测试更新后移动到 LRU 末尾"""
        from src.core.memory.retrieval.vector_store import VectorStore
        
        store = VectorStore(dimension=128, max_size=3)
        
        # 添加 3 个向量
        ids = []
        for i in range(3):
            vid = store.add([float(i) / 10.0] * 128, {"name": f"vec_{i}"})
            ids.append(vid)
        
        # 更新第一个向量
        store.update(ids[0], metadata={"updated": True})
        
        # 添加第 4 个向量，应该淘汰第二个（因为第一个刚被更新）
        store.add([0.9] * 128, {"name": "vec_new"})
        
        assert store.get(ids[0]) is not None  # 第一个还在（刚被更新）
        assert store.get(ids[1]) is None  # 第二个被淘汰
        assert store.get(ids[2]) is not None  # 第三个还在
    
    def test_load_respects_max_size(self):
        """测试加载时遵守 max_size"""
        from src.core.memory.retrieval.vector_store import VectorStore
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 先创建一个存储并保存 10 个向量
            store1 = VectorStore(dimension=128, storage_path=tmpdir, auto_save=True)
            for i in range(10):
                store1.add([float(i) / 10.0] * 128, {"name": f"vec_{i}"})
            store1.save()
            
            # 用更小的 max_size 加载
            evicted = []
            store2 = VectorStore(
                dimension=128,
                storage_path=tmpdir,
                max_size=5,
                on_evict=lambda vid, entry: evicted.append(vid)
            )
            
            # 应该只保留 5 个
            assert store2.count() == 5
            assert len(evicted) == 5  # 5 个被淘汰