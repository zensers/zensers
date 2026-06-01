# -*- coding: utf-8 -*-
"""
向量存储

实现向量嵌入的存储、检索和管理功能：
- 向量添加、更新、删除
- 余弦相似度计算
- Top-K 检索
- 持久化存储

设计目标：
- 无外部依赖（纯 Python 实现）
- 支持 SQLite 存储
- 支持大规模向量检索
"""

__all__ = ["VectorStore"]

from collections import OrderedDict
import json
import logging
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)


class VectorStore:
    """
    向量存储
    
    核心功能：
    - 向量的增删改查
    - 余弦相似度计算
    - Top-K 检索
    - 持久化存储
    - LRU 内存淘汰
    
    设计特点：
    - 纯 Python 实现，无外部依赖
    - 使用 OrderedDict 实现 LRU 淘汰
    - 支持元数据过滤
    - 支持淘汰回调通知
    
    线程安全：
    - 本类非线程安全，多线程环境需外部加锁
    - 建议使用 threading.Lock 保护并发访问
    
    参考：CONTEXT_COMPRESSION.md 第 2.2 节 Layer 3 知识库设计
    """
    
    # 默认配置
    DEFAULT_DIMENSION = 1536  # OpenAI embedding 维度
    DEFAULT_MAX_SIZE = 10000  # 默认最大向量数
    
    def __init__(
        self,
        dimension: int = DEFAULT_DIMENSION,
        storage_path: Optional[str] = None,
        auto_save: bool = False,
        max_size: Optional[int] = DEFAULT_MAX_SIZE,
        on_evict: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        """
        初始化向量存储
        
        Args:
            dimension: 向量维度
            storage_path: 存储路径，默认不持久化
            auto_save: 是否自动保存
            max_size: 最大向量数量（LRU 淘汰），None 表示无限制
            on_evict: 淘汰回调函数，签名 (vector_id, entry) -> None
                      用于在向量被淘汰前保存到持久化存储或通知调用者
        """
        self.dimension = dimension
        self.storage_path = Path(storage_path) if storage_path else None
        self.auto_save = auto_save
        self.max_size = max_size
        self.on_evict = on_evict
        
        # 使用 OrderedDict 实现 LRU 淘汰
        self._vectors: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._id_counter = 0
        self._evicted_count = 0  # 淘汰计数器
        
        # 如果有存储路径，尝试加载
        if self.storage_path:
            self._storage_file = self.storage_path / "vectors.json"
            if self._storage_file.exists():
                self.load()
        else:
            self._storage_file = None
        
        logger.info(
            f"VectorStore initialized: dimension={dimension}, "
            f"storage_path={storage_path}, auto_save={auto_save}, max_size={max_size}"
        )
    
    # ========== 向量操作 ==========
    
    def add(
        self,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        添加向量
        
        Args:
            vector: 向量数据
            metadata: 元数据
            
        Returns:
            向量ID
            
        Raises:
            ValueError: 向量维度不匹配或为空
        """
        # 验证向量
        if not vector:
            raise ValueError("Vector cannot be empty")
        
        if len(vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, "
                f"got {len(vector)}"
            )
        
        # 验证向量元素（防止 NaN/Inf）
        for i, v in enumerate(vector):
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(
                    f"Invalid vector element at index {i}: {v}. "
                    "All elements must be finite numbers."
                )
        
        # LRU 淘汰：如果达到最大容量，移除最久未使用的向量
        if self.max_size and len(self._vectors) >= self.max_size:
            # popitem(last=False) 移除最旧的项（FIFO 策略）
            evicted_id, evicted_entry = self._vectors.popitem(last=False)
            self._evicted_count += 1
            
            # 调用淘汰回调（可用于保存到持久化存储）
            if self.on_evict:
                try:
                    self.on_evict(evicted_id, evicted_entry)
                except Exception as e:
                    logger.error(f"Eviction callback failed for {evicted_id}: {e}")
            
            logger.info(
                f"LRU eviction: removed vector {evicted_id}, "
                f"metadata={evicted_entry.get('metadata', {})}, "
                f"total_evicted={self._evicted_count}"
            )
        
        # 生成ID
        vector_id = str(uuid.uuid4())
        
        # 存储向量（添加到末尾，表示最近使用）
        self._vectors[vector_id] = {
            "id": vector_id,
            "vector": vector,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat()
        }
        
        self._id_counter += 1
        
        # 自动保存
        if self.auto_save and self.storage_path:
            self.save()
        
        logger.debug(f"Added vector: id={vector_id}, total={len(self._vectors)}")
        return vector_id
    
    def get(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """
        获取向量
        
        Args:
            vector_id: 向量ID
            
        Returns:
            向量数据，包含 vector, metadata, created_at
        """
        entry = self._vectors.get(vector_id)
        if entry is None:
            return None
        
        # 更新 LRU 顺序：移动到末尾（最近使用）
        self._vectors.move_to_end(vector_id)
        
        return entry
    
    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新向量
        
        Args:
            vector_id: 向量ID
            vector: 新向量（可选）
            metadata: 新元数据（可选）
            
        Returns:
            是否更新成功
            
        Raises:
            ValueError: 向量维度不匹配或包含无效元素
        """
        if vector_id not in self._vectors:
            return False
        
        # 验证新向量
        if vector is not None:
            if len(vector) != self.dimension:
                raise ValueError(f"Vector dimension mismatch")
            
            # 验证向量元素（防止 NaN/Inf）
            for i, v in enumerate(vector):
                if not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ValueError(
                        f"Invalid vector element at index {i}: {v}. "
                        "All elements must be finite numbers."
                    )
        
        entry = self._vectors[vector_id]
        
        # 更新向量
        if vector is not None:
            entry["vector"] = vector
        
        # 更新元数据
        if metadata is not None:
            entry["metadata"].update(metadata)
        
        entry["updated_at"] = datetime.now().isoformat()
        
        # 更新 LRU 顺序：移动到末尾（最近使用）
        self._vectors.move_to_end(vector_id)
        
        # 自动保存
        if self.auto_save and self.storage_path:
            self.save()
        
        return True
    
    def delete(self, vector_id: str) -> bool:
        """
        删除向量
        
        Args:
            vector_id: 向量ID
            
        Returns:
            是否删除成功
        """
        if vector_id not in self._vectors:
            return False
        
        del self._vectors[vector_id]
        
        # 自动保存
        if self.auto_save and self.storage_path:
            self.save()
        
        return True
    
    def count(self) -> int:
        """获取向量数量"""
        return len(self._vectors)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            包含向量数量、内存占用等统计信息
        """
        total_vectors = len(self._vectors)
        
        # 估算内存占用（每个 float 约 8 字节）
        vector_memory = total_vectors * self.dimension * 8 if total_vectors > 0 else 0
        
        # 元数据内存估算
        metadata_memory = sum(
            len(str(entry.get("metadata", {}))) 
            for entry in self._vectors.values()
        )
        
        return {
            "total_vectors": total_vectors,
            "max_size": self.max_size,
            "dimension": self.dimension,
            "vector_memory_bytes": vector_memory,
            "metadata_memory_bytes": metadata_memory,
            "total_memory_bytes": vector_memory + metadata_memory,
            "utilization": total_vectors / self.max_size if self.max_size else None,
            "evicted_count": self._evicted_count,
        }
    
    def clear(self) -> int:
        """
        清空所有向量
        
        Returns:
            清除的向量数量
        """
        count = len(self._vectors)
        self._vectors.clear()
        
        if self.auto_save and self.storage_path:
            self.save()
        
        logger.info(f"Cleared {count} vectors from VectorStore")
        return count
    
    # ========== 搜索功能 ==========
    
    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        threshold: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相似向量
        
        Args:
            query_vector: 查询向量
            top_k: 返回数量
            threshold: 相似度阈值
            filter: 元数据过滤条件
            
        Returns:
            搜索结果列表，包含 id, similarity, metadata
        """
        if not self._vectors:
            return []
        
        # 计算相似度
        results = []
        
        for vector_id, entry in self._vectors.items():
            # 应用过滤
            if filter:
                if not self._match_filter(entry["metadata"], filter):
                    continue
            
            # 计算相似度
            similarity = self.cosine_similarity(query_vector, entry["vector"])
            
            # 应用阈值
            if threshold is not None and similarity < threshold:
                continue
            
            results.append({
                "id": vector_id,
                "similarity": similarity,
                "metadata": entry["metadata"]
            })
        
        # 按相似度排序
        results.sort(key=lambda x: x["similarity"], reverse=True)
        
        # 返回 Top-K
        return results[:top_k]
    
    def _match_filter(
        self,
        metadata: Dict[str, Any],
        filter: Dict[str, Any]
    ) -> bool:
        """检查元数据是否匹配过滤条件"""
        for key, value in filter.items():
            if metadata.get(key) != value:
                return False
        return True
    
    # ========== 相似度计算 ==========
    
    def cosine_similarity(
        self,
        v1: List[float],
        v2: List[float]
    ) -> float:
        """
        计算余弦相似度
        
        Args:
            v1: 向量1
            v2: 向量2
            
        Returns:
            相似度 (-1.0 到 1.0)
        """
        if len(v1) != len(v2):
            raise ValueError("Vector dimensions must match")
        
        # 计算点积
        dot_product = sum(a * b for a, b in zip(v1, v2))
        
        # 计算模长
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        
        # 避免除以零
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    # ========== 持久化 ==========
    
    def save(self) -> bool:
        """保存到文件"""
        if not self.storage_path or not self._storage_file:
            logger.warning("No storage path configured")
            return False
        
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            
            data = {
                "dimension": self.dimension,
                "vectors": self._vectors,
                "saved_at": datetime.now().isoformat()
            }
            
            with open(str(self._storage_file), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            
            logger.info(f"Saved {len(self._vectors)} vectors to {self._storage_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save vectors: {e}")
            return False
    
    def load(self) -> bool:
        """
        从文件加载
        
        如果加载的向量数超过 max_size，会触发 LRU 淘汰（保留最近的向量）。
        
        Returns:
            是否加载成功
        """
        if not self._storage_file or not self._storage_file.exists():
            return False
        
        try:
            with open(self._storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证维度
            if data.get("dimension") != self.dimension:
                logger.warning(
                    f"Dimension mismatch in stored data: "
                    f"{data.get('dimension')} vs {self.dimension}"
                )
            
            loaded_vectors = data.get("vectors", {})
            
            # 转换为 OrderedDict（保持插入顺序）
            loaded_vectors = OrderedDict(loaded_vectors)
            
            # 检查是否超过 max_size
            if self.max_size and len(loaded_vectors) > self.max_size:
                logger.warning(
                    f"Loaded {len(loaded_vectors)} vectors exceeds max_size={self.max_size}, "
                    f"will keep only the most recent {self.max_size}"
                )
                
                # 保留最近的向量（假设 OrderedDict 保持插入顺序）
                # 将字典转换为列表，保留最后 max_size 个
                items = list(loaded_vectors.items())
                kept_items = items[-self.max_size:]
                evicted_items = items[:-self.max_size]
                
                # 触发淘汰回调
                for evicted_id, evicted_entry in evicted_items:
                    self._evicted_count += 1
                    if self.on_evict:
                        try:
                            self.on_evict(evicted_id, evicted_entry)
                        except Exception as e:
                            logger.error(f"Eviction callback failed for {evicted_id}: {e}")
                
                # 重建字典
                self._vectors = OrderedDict(kept_items)
            else:
                self._vectors = OrderedDict(loaded_vectors)
            
            logger.info(f"Loaded {len(self._vectors)} vectors from {self._storage_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load vectors: {e}")
            return False