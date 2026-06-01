# -*- coding: utf-8 -*-
"""
知识提取器 Pipeline

整合实体识别、关系提取、事实验证、知识标准化的完整 Pipeline

设计参考: CONTEXT_COMPRESSION.md 第 11.2 节
"""

__all__ = ["KnowledgeExtractor"]

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from .entity_extractor import EntityExtractor
from .relation_extractor import RelationExtractor
from .fact_verifier import FactVerifier
from .knowledge_normalizer import KnowledgeNormalizer

logger = logging.getLogger(__name__)


@dataclass
class StructuredKnowledge:
    """结构化知识"""
    entities: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    data_points: List[Dict[str, Any]]
    provenance: Dict[str, Any]
    confidence: float
    extracted_at: datetime = field(default_factory=datetime.now)


class KnowledgeExtractor:
    """
    知识提取器 Pipeline
    
    完整的 4 步提取流程：
    1. 实体识别 - EntityExtractor
    2. 关系提取 - RelationExtractor
    3. 事实验证 - FactVerifier
    4. 知识标准化 - KnowledgeNormalizer
    
    参考：CONTEXT_COMPRESSION.md 第 11.4 节
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化知识提取器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 初始化各组件
        self.entity_extractor = EntityExtractor(
            config=self.config.get("entity", {})
        )
        self.relation_extractor = RelationExtractor(
            config=self.config.get("relation", {})
        )
        self.fact_verifier = FactVerifier(
            config=self.config.get("verification", {})
        )
        self.normalizer = KnowledgeNormalizer(
            config=self.config.get("normalization", {})
        )
        
        logger.info("KnowledgeExtractor initialized")
    
    async def extract(
        self,
        text: str,
        source: Optional[Dict[str, Any]] = None
    ) -> StructuredKnowledge:
        """
        从文本中提取结构化知识
        
        Args:
            text: 输入文本
            source: 来源信息
            
        Returns:
            结构化知识
        """
        # Step 1: 实体识别
        entities = self.entity_extractor.extract(text, source)
        logger.debug(f"Extracted {len(entities)} entities")
        
        # Step 2: 关系提取
        relations = self.relation_extractor.extract(text, entities, source)
        logger.debug(f"Extracted {len(relations)} relations")
        
        # Step 3: 事实验证
        verified_entities, verified_relations = self.fact_verifier.verify(
            entities, relations, [source] if source else None
        )
        logger.debug(f"Verified {len(verified_entities)} entities, {len(verified_relations)} relations")
        
        # Step 4: 知识标准化
        normalized_entities, normalized_relations = self.normalizer.normalize(
            verified_entities, verified_relations
        )
        logger.debug(f"Normalized {len(normalized_entities)} entities, {len(normalized_relations)} relations")
        
        # 构建结果
        data_points = self._extract_data_points(text, normalized_entities)
        
        # 计算整体置信度
        confidence = self._calculate_confidence(
            normalized_entities, normalized_relations
        )
        
        return StructuredKnowledge(
            entities=normalized_entities,
            relations=normalized_relations,
            data_points=data_points,
            provenance=source or {},
            confidence=confidence
        )
    
    def _extract_data_points(
        self,
        text: str,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """提取数据点"""
        import re
        
        data_points = []
        
        # 提取数值型数据
        patterns = [
            r'(\d+(?:\.\d+)?)\s*(万亿|亿|万|%)',
            r'市场份额[：:]\s*(\d+(?:\.\d+)?)\s*%',
            r'增长[：:]\s*(\d+(?:\.\d+)?)\s*%',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                data_points.append({
                    "value": match.group(1),
                    "unit": match.group(2) if len(match.groups()) > 1 else "",
                    "context": text[max(0, match.start()-10):match.end()+10]
                })
        
        return data_points
    
    def _calculate_confidence(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]]
    ) -> float:
        """计算整体置信度"""
        if not entities and not relations:
            return 0.0
        
        entity_confidence = sum(e.get("confidence", 0) for e in entities) / len(entities) if entities else 0
        relation_confidence = sum(r.get("confidence", 0) for r in relations) / len(relations) if relations else 0
        
        # 加权平均
        total = len(entities) + len(relations)
        if total == 0:
            return 0.0
        
        weighted = (entity_confidence * len(entities) + relation_confidence * len(relations)) / total
        
        return round(weighted, 2)