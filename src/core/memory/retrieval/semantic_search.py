# -*- coding: utf-8 -*-
"""
语义检索

实现基于向量的语义检索功能：
- 向量相似度搜索
- 关键词扩展
- 结果排序和加权

设计目标：
- 支持 Top-K 检索
- 支持元数据过滤
- 支持结果加权
"""

__all__ = ["SemanticSearch"]

import logging
import re
from typing import Dict, Any, List, Optional, Callable, Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """嵌入器协议"""
    
    def embed(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        ...
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量"""
        ...


class SemanticSearch:
    """
    语义检索器
    
    核心功能：
    - 向量相似度搜索
    - 关键词扩展
    - 结果排序和加权
    
    设计特点：
    - 支持自定义嵌入器
    - 支持多种检索策略
    - 支持结果后处理
    
    参考：CONTEXT_COMPRESSION.md 第 13 节检索增强策略
    """
    
    # 默认配置
    DEFAULT_TOP_K = 10
    DEFAULT_SIMILARITY_THRESHOLD = 0.0
    
    # 同义词表（市场研究领域）
    SYNONYMS = {
        "电动汽车": ["电动车", "EV", "新能源车"],
        "新能源汽车": ["电动车", "新能源车", "电动汽车"],
        "电池": ["锂电池", "动力电池"],
        "市场份额": ["市占率", "市场占有率"],
        "营收": ["收入", "营业收入"],
        "增长率": ["增速", "增长速度"],
    }
    
    # 缩写展开
    ABBREVIATIONS = {
        "CATL": "宁德时代",
        "BYD": "比亚迪",
        "EV": "电动汽车",
        "NEV": "新能源汽车",
    }
    
    def __init__(
        self,
        vector_store: Optional[Any] = None,
        embedder: Optional[Embedder] = None,
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        boost_field: Optional[str] = None,
        enable_synonym_expansion: bool = False,
        enable_abbreviation_expansion: bool = False
    ):
        """
        初始化语义检索器
        
        Args:
            vector_store: 向量存储
            embedder: 嵌入器（用于文本转向量）
            top_k: 返回结果数量
            similarity_threshold: 相似度阈值
            boost_field: 加权字段名
            enable_synonym_expansion: 启用同义词扩展
            enable_abbreviation_expansion: 启用缩写展开
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.boost_field = boost_field
        self.enable_synonym_expansion = enable_synonym_expansion
        self.enable_abbreviation_expansion = enable_abbreviation_expansion
        
        logger.info(
            f"SemanticSearch initialized: top_k={top_k}, "
            f"threshold={similarity_threshold}, boost_field={boost_field}"
        )
    
    # ========== 搜索接口 ==========
    
    def search(
        self,
        query_vector: List[float],
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        向量搜索
        
        Args:
            query_vector: 查询向量
            filters: 元数据过滤条件
            top_k: 返回数量（覆盖默认值）
            
        Returns:
            搜索结果列表
        """
        if not self.vector_store:
            logger.warning("No vector store configured")
            return []
        
        k = top_k or self.top_k
        
        # 执行搜索
        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=k,
            threshold=self.similarity_threshold,
            filter=filters
        )
        
        # 应用加权
        if self.boost_field:
            results = self._apply_boost(results)
        
        return results
    
    def search_text(
        self,
        query_text: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        文本搜索（需要嵌入器）
        
        Args:
            query_text: 查询文本
            filters: 元数据过滤条件
            top_k: 返回数量
            
        Returns:
            搜索结果列表
        """
        if not self.embedder:
            logger.warning("No embedder configured for text search")
            return []
        
        # 生成查询向量
        query_vector = self.embedder.embed(query_text)
        
        return self.search(query_vector, filters, top_k)
    
    # ========== 关键词扩展 ==========
    
    def expand_keywords(self, query: str) -> List[str]:
        """
        扩展关键词
        
        Args:
            query: 原始查询
            
        Returns:
            扩展后的关键词列表
        """
        keywords = [query]
        
        # 同义词扩展
        if self.enable_synonym_expansion:
            keywords.extend(self._expand_synonyms(query))
        
        # 缩写展开
        if self.enable_abbreviation_expansion:
            keywords.extend(self._expand_abbreviations(query))
        
        # 去重
        return list(set(keywords))
    
    def _expand_synonyms(self, query: str) -> List[str]:
        """同义词扩展"""
        expanded = []
        
        for term, synonyms in self.SYNONYMS.items():
            if term in query:
                expanded.extend(synonyms)
        
        return expanded
    
    def _expand_abbreviations(self, query: str) -> List[str]:
        """缩写展开"""
        expanded = []
        
        for abbr, full in self.ABBREVIATIONS.items():
            if abbr in query:
                expanded.append(full)
        
        return expanded
    
    # ========== 结果处理 ==========
    
    def _apply_boost(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        应用加权
        
        Args:
            results: 原始结果
            
        Returns:
            加权后的结果
        """
        boosted_results = []
        
        for result in results:
            # 获取加权值
            boost_value = result.get("metadata", {}).get(self.boost_field, 0)
            
            # 计算加权分数
            # 公式: final_score = similarity * (1 + boost_value / 10)
            boost_factor = 1.0 + (boost_value / 10.0)
            final_score = result["similarity"] * boost_factor
            
            result_copy = result.copy()
            result_copy["final_score"] = final_score
            boosted_results.append(result_copy)
        
        # 按加权分数重新排序
        boosted_results.sort(key=lambda x: x["final_score"], reverse=True)
        
        return boosted_results
    
    # ========== 配置更新 ==========
    
    def set_top_k(self, top_k: int):
        """设置返回数量"""
        self.top_k = top_k
    
    def set_threshold(self, threshold: float):
        """设置相似度阈值"""
        self.similarity_threshold = threshold
    
    def set_vector_store(self, vector_store: Any):
        """设置向量存储"""
        self.vector_store = vector_store
    
    def set_embedder(self, embedder: Embedder):
        """设置嵌入器"""
        self.embedder = embedder


# 导入 List 类型
from typing import List