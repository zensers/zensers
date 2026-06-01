# -*- coding: utf-8 -*-
"""
数据点存储
========

存储和管理量化数据。

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
class DataPoint:
    """数据点数据模型"""
    data_id: str
    entity_id: str
    metric_name: str       # 营收/市值/市场份额/增长率
    metric_value: str
    unit: str = ""         # 亿元/%/万台
    
    # 时间
    time_period: str = ""  # 2023/2023Q3/2024-03
    
    # 来源
    source_ref: str = ""
    confidence: str = "medium"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "data_id": self.data_id,
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "time_period": self.time_period,
            "confidence": self.confidence,
        }


class DataPointStore(SQLiteStore[DataPoint]):
    """数据点存储"""
    
    def __init__(
        self,
        db: Optional[sqlite3.Connection] = None,
        db_path: Optional[Union[str, object]] = None,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "knowledge_bank",
        **kwargs
    ):
        """初始化数据点存储"""
        if connection_manager is not None:
            super().__init__(
                connection_manager=connection_manager,
                connection_name=connection_name,
                table_name="data_points",
                **kwargs
            )
        elif db is not None:
            super().__init__(
                external_db=db,
                table_name="data_points",
                auto_init=False,
                **kwargs
            )
        elif db_path is not None:
            super().__init__(
                db_path=db_path,
                table_name="data_points",
                **kwargs
            )
        else:
            raise ValueError("Must provide db, db_path, or connection_manager")
    
    def _create_table(self) -> None:
        """创建表"""
        from src.core.storage.schemas import DATA_POINTS_SCHEMA
        if not DATA_POINTS_SCHEMA.exists(self.db):
            DATA_POINTS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row: sqlite3.Row) -> DataPoint:
        """行转对象"""
        return DataPoint(
            data_id=row['data_id'],
            entity_id=row['entity_id'],
            metric_name=row['metric_name'],
            metric_value=row['metric_value'],
            unit=row['unit'] or "",
            time_period=row['time_period'] or "",
            source_ref=row['source_ref'] or "",
            confidence=row['confidence']
        )
    
    def _item_to_dict(self, item: DataPoint) -> Dict[str, Any]:
        """对象转字典"""
        return {
            'data_id': item.data_id,
            'entity_id': item.entity_id,
            'metric_name': item.metric_name,
            'metric_value': item.metric_value,
            'unit': item.unit,
            'time_period': item.time_period,
            'source_ref': item.source_ref,
            'confidence': item.confidence
        }
    
    def _get_id(self, item: DataPoint) -> str:
        return item.data_id
    
    def _get_id_column(self) -> str:
        """获取 ID 列名"""
        return "data_id"
    
    def _get_allowed_columns(self) -> List[str]:
        return [
            'data_id', 'entity_id', 'metric_name', 'metric_value',
            'unit', 'time_period', 'source_ref', 'confidence', 'created_at'
        ]
    
    # === 公共方法 ===
    
    @deprecated(replacement="add()", version="2.0")
    def add_data_point(
        self,
        entity_id: str,
        metric_name: str,
        metric_value: str,
        unit: str = "",
        time_period: str = "",
        source: str = "",
        confidence: float = 1.0
    ) -> str:
        """
        添加数据点
        
        .. deprecated:: 1.2
            使用 :meth:`add` 方法替代。
        """
        data_id = f"data_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        self.db.execute("""
            INSERT INTO data_points (
                data_id, entity_id, metric_name, metric_value,
                unit, time_period, source_ref, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data_id,
            entity_id,
            metric_name,
            metric_value,
            unit,
            time_period,
            source,
            confidence,
            now
        ))
        
        self.db.commit()
        return data_id
    
    @deprecated(replacement="get()", version="2.0")
    def get_data_point(self, data_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取数据点
        
        .. deprecated:: 1.2
            使用 :meth:`get` 方法替代。
        """
        cursor = self.db.execute(
            "SELECT * FROM data_points WHERE data_id = ?",
            (data_id,)
        )
        row = cursor.fetchone()
        return self._row_to_dict_internal(row) if row else None
    
    @deprecated(replacement="list() with filters", version="2.0")
    def search_data_points(
        self,
        query: str = "",
        entity_id: Optional[str] = None,
        metric_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索数据点
        
        .. deprecated:: 1.2
            使用 :meth:`list` 方法替代，使用 filters 参数过滤。
        """
        conditions = []
        params = []
        
        if query:
            conditions.append("metric_name LIKE ?")
            params.append(f"%{query}%")
        
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        
        if metric_name:
            conditions.append("metric_name = ?")
            params.append(metric_name)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        
        cursor = self.db.execute(
            f"SELECT * FROM data_points WHERE {where_clause} LIMIT ?",
            tuple(params)
        )
        
        return [self._row_to_dict_internal(row) for row in cursor.fetchall()]
    
    def update_confidence(self, data_id: str, confidence: str) -> None:
        """更新置信度"""
        self.db.execute(
            "UPDATE data_points SET confidence = ? WHERE data_id = ?",
            (confidence, data_id)
        )
        self.db.commit()
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计数据点数量"""
        return super().count(filters)
    
    # === 内部方法 ===
    
    def _row_to_dict_internal(self, row: sqlite3.Row) -> Dict[str, Any]:
        """内部：行转字典"""
        return {
            "data_id": row[0],
            "entity_id": row[1],
            "metric_name": row[2],
            "metric_value": row[3],
            "unit": row[4] or "",
            "time_period": row[5] or "",
            "source_ref": row[6] or "",
            "confidence": row[7]
        }
    
    def create(self, data_point: DataPoint) -> str:
        """创建数据点（内部方法）"""
        self.db.execute("""
            INSERT INTO data_points (
                data_id, entity_id, metric_name, metric_value,
                unit, time_period, source_ref, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data_point.data_id,
            data_point.entity_id,
            data_point.metric_name,
            data_point.metric_value,
            data_point.unit,
            data_point.time_period,
            data_point.source_ref,
            data_point.confidence,
            datetime.now().isoformat()
        ))
        self.db.commit()
        return data_point.data_id
    
    def get(self, data_id: str) -> Optional[DataPoint]:
        """获取数据点对象（内部方法）"""
        cursor = self.db.execute(
            "SELECT * FROM data_points WHERE data_id = ?",
            (data_id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
