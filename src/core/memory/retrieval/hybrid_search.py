# -*- coding: utf-8 -*-
"""
混合检索

实现多策略组合检索功能：
- 向量 + 关键词混合
- 多种融合策略
- 结果过滤和排序

设计目标：
- 支持快速/精确/完整三种模式
- 支持 RRF 和加权融合
- 支持多维度过滤

参考：CONTEXT_COMPRESSION.md 第 13 节检索增强策略
"""

__all__ = ["HybridSearch"]

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HybridSearch:
    """
    混合检索器
    
    核心功能：
    - 向量 + 关键词混合检索
    - 多策略组合
    - 结果融合和去重
    
    设计特点：
    - 支持快速/精确/完整三种模式
    - 支持 RRF 和加权融合
    - 支持时间范围和类型过滤
    
    参考：CONTEXT_COMPRESSION.md 第 13.1 节多策略组合
    """
    
    # 检索模式
    STRATEGY_FAST = "fast"      # 快速模式：向量 + 关键词 (~60ms)
    STRATEGY_PRECISE = "precise"  # 精确模式：向量 + 关键词 + 重排序 (~250ms)
    STRATEGY_FULL = "full"       # 完整模式：全部策略 (~500ms)
    
    # 默认配置
    DEFAULT_TOP_K = 10
    DEFAULT_RRF_K = 60  # RRF 常数
    
    def __init__(
        self,
        vector_store: Optional[Any] = None,
        semantic_search: Optional[Any] = None,
        strategy: str = STRATEGY_FAST,
        top_k: int = DEFAULT_TOP_K
    ):
        """
        初始化混合检索器
        
        Args:
            vector_store: 向量存储
            semantic_search: 语义检索器
            strategy: 检索策略
            top_k: 返回数量
        """
        self.vector_store = vector_store
        self.semantic_search = semantic_search
        self.strategy = strategy
        self.top_k = top_k
        
        logger.info(
            f"HybridSearch initialized: strategy={strategy}, top_k={top_k}"
        )
    
    # ========== 搜索接口 ==========
    
    def search(
        self,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        time_range: Optional[Tuple[str, str]] = None,
        strategy: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        混合检索
        
        Args:
            query_vector: 查询向量
            query_text: 查询文本
            filters: 元数据过滤条件
            time_range: 时间范围 (start, end)
            strategy: 检索策略（覆盖默认值）
            top_k: 返回数量（覆盖默认值）
            
        Returns:
            搜索结果列表
        """
        use_strategy = strategy or self.strategy
        use_top_k = top_k or self.top_k
        
        results = []
        
        # 根据策略执行搜索
        if use_strategy == self.STRATEGY_FAST:
            results = self._fast_search(query_vector, query_text, use_top_k)
        elif use_strategy == self.STRATEGY_PRECISE:
            results = self._precise_search(query_vector, query_text, use_top_k)
        elif use_strategy == self.STRATEGY_FULL:
            results = self._full_search(query_vector, query_text, use_top_k)
        else:
            # 默认使用快速模式
            results = self._fast_search(query_vector, query_text, use_top_k)
        
        # 应用过滤器
        if filters:
            results = self._apply_filters(results, filters)
        
        # 应用时间范围
        if time_range:
            results = self._apply_time_range(results, time_range)
        
        return results[:use_top_k]
    
    # ========== 策略实现 ==========
    
    def _fast_search(
        self,
        query_vector: Optional[List[float]],
        query_text: Optional[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """快速模式：向量 + 关键词"""
        results = []
        
        # 向量搜索
        if query_vector and self.vector_store:
            vector_results = self.vector_store.search(
                query_vector=query_vector,
                top_k=top_k * 2  # 多取一些用于融合
            )
            results.append(vector_results)
        
        # 关键词搜索
        if query_text and self.vector_store:
            keyword_results = self._keyword_search(query_text, top_k * 2)
            results.append(keyword_results)
        
        # 融合结果
        if len(results) > 1:
            return self.reciprocal_rank_fusion(results)
        elif len(results) == 1:
            return results[0][:top_k]
        
        return []
    
    def _precise_search(
        self,
        query_vector: Optional[List[float]],
        query_text: Optional[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """精确模式：向量 + 关键词 + 重排序"""
        # 先执行快速搜索
        results = self._fast_search(query_vector, query_text, top_k * 2)
        
        # 重排序（基于相似度重新计算）
        if results and query_vector:
            results = self._rerank(results, query_vector)
        
        return results[:top_k]
    
    def _full_search(
        self,
        query_vector: Optional[List[float]],
        query_text: Optional[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """完整模式：全部策略"""
        # 执行精确搜索
        results = self._precise_search(query_vector, query_text, top_k * 2)
        
        # 扩展关键词
        if query_text and self.semantic_search:
            expanded_keywords = self.semantic_search.expand_keywords(query_text)
            
            # 对扩展关键词进行搜索
            expanded_results = []
            for keyword in expanded_keywords[:3]:  # 最多扩展3个
                keyword_results = self._keyword_search(keyword, top_k)
                expanded_results.extend(keyword_results)
            
            # 合并结果
            if expanded_results:
                all_results = [results, expanded_results]
                results = self.reciprocal_rank_fusion(all_results)
        
        return results[:top_k]
    
    def _keyword_search(
        self,
        query_text: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """关键词搜索"""
        if not self.vector_store:
            return []
        
        # 遍历所有向量，匹配关键词
        results = []
        
        for vector_id, entry in self.vector_store._vectors.items():
            # 检查元数据中是否包含关键词
            metadata = entry.get("metadata", {})
            text_fields = [
                metadata.get("name", ""),
                metadata.get("desc", ""),
                " ".join(metadata.get("keywords", []))
            ]
            
            combined_text = " ".join(text_fields).lower()
            
            if query_text.lower() in combined_text:
                results.append({
                    "id": vector_id,
                    "similarity": 0.5,  # 关键词匹配默认相似度
                    "metadata": metadata,
                    "match_type": "keyword"
                })
        
        return results[:top_k]
    
    def _rerank(
        self,
        results: List[Dict[str, Any]],
        query_vector: List[float]
    ) -> List[Dict[str, Any]]:
        """重排序结果"""
        if not self.vector_store:
            return results
        
        reranked = []
        for result in results:
            vector_id = result["id"]
            entry = self.vector_store.get(vector_id)
            
            if entry:
                # 重新计算相似度
                similarity = self.vector_store.cosine_similarity(
                    query_vector,
                    entry["vector"]
                )
                
                reranked.append({
                    "id": vector_id,
                    "similarity": similarity,
                    "metadata": result["metadata"],
                    "match_type": "reranked"
                })
        
        # 按相似度排序
        reranked.sort(key=lambda x: x["similarity"], reverse=True)
        
        return reranked
    
    # ========== 结果融合 ==========
    
    def reciprocal_rank_fusion(
        self,
        result_lists: List[List[Dict[str, Any]]],
        k: int = DEFAULT_RRF_K
    ) -> List[Dict[str, Any]]:
        """
        RRF (Reciprocal Rank Fusion) 融合
        
        公式: RRF(d) = Σ 1/(k + rank(d))
        
        Args:
            result_lists: 多个结果列表
            k: RRF 常数
            
        Returns:
            融合后的结果
        """
        scores = {}
        
        for results in result_lists:
            for rank, result in enumerate(results):
                doc_id = result["id"]
                
                if doc_id not in scores:
                    scores[doc_id] = {
                        "id": doc_id,
                        "score": 0.0,
                        "metadata": result.get("metadata", {}),
                        "similarity": result.get("similarity", 0.0)
                    }
                
                # RRF 公式
                scores[doc_id]["score"] += 1.0 / (k + rank + 1)
        
        # 按分数排序
        fused = list(scores.values())
        fused.sort(key=lambda x: x["score"], reverse=True)
        
        return fused
    
    def weighted_fusion(
        self,
        result_lists: List[List[Dict[str, Any]]],
        weights: List[float]
    ) -> List[Dict[str, Any]]:
        """
        加权融合
        
        Args:
            result_lists: 多个结果列表
            weights: 权重列表
            
        Returns:
            融合后的结果
        """
        if len(result_lists) != len(weights):
            raise ValueError("Result lists and weights must have same length")
        
        scores = {}
        
        for results, weight in zip(result_lists, weights):
            for result in results:
                doc_id = result["id"]
                
                if doc_id not in scores:
                    scores[doc_id] = {
                        "id": doc_id,
                        "score": 0.0,
                        "metadata": result.get("metadata", {}),
                        "similarity": result.get("similarity", 0.0)
                    }
                
                # 加权分数
                scores[doc_id]["score"] += result.get("similarity", 0.0) * weight
        
        # 按分数排序
        fused = list(scores.values())
        fused.sort(key=lambda x: x["score"], reverse=True)
        
        return fused
    
    def deduplicate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        结果去重
        
        保留每个 ID 的最高分结果
        
        Args:
            results: 原始结果
            
        Returns:
            去重后的结果
        """
        seen = {}
        
        for result in results:
            doc_id = result["id"]
            
            if doc_id not in seen:
                seen[doc_id] = result
            else:
                # 保留高分
                if result.get("similarity", 0) > seen[doc_id].get("similarity", 0):
                    seen[doc_id] = result
        
        return list(seen.values())
    
    # ========== 过滤功能 ==========
    
    def _apply_filters(
        self,
        results: List[Dict[str, Any]],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """应用元数据过滤"""
        filtered = []
        
        for result in results:
            metadata = result.get("metadata", {})
            match = True
            
            for key, value in filters.items():
                if metadata.get(key) != value:
                    match = False
                    break
            
            if match:
                filtered.append(result)
        
        return filtered
    
    def _apply_time_range(
        self,
        results: List[Dict[str, Any]],
        time_range: Tuple[str, str]
    ) -> List[Dict[str, Any]]:
        """应用时间范围过滤"""
        start_time, end_time = time_range
        filtered = []
        
        for result in results:
            metadata = result.get("metadata", {})
            created_at = metadata.get("created_at", "")
            
            if created_at:
                try:
                    # 检查时间范围
                    if start_time <= created_at <= end_time:
                        filtered.append(result)
                except Exception:
                    pass
        
        return filtered
    
    # ========== 配置更新 ==========
    
    def set_strategy(self, strategy: str):
        """设置检索策略"""
        self.strategy = strategy
    
    def set_top_k(self, top_k: int):
        """设置返回数量"""
        self.top_k = top_k
    
    def set_vector_store(self, vector_store: Any):
        """设置向量存储"""
        self.vector_store = vector_store
    
    def set_semantic_search(self, semantic_search: Any):
        """设置语义检索器"""
        self.semantic_search = semantic_search


# 导入 List 类型
from typing import List