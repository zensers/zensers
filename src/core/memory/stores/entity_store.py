# -*- coding: utf-8 -*-
"""
实体存储
========

存储和管理实体知识。

Phase 10 重构：
- 继承 SQLiteStore 基类
- 支持 ConnectionManager 注入
- 保持向后兼容

v1.2 重构：
- 遗留方法标记 @deprecated
- 推荐使用统一的 BaseStore 接口
"""

import sqlite3
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.storage.connection_manager import ConnectionManager

from src.core.storage.base_store import SQLiteStore, NotFoundError, ValidationError, DuplicateError
from src.core.storage.schema_registry import SchemaRegistry
from src.core.utils.deprecation import deprecated


@dataclass
class Entity:
    """实体数据模型"""
    entity_id: str
    entity_type: str       # company/person/technology/product/concept
    name: str
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    
    # 元数据
    first_seen: datetime = field(default_factory=datetime.now)
    last_mentioned: datetime = field(default_factory=datetime.now)
    mention_count: int = 1
    importance_score: float = 0.5
    
    # 扩展属性
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "mention_count": self.mention_count,
            "importance_score": self.importance_score,
        }


class EntityStore(SQLiteStore[Entity]):
    """
    实体存储
    
    Phase 10 重构：继承 SQLiteStore，支持多种连接模式。
    
    用法：
        # 方式 1：ConnectionManager 注入（推荐）
        manager = ConnectionManager(base_path)
        store = EntityStore(connection_manager=manager)
        
        # 方式 2：外部连接（兼容模式）
        conn = sqlite3.connect("knowledge_bank.db")
        store = EntityStore(external_db=conn)
        
        # 方式 3：自管理连接（遗留模式）
        store = EntityStore(db_path="path/to/db")
    """
    
    def __init__(
        self,
        db: Optional[sqlite3.Connection] = None,
        db_path: Optional[Union[str, object]] = None,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "knowledge_bank",
        **kwargs
    ):
        """
        初始化实体存储
        
        Args:
            db: 外部连接（兼容模式）
            db_path: 数据库路径（自管理模式）
            connection_manager: 连接管理器（推荐）
            connection_name: 连接名称
        """
        # 确定连接模式
        if connection_manager is not None:
            # 模式 1：ConnectionManager 注入
            super().__init__(
                connection_manager=connection_manager,
                connection_name=connection_name,
                table_name="entities",
                **kwargs
            )
        elif db is not None:
            # 模式 2：外部连接（兼容模式）
            super().__init__(
                external_db=db,
                table_name="entities",
                auto_init=False,  # 表由外部创建
                **kwargs
            )
        elif db_path is not None:
            # 模式 3：自管理连接
            super().__init__(
                db_path=db_path,
                table_name="entities",
                **kwargs
            )
        else:
            raise ValueError("Must provide db, db_path, or connection_manager")
    
    # === SQLiteStore 抽象方法实现 ===
    
    def _create_table(self) -> None:
        """创建表（使用 SchemaRegistry）"""
        from src.core.storage.schemas import ENTITIES_SCHEMA
        if not ENTITIES_SCHEMA.exists(self.db):
            ENTITIES_SCHEMA.create(self.db)
    
    def _row_to_item(self, row: sqlite3.Row) -> Entity:
        """行转对象"""
        return Entity(
            entity_id=row['entity_id'],
            entity_type=row['entity_type'],
            name=row['name'],
            aliases=json.loads(row['aliases']) if row['aliases'] else [],
            description=row['description'] or "",
            first_seen=datetime.fromisoformat(row['first_seen']),
            last_mentioned=datetime.fromisoformat(row['last_mentioned']),
            mention_count=row['mention_count'],
            importance_score=row['importance_score'] if 'importance_score' in row.keys() else 0.5,
            properties=json.loads(row['properties']) if 'properties' in row.keys() and row['properties'] else {}
        )
    
    def _item_to_dict(self, item: Entity) -> Dict[str, Any]:
        """对象转字典"""
        return {
            'entity_id': item.entity_id,
            'entity_type': item.entity_type,
            'name': item.name,
            'aliases': json.dumps(item.aliases),
            'description': item.description,
            'first_seen': item.first_seen.isoformat(),
            'last_mentioned': item.last_mentioned.isoformat(),
            'mention_count': item.mention_count,
            'importance_score': item.importance_score,
            'properties': json.dumps(item.properties)
        }
    
    def _get_id(self, item: Entity) -> str:
        """获取 ID"""
        return item.entity_id
    
    def _get_id_column(self) -> str:
        """获取 ID 列名"""
        return "entity_id"
    
    def _get_allowed_columns(self) -> List[str]:
        """获取允许的列名白名单"""
        return [
            'entity_id', 'entity_type', 'name', 'aliases', 'description',
            'first_seen', 'last_mentioned', 'mention_count', 'importance_score', 'properties'
        ]
    
    # === 公共方法（保持向后兼容）===
    
    # Note: Uses custom INSERT logic for special deduplication behavior.
    # Does not use inherited SQLiteStore.add() method.
    @deprecated(replacement="add()", version="2.0")
    def add_entity(
        self,
        entity_type: str,
        name: str,
        aliases: Optional[List[str]] = None,
        description: str = ""
    ) -> str:
        """
        添加实体（如果已存在则增加提及次数）
        
        .. deprecated:: 1.2
            使用 :meth:`add` 方法替代。
        
        使用 INSERT OR IGNORE + UPDATE 模式避免竞争条件。
        
        Args:
            entity_type: 实体类型
            name: 实体名称
            aliases: 别名列表
            description: 描述
        
        Returns:
            实体ID
        """
        # 创建新实体 ID
        entity_id = f"entity_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        try:
            # 尝试插入新实体
            self.db.execute("""
                INSERT INTO entities (
                    entity_id, entity_type, name, aliases, description,
                    first_seen, last_mentioned, mention_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id,
                entity_type,
                name,
                json.dumps(aliases or []),
                description,
                now,
                now,
                1
            ))
            self.db.commit()
            return entity_id
        except sqlite3.IntegrityError:
            # 名称已存在（UNIQUE 约束），更新提及次数
            self.db.rollback()  # 回滚失败的事务
            cursor = self.db.execute(
                "SELECT entity_id FROM entities WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            if row:
                existing_id = row[0]
                self.update_mention(existing_id)
                return existing_id
            # 如果还是找不到，重新抛出异常
            raise
    
    @deprecated(replacement="get()", version="2.0")
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取实体
        
        .. deprecated:: 1.2
            使用 :meth:`get` 方法替代，返回 Entity 对象。
        
        Args:
            entity_id: 实体ID
        
        Returns:
            实体字典，不存在返回None
        """
        cursor = self.db.execute(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,)
        )
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        return self._row_to_dict_internal(row)
    
    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        通过名称或别名获取实体
        
        Args:
            name: 实体名称或别名
        
        Returns:
            实体字典，不存在返回None
        """
        # 先尝试精确匹配名称
        cursor = self.db.execute(
            "SELECT * FROM entities WHERE name = ?",
            (name,)
        )
        
        row = cursor.fetchone()
        if row:
            return self._row_to_dict_internal(row)
        
        # 尝试匹配别名（使用 JSON 函数优化）
        # SQLite json_each 将 JSON 数组展开为行，避免加载所有实体
        try:
            cursor = self.db.execute(
                """SELECT DISTINCT e.* FROM entities e, json_each(e.aliases) j
                   WHERE j.value = ?""",
                (name,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict_internal(row)
        except sqlite3.OperationalError:
            # Fallback: 如果 JSON 函数不可用，使用 LIKE 模式
            # 注意：这是降级方案，性能较低
            cursor = self.db.execute(
                "SELECT * FROM entities WHERE aliases LIKE ?",
                (f'%"{name}"%',)
            )
            for row in cursor.fetchall():
                try:
                    aliases = json.loads(row[3]) if row[3] else []
                    if name in aliases:
                        return self._row_to_dict_internal(row)
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return None
    
    @deprecated(replacement="list() with filters", version="2.0")
    def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索实体
        
        .. deprecated:: 1.2
            使用 :meth:`list` 方法替代，使用 filters 参数过滤。
        
        Args:
            query: 搜索关键词（空字符串返回所有）
            entity_type: 过滤实体类型（可选）
            limit: 最大返回数量
        
        Returns:
            匹配的实体列表
        """
        if query:
            if entity_type:
                cursor = self.db.execute(
                    """SELECT * FROM entities 
                       WHERE (name LIKE ? OR description LIKE ?) 
                       AND entity_type = ?
                       ORDER BY mention_count DESC
                       LIMIT ?""",
                    (f"%{query}%", f"%{query}%", entity_type, limit)
                )
            else:
                cursor = self.db.execute(
                    """SELECT * FROM entities 
                       WHERE name LIKE ? OR description LIKE ?
                       ORDER BY mention_count DESC
                       LIMIT ?""",
                    (f"%{query}%", f"%{query}%", limit)
                )
        else:
            if entity_type:
                cursor = self.db.execute(
                    """SELECT * FROM entities 
                       WHERE entity_type = ?
                       ORDER BY mention_count DESC
                       LIMIT ?""",
                    (entity_type, limit)
                )
            else:
                cursor = self.db.execute(
                    """SELECT * FROM entities 
                       ORDER BY mention_count DESC
                       LIMIT ?""",
                    (limit,)
                )
        
        return [self._row_to_dict_internal(row) for row in cursor.fetchall()]
    
    def update_mention(self, entity_id: str) -> None:
        """
        更新实体提及次数和最后提及时间
        
        Args:
            entity_id: 实体ID
        """
        self.db.execute("""
            UPDATE entities 
            SET mention_count = mention_count + 1,
                last_mentioned = ?
            WHERE entity_id = ?
        """, (datetime.now().isoformat(), entity_id))
        self.db.commit()
    
    # === 内部方法 ===
    
    def _row_to_dict_internal(self, row: sqlite3.Row) -> Dict[str, Any]:
        """内部：行转字典"""
        return {
            "entity_id": row[0],
            "entity_type": row[1],
            "name": row[2],
            "aliases": json.loads(row[3]) if row[3] else [],
            "description": row[4] or "",
            "first_seen": row[5],
            "last_mentioned": row[6],
            "mention_count": row[7]
        }
    
    def create(self, entity: Entity) -> str:
        """创建实体（内部方法）"""
        self.db.execute("""
            INSERT INTO entities (
                entity_id, entity_type, name, aliases, description,
                first_seen, last_mentioned, mention_count, importance_score, properties
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity.entity_id,
            entity.entity_type,
            entity.name,
            json.dumps(entity.aliases),
            entity.description,
            entity.first_seen.isoformat(),
            entity.last_mentioned.isoformat(),
            entity.mention_count,
            entity.importance_score,
            json.dumps(entity.properties)
        ))
        
        self.db.commit()
        return entity.entity_id
    
    def get(self, entity_id: str) -> Optional[Entity]:
        """获取实体对象（内部方法）"""
        cursor = self.db.execute(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,)
        )
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        return self._row_to_item(row)
    
    def get_by_type(self, entity_type: str, limit: int = 100) -> List[Entity]:
        """按类型获取实体对象列表（内部方法）"""
        results = self.search_entities("", entity_type=entity_type, limit=limit)
        return [Entity(
            entity_id=r["entity_id"],
            entity_type=r["entity_type"],
            name=r["name"],
            aliases=r["aliases"],
            description=r["description"],
            mention_count=r["mention_count"]
        ) for r in results]
    
    def get_top_entities(self, limit: int = 10) -> List[Entity]:
        """获取高频实体对象列表（内部方法）"""
        results = self.search_entities("", limit=limit)
        return [Entity(
            entity_id=r["entity_id"],
            entity_type=r["entity_type"],
            name=r["name"],
            aliases=r["aliases"],
            description=r["description"],
            mention_count=r["mention_count"]
        ) for r in results]
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计实体数量"""
        return super().count(filters)
