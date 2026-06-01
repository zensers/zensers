# -*- coding: utf-8 -*-
"""
关系存储
========

存储和管理实体间的关系。

Phase 10 重构：继承 SQLiteStore 基类

v1.2 重构：
- 遗留方法标记 @deprecated
- 推荐使用统一的 BaseStore 接口
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.storage.connection_manager import ConnectionManager

from src.core.storage.base_store import SQLiteStore
from src.core.utils.deprecation import deprecated


@dataclass
class Relation:
    """关系数据模型"""
    relation_id: str
    source_entity: str
    target_entity: str
    relation_type: str     # competes_with/supplies_to/invests_in/...
    
    # 上下文
    context: str = ""
    source_ref: str = ""
    
    # 时间有效性
    valid_from: datetime = field(default_factory=datetime.now)
    valid_until: Optional[datetime] = None  # None表示仍有效
    
    # 置信度
    confidence: str = "medium"  # high/medium/low
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "relation_id": self.relation_id,
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "relation_type": self.relation_type,
            "context": self.context,
            "confidence": self.confidence,
        }


class RelationStore(SQLiteStore[Relation]):
    """关系存储"""
    
    def __init__(
        self,
        db: Optional[sqlite3.Connection] = None,
        db_path: Optional[Union[str, object]] = None,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "knowledge_bank",
        **kwargs
    ):
        """初始化关系存储"""
        if connection_manager is not None:
            super().__init__(
                connection_manager=connection_manager,
                connection_name=connection_name,
                table_name="relations",
                **kwargs
            )
        elif db is not None:
            super().__init__(
                external_db=db,
                table_name="relations",
                auto_init=False,
                **kwargs
            )
        elif db_path is not None:
            super().__init__(
                db_path=db_path,
                table_name="relations",
                **kwargs
            )
        else:
            raise ValueError("Must provide db, db_path, or connection_manager")
    
    def _create_table(self) -> None:
        """创建表"""
        from src.core.storage.schemas import RELATIONS_SCHEMA
        if not RELATIONS_SCHEMA.exists(self.db):
            RELATIONS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row: sqlite3.Row) -> Relation:
        """行转对象"""
        return Relation(
            relation_id=row['relation_id'],
            source_entity=row['source_entity'],
            target_entity=row['target_entity'],
            relation_type=row['relation_type'],
            context=row['context'] or "",
            source_ref=row['source_ref'] or "",
            valid_from=datetime.fromisoformat(row['valid_from']),
            valid_until=datetime.fromisoformat(row['valid_until']) if row['valid_until'] else None,
            confidence=row['confidence']
        )
    
    def _item_to_dict(self, item: Relation) -> Dict[str, Any]:
        """对象转字典"""
        return {
            'relation_id': item.relation_id,
            'source_entity': item.source_entity,
            'target_entity': item.target_entity,
            'relation_type': item.relation_type,
            'context': item.context,
            'source_ref': item.source_ref,
            'valid_from': item.valid_from.isoformat(),
            'valid_until': item.valid_until.isoformat() if item.valid_until else None,
            'confidence': item.confidence
        }
    
    def _get_id(self, item: Relation) -> str:
        return item.relation_id
    
    def _get_id_column(self) -> str:
        """获取 ID 列名"""
        return "relation_id"
    
    def _get_allowed_columns(self) -> List[str]:
        return [
            'relation_id', 'source_entity', 'target_entity', 'relation_type',
            'context', 'source_ref', 'valid_from', 'valid_until', 'confidence', 'created_at'
        ]
    
    # === 公共方法 ===
    
    @deprecated(replacement="add()", version="2.0")
    def add_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str,
        context: str = "",
        confidence: float = 1.0,
        source: str = ""
    ) -> str:
        """
        添加关系
        
        .. deprecated:: 1.2
            使用 :meth:`add` 方法替代。
        """
        relation_id = f"relation_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        self.db.execute("""
            INSERT INTO relations (
                relation_id, source_entity, target_entity, relation_type,
                context, source_ref, valid_from, valid_until, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            relation_id,
            source_entity,
            target_entity,
            relation_type,
            context,
            source,
            now,
            None,
            str(confidence),
            now
        ))
        
        self.db.commit()
        return relation_id
    
    @deprecated(replacement="get()", version="2.0")
    def get_relation(self, relation_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取关系
        
        .. deprecated:: 1.2
            使用 :meth:`get` 方法替代。
        """
        cursor = self.db.execute(
            "SELECT * FROM relations WHERE relation_id = ?",
            (relation_id,)
        )
        row = cursor.fetchone()
        return self._row_to_dict_internal(row) if row else None
    
    @deprecated(replacement="list() with filters", version="2.0")
    def search_relations(
        self,
        query: str = "",
        relation_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索关系
        
        .. deprecated:: 1.2
            使用 :meth:`list` 方法替代，使用 filters 参数过滤。
        """
        conditions = []
        params = []
        
        if query:
            conditions.append("context LIKE ?")
            params.append(f"%{query}%")
        
        if relation_type:
            conditions.append("relation_type = ?")
            params.append(relation_type)
        
        if entity_id:
            conditions.append("(source_entity = ? OR target_entity = ?)")
            params.extend([entity_id, entity_id])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        
        cursor = self.db.execute(
            f"SELECT * FROM relations WHERE {where_clause} LIMIT ?",
            tuple(params)
        )
        
        return [self._row_to_dict_internal(row) for row in cursor.fetchall()]
    
    def update_confidence(self, relation_id: str, confidence: str) -> None:
        """更新置信度"""
        self.db.execute(
            "UPDATE relations SET confidence = ? WHERE relation_id = ?",
            (confidence, relation_id)
        )
        self.db.commit()
    
    def invalidate(self, relation_id: str) -> None:
        """使关系失效"""
        self.db.execute(
            "UPDATE relations SET valid_until = ? WHERE relation_id = ?",
            (datetime.now().isoformat(), relation_id)
        )
        self.db.commit()
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计关系数量"""
        return super().count(filters)
    
    # === 内部方法 ===
    
    def _row_to_dict_internal(self, row: sqlite3.Row) -> Dict[str, Any]:
        """内部：行转字典"""
        return {
            "relation_id": row[0],
            "source_entity": row[1],
            "target_entity": row[2],
            "relation_type": row[3],
            "context": row[4] or "",
            "source_ref": row[5] or "",
            "valid_from": row[6],
            "valid_until": row[7],
            "confidence": row[8]
        }
    
    def create(self, relation: Relation) -> str:
        """创建关系（内部方法）"""
        self.db.execute("""
            INSERT INTO relations (
                relation_id, source_entity, target_entity, relation_type,
                context, source_ref, valid_from, valid_until, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            relation.relation_id,
            relation.source_entity,
            relation.target_entity,
            relation.relation_type,
            relation.context,
            relation.source_ref,
            relation.valid_from.isoformat(),
            relation.valid_until.isoformat() if relation.valid_until else None,
            relation.confidence,
            datetime.now().isoformat()
        ))
        self.db.commit()
        return relation.relation_id
    
    def get(self, relation_id: str) -> Optional[Relation]:
        """获取关系对象（内部方法）"""
        cursor = self.db.execute(
            "SELECT * FROM relations WHERE relation_id = ?",
            (relation_id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
