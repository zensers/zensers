# -*- coding: utf-8 -*-
"""
洞察存储
========

存储和管理研究发现。

Phase 10 重构：继承 SQLiteStore 基类

v1.2 重构：
- 遗留方法标记 @deprecated
- 推荐使用统一的 BaseStore 接口
"""

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.storage.connection_manager import ConnectionManager

from src.core.storage.base_store import SQLiteStore
from src.core.utils.deprecation import deprecated


@dataclass
class Insight:
    """洞察数据模型"""
    insight_id: str
    research_id: str
    topic: str = ""
    content: str = ""
    
    # 支撑
    supporting_data: List[str] = field(default_factory=list)
    source_ref: str = ""
    
    # 元数据
    confidence: str = "medium"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "insight_id": self.insight_id,
            "research_id": self.research_id,
            "topic": self.topic,
            "content": self.content,
            "confidence": self.confidence,
        }


class InsightStore(SQLiteStore[Insight]):
    """洞察存储"""
    
    def __init__(
        self,
        db: Optional[sqlite3.Connection] = None,
        db_path: Optional[Union[str, object]] = None,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "knowledge_bank",
        **kwargs
    ):
        """初始化洞察存储"""
        if connection_manager is not None:
            super().__init__(
                connection_manager=connection_manager,
                connection_name=connection_name,
                table_name="insights",
                **kwargs
            )
        elif db is not None:
            super().__init__(
                external_db=db,
                table_name="insights",
                auto_init=False,
                **kwargs
            )
        elif db_path is not None:
            super().__init__(
                db_path=db_path,
                table_name="insights",
                **kwargs
            )
        else:
            raise ValueError("Must provide db, db_path, or connection_manager")
    
    def _create_table(self) -> None:
        """创建表"""
        from src.core.storage.schemas import INSIGHTS_SCHEMA
        if not INSIGHTS_SCHEMA.exists(self.db):
            INSIGHTS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row: sqlite3.Row) -> Insight:
        """行转对象"""
        return Insight(
            insight_id=row['insight_id'],
            research_id=row['research_id'],
            topic=row['topic'] or "",
            content=row['content'] or "",
            supporting_data=json.loads(row['supporting_data']) if row['supporting_data'] else [],
            source_ref=row['source_ref'] or "",
            confidence=row['confidence']
        )
    
    def _item_to_dict(self, item: Insight) -> Dict[str, Any]:
        """对象转字典"""
        return {
            'insight_id': item.insight_id,
            'research_id': item.research_id,
            'topic': item.topic,
            'content': item.content,
            'supporting_data': json.dumps(item.supporting_data),
            'source_ref': item.source_ref,
            'confidence': item.confidence
        }
    
    def _get_id(self, item: Insight) -> str:
        return item.insight_id
    
    def _get_id_column(self) -> str:
        """获取 ID 列名"""
        return "insight_id"
    
    def _get_allowed_columns(self) -> List[str]:
        return [
            'insight_id', 'research_id', 'topic', 'content',
            'supporting_data', 'source_ref', 'confidence', 'created_at'
        ]
    
    # === 公共方法 ===
    
    @deprecated(replacement="add()", version="2.0")
    def create(self, insight: Insight) -> str:
        """
        创建洞察
        
        .. deprecated:: 1.2
            使用 :meth:`add` 方法替代。
        """
        self.db.execute("""
            INSERT INTO insights (
                insight_id, research_id, topic, content,
                supporting_data, source_ref, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            insight.insight_id,
            insight.research_id,
            insight.topic,
            insight.content,
            json.dumps(insight.supporting_data),
            insight.source_ref,
            insight.confidence,
            datetime.now().isoformat()
        ))
        
        self.db.commit()
        return insight.insight_id
    
    @deprecated(replacement="get()", version="2.0")
    def get(self, insight_id: str) -> Optional[Insight]:
        """
        获取洞察
        
        .. deprecated:: 1.2
            使用继承自 SQLiteStore 的 :meth:`get` 方法。
        """
        cursor = self.db.execute(
            "SELECT * FROM insights WHERE insight_id = ?",
            (insight_id,)
        )
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        return self._row_to_item(row)
    
    @deprecated(replacement="list() with filters", version="2.0")
    def get_by_research(self, research_id: str) -> List[Insight]:
        """
        按研究ID获取洞察列表
        
        .. deprecated:: 1.2
            使用 :meth:`list` 方法替代，使用 filters={"research_id": ...} 参数。
        """
        cursor = self.db.execute(
            "SELECT * FROM insights WHERE research_id = ?",
            (research_id,)
        )
        
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def search(
        self,
        query: str = "",
        topic: Optional[str] = None,
        limit: int = 100
    ) -> List[Insight]:
        """搜索洞察"""
        conditions = []
        params = []
        
        if query:
            conditions.append("content LIKE ?")
            params.append(f"%{query}%")
        
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        
        cursor = self.db.execute(
            f"SELECT * FROM insights WHERE {where_clause} LIMIT ?",
            tuple(params)
        )
        
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计洞察数量"""
        return super().count(filters)
