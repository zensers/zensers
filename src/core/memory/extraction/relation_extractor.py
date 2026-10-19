# -*- coding: utf-8 -*-
"""
关系提取器

从文本中提取实体之间的关系：
- 竞争关系
- 供应关系
- 投资关系
- 属于关系

设计参考: CONTEXT_COMPRESSION.md 第 11.2 节
"""

__all__ = ["RelationExtractor"]

import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Relation:
    """关系数据类"""
    relation_id: str
    source_entity: str
    target_entity: str
    relation_type: str
    context: Optional[str] = None
    confidence: float = 0.8
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class RelationExtractor:
    """
    关系提取器
    
    核心功能：
    - 从文本中提取实体关系
    - 支持多种关系类型
    - 关系置信度计算
    
    关系类型：
    - competes_with: 竞争
    - supplies_to: 供应
    - invests_in: 投资
    - belongs_to: 属于
    
    参考：CONTEXT_COMPRESSION.md 第 11.2 节
    """
    
    # 关系模式
    RELATION_PATTERNS = {
        "competes_with": [
            r"(.+?)与(.+?)竞争",
            r"(.+?)的竞争对手(.+)",
            r"(.+?)和(.+?)竞争",
        ],
        "supplies_to": [
            r"(.+?)向(.+?)供应",
            r"(.+?)是(.+?)的供应商",
            r"(.+?)为(.+?)提供",
        ],
        "invests_in": [
            r"(.+?)投资(.+)",
            r"(.+?)入股(.+)",
        ],
        "belongs_to": [
            r"(.+?)属于(.+)",
            r"(.+?)是(.+?)的",
        ],
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化关系提取器"""
        self.config = config or {}
        self._init_patterns()
        logger.info("RelationExtractor initialized")
    
    def _init_patterns(self):
        """初始化正则模式"""
        self.compiled_patterns = {}
        for rel_type, patterns in self.RELATION_PATTERNS.items():
            self.compiled_patterns[rel_type] = [
                re.compile(p) for p in patterns
            ]
    
    def extract(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        source: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取关系
        
        Args:
            text: 输入文本
            entities: 已识别的实体列表
            source: 来源信息
            
        Returns:
            关系列表
        """
        relations = []
        
        # 基于模式提取关系
        for rel_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    source_name = match.group(1).strip()
                    target_name = match.group(2).strip()
                    
                    relation = self._create_relation(
                        source_entity=source_name,
                        target_entity=target_name,
                        relation_type=rel_type,
                        context=text[max(0, match.start()-20):match.end()+20],
                        source=source
                    )
                    relations.append(relation)
        
        # 基于实体列表提取关系
        if entities:
            relations.extend(self._extract_from_entities(text, entities, source))
        
        return [self._relation_to_dict(r) for r in relations]
    
    def _extract_from_entities(
        self,
        text: str,
        entities: List[Dict[str, Any]],
        source: Optional[Dict[str, Any]]
    ) -> List[Relation]:
        """基于实体列表提取关系"""
        relations = []
        
        # TODO: 实现更复杂的关系提取逻辑
        # 可以使用依存句法分析或 LLM
        
        return relations
    
    def _create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str,
        context: str,
        source: Optional[Dict[str, Any]],
        confidence: float = 0.8
    ) -> Relation:
        """创建关系对象"""
        import uuid
        
        return Relation(
            relation_id=str(uuid.uuid4()),
            source_entity=source_entity,
            target_entity=target_entity,
            relation_type=relation_type,
            context=context,
            confidence=confidence
        )
    
    def _relation_to_dict(self, relation: Relation) -> Dict[str, Any]:
        """将关系转换为字典"""
        result = {
            "relation_id": relation.relation_id,
            "source_entity": relation.source_entity,
            "target_entity": relation.target_entity,
            "relation_type": relation.relation_type,
            "confidence": relation.confidence
        }
        
        if relation.context:
            result["context"] = relation.context
        
        if relation.valid_from:
            result["valid_from"] = relation.valid_from.isoformat()
        
        if relation.valid_until:
            result["valid_until"] = relation.valid_until.isoformat()
        
        return result