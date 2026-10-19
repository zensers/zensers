# -*- coding: utf-8 -*-
"""
知识标准化器

对提取的知识进行标准化处理：
- 术语统一
- 单位统一
- 时间标准化
- 实体消歧

设计参考: CONTEXT_COMPRESSION.md 第 11.2 节
"""

__all__ = ["KnowledgeNormalizer"]

import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class KnowledgeNormalizer:
    """
    知识标准化器
    
    核心功能：
    - 术语统一：宁德时代 = CATL
    - 单位统一：1.2万亿 = 12000亿
    - 时间标准化：去年 = 2024年
    - 实体消歧：苹果 → 公司 or 水果
    
    参考：CONTEXT_COMPRESSION.md 第 11.2 节
    """
    
    # 术语映射
    TERM_MAPPINGS = {
        # 公司别名
        "CATL": "宁德时代",
        "BYD": "比亚迪",
        "Tesla": "特斯拉",
        # 单位映射
        "万亿": "10000亿",
        "千万": "1000万",
        "百万": "100万",
    }
    
    # 时间映射
    TIME_MAPPINGS = {
        "去年": "2024年",
        "今年": "2025年",
        "去年上半年": "2024年上半年",
        "去年下半年": "2024年下半年",
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化标准化器"""
        self.config = config or {}
        self.current_year = datetime.now().year
        logger.info("KnowledgeNormalizer initialized")
    
    def normalize(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        标准化实体和关系
        
        Args:
            entities: 实体列表
            relations: 关系列表
            
        Returns:
            标准化后的实体和关系列表
        """
        normalized_entities = []
        normalized_relations = []
        
        # 标准化实体
        for entity in entities:
            normalized = self._normalize_entity(entity)
            normalized_entities.append(normalized)
        
        # 标准化关系
        for relation in relations:
            normalized = self._normalize_relation(relation)
            normalized_relations.append(normalized)
        
        return normalized_entities, normalized_relations
    
    def _normalize_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """标准化单个实体"""
        entity = entity.copy()
        
        # 术语统一
        name = entity.get("name", "")
        if name in self.TERM_MAPPINGS:
            normalized_name = self.TERM_MAPPINGS[name]
            if "aliases" not in entity:
                entity["aliases"] = []
            if name not in entity["aliases"]:
                entity["aliases"].append(name)
            entity["name"] = normalized_name
        
        # 标准化别名
        aliases = entity.get("aliases", [])
        normalized_aliases = []
        for alias in aliases:
            if alias in self.TERM_MAPPINGS:
                normalized_aliases.append(self.TERM_MAPPINGS[alias])
            else:
                normalized_aliases.append(alias)
        entity["aliases"] = list(set(normalized_aliases))
        
        return entity
    
    def _normalize_relation(self, relation: Dict[str, Any]) -> Dict[str, Any]:
        """标准化单个关系"""
        relation = relation.copy()
        
        # 术语统一
        source = relation.get("source_entity", "")
        target = relation.get("target_entity", "")
        
        if source in self.TERM_MAPPINGS:
            relation["source_entity"] = self.TERM_MAPPINGS[source]
        
        if target in self.TERM_MAPPINGS:
            relation["target_entity"] = self.TERM_MAPPINGS[target]
        
        return relation
    
    def normalize_text(self, text: str) -> str:
        """
        标准化文本
        
        Args:
            text: 原始文本
            
        Returns:
            标准化后的文本
        """
        result = text
        
        # 时间标准化
        for old, new in self.TIME_MAPPINGS.items():
            result = result.replace(old, new)
        
        # 术语标准化
        for old, new in self.TERM_MAPPINGS.items():
            result = result.replace(old, new)
        
        return result
    
    def normalize_value(self, value: str) -> str:
        """
        标准化数值
        
        Args:
            value: 数值字符串
            
        Returns:
            标准化后的数值
        """
        # 处理 "1.2万亿" 格式
        match = re.match(r'([\d.]+)\s*万亿', value)
        if match:
            num = float(match.group(1))
            return f"{num * 10000}亿"
        
        # 处理 "1.2亿" 格式
        match = re.match(r'([\d.]+)\s*亿', value)
        if match:
            return f"{match.group(1)}亿"
        
        return value