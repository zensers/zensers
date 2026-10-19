# -*- coding: utf-8 -*-
"""
LearningStore - 学习记录存储

Phase 3.7 核心功能: 记录和管理用户学习记录

Phase 10 重构：继承 SQLiteStore 基类

功能:
- 记录学习（用户纠正、错误、模式、偏好）
- 学习去重（Pattern-Key）
- 学习查询
- 学习统计
"""

__all__ = [
    "LearningStore",
    "LearningRecord",
    "LearningCategory",
    "LearningStatus"
]

import sqlite3
import json
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from src.core.storage.connection_manager import ConnectionManager

from src.core.storage.base_store import SQLiteStore

logger = logging.getLogger(__name__)


class LearningCategory(Enum):
    """学习类别"""
    CORRECTION = "correction"    # 用户纠正
    ERROR = "error"              # 错误记录
    PATTERN = "pattern"          # 模式发现
    PREFERENCE = "preference"    # 偏好学习


class LearningStatus(Enum):
    """学习状态"""
    PENDING = "pending"          # 待处理
    PROMOTED = "promoted"        # 已晋升
    IGNORED = "ignored"          # 已忽略


@dataclass
class LearningRecord:
    """学习记录"""
    learning_id: str
    user_id: str
    category: str
    content: str
    session_id: Optional[str] = None
    pattern_key: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    recurrence_count: int = 1
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    promoted_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = datetime.now().isoformat()
        if self.last_seen is None:
            self.last_seen = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningRecord":
        """从字典创建"""
        return cls(**data)


class LearningStore(SQLiteStore[LearningRecord]):
    """
    学习记录存储
    
    Phase 10 重构：继承 SQLiteStore，支持多种连接模式。
    
    管理学习记录的存储、查询和统计。
    支持 Pattern-Key 去重机制。
    """
    
    def __init__(
        self,
        db_path: Optional[Union[str, object]] = None,
        user_id: str = "",
        *,
        db: Optional[sqlite3.Connection] = None,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "learning",
        **kwargs
    ):
        """
        初始化学习存储
        
        Args:
            db_path: 数据库路径（自管理模式）
            user_id: 用户ID
            db: 外部连接（兼容模式）
            connection_manager: 连接管理器（推荐）
            connection_name: 连接名称
        """
        self.user_id = user_id
        
        # 确定连接模式
        if connection_manager is not None:
            super().__init__(
                connection_manager=connection_manager,
                connection_name=connection_name,
                table_name="learnings",
                **kwargs
            )
        elif db is not None:
            super().__init__(
                external_db=db,
                table_name="learnings",
                auto_init=False,
                **kwargs
            )
        elif db_path is not None:
            super().__init__(
                db_path=db_path,
                table_name="learnings",
                **kwargs
            )
        else:
            raise ValueError("Must provide db_path, db, or connection_manager")
        
        logger.info(f"LearningStore initialized for user {user_id}")
    
    # === SQLiteStore 抽象方法实现 ===
    
    def _create_table(self) -> None:
        """创建表（使用 SchemaRegistry）"""
        from src.core.storage.schemas import LEARNINGS_SCHEMA
        if not LEARNINGS_SCHEMA.exists(self.db):
            LEARNINGS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row: sqlite3.Row) -> LearningRecord:
        """行转对象"""
        return LearningRecord(
            learning_id=row['learning_id'],
            user_id=row['user_id'],
            category=row['category'],
            content=row['content'],
            session_id=row['session_id'],
            pattern_key=row['pattern_key'],
            priority=row['priority'],
            status=row['status'],
            recurrence_count=row['recurrence_count'],
            first_seen=row['first_seen'],
            last_seen=row['last_seen'],
            promoted_to=row['promoted_to'],
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
    
    def _item_to_dict(self, item: LearningRecord) -> Dict[str, Any]:
        """对象转字典 - 用于基类 add() 方法"""
        return {
            'learning_id': item.learning_id,
            'user_id': item.user_id,
            'session_id': item.session_id,
            'category': item.category,
            'pattern_key': item.pattern_key,
            'content': item.content,
            'priority': item.priority,
            'status': item.status,
            'recurrence_count': item.recurrence_count,
            'first_seen': item.first_seen,
            'last_seen': item.last_seen,
            'promoted_to': item.promoted_to,
            'metadata': json.dumps(item.metadata)
        }
    
    def _get_id(self, item: LearningRecord) -> str:
        return item.learning_id
    
    def _get_id_column(self) -> str:
        """获取 ID 列名"""
        return "learning_id"
    
    def _get_allowed_columns(self) -> List[str]:
        return [
            'learning_id', 'user_id', 'session_id', 'session_ids',
            'category', 'pattern_key', 'content', 'priority', 'status',
            'recurrence_count', 'first_seen', 'last_seen', 'promoted_to',
            'metadata', 'created_at'
        ]
    
    # === 公共方法 ===
    
    def generate_pattern_key(self, category: str, content: str) -> str:
        """生成模式键（用于去重）"""
        normalized = content.strip().lower()
        content_hash = hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:8]
        return f"{category}.{content_hash}"
    
    def generate_learning_id(self) -> str:
        """生成学习ID（uuid4，122 bit 熵，实际零碰撞）"""
        import uuid
        return f"LRN-{uuid.uuid4().hex[:16]}"
    
    # Note: Uses custom INSERT logic for special deduplication behavior.
    # Does not use inherited SQLiteStore.add() method.
    def record_learning(
        self,
        category: str,
        content: str,
        session_id: Optional[str] = None,
        priority: str = "medium",
        metadata: Optional[Dict[str, Any]] = None
    ) -> LearningRecord:
        """记录学习（使用事务确保一致性）"""
        pattern_key = self.generate_pattern_key(category, content)
        now = datetime.now().isoformat()
        
        try:
            # 开始事务
            self.db.execute("BEGIN IMMEDIATE")
            
            # 检查是否已存在
            cursor = self.db.execute(
                "SELECT * FROM learnings WHERE pattern_key = ? AND user_id = ?",
                (pattern_key, self.user_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                new_count = existing["recurrence_count"] + 1
                
                existing_session_ids = json.loads(existing["session_ids"] or "[]")
                if session_id and session_id not in existing_session_ids:
                    existing_session_ids.append(session_id)
                session_ids_json = json.dumps(existing_session_ids)
                
                self.db.execute(
                    """
                    UPDATE learnings 
                    SET recurrence_count = ?, last_seen = ?, session_id = ?, session_ids = ?
                    WHERE learning_id = ?
                    """,
                    (new_count, now, session_id, session_ids_json, existing["learning_id"])
                )
                
                record = LearningRecord(
                    learning_id=existing["learning_id"],
                    user_id=existing["user_id"],
                    session_id=session_id or existing["session_id"],
                    category=existing["category"],
                    pattern_key=existing["pattern_key"],
                    content=existing["content"],
                    priority=existing["priority"],
                    status=existing["status"],
                    recurrence_count=new_count,
                    first_seen=existing["first_seen"],
                    last_seen=now,
                    promoted_to=existing["promoted_to"],
                    metadata=json.loads(existing["metadata"] or "{}")
                )
                
                logger.info(f"Updated learning {record.learning_id}, recurrence: {new_count}")
            else:
                # 创建新记录
                learning_id = self.generate_learning_id()
                metadata_json = json.dumps(metadata or {})
                session_ids_json = json.dumps([session_id] if session_id else [])
                
                self.db.execute(
                    """
                    INSERT INTO learnings (
                        learning_id, user_id, session_id, session_ids, category, pattern_key,
                        content, priority, status, recurrence_count,
                        first_seen, last_seen, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        learning_id, self.user_id, session_id, session_ids_json, category, pattern_key,
                        content, priority, "pending", 1,
                        now, now, metadata_json
                    )
                )
                
                record = LearningRecord(
                    learning_id=learning_id,
                    user_id=self.user_id,
                    session_id=session_id,
                    category=category,
                    pattern_key=pattern_key,
                    content=content,
                    priority=priority,
                    status="pending",
                    recurrence_count=1,
                    first_seen=now,
                    last_seen=now,
                    metadata=metadata or {}
                )
                
                logger.info(f"Created learning {learning_id}: {category}")
            
            # 提交事务
            self.db.commit()
            return record
            
        except Exception as e:
            # 回滚事务
            self.db.rollback()
            logger.error(f"Failed to record learning: {e}")
            raise
    
    def get_learning(self, learning_id: str) -> Optional[LearningRecord]:
        """获取学习记录"""
        cursor = self.db.execute(
            "SELECT * FROM learnings WHERE learning_id = ?",
            (learning_id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
    
    def query_learnings(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        min_recurrence: int = 1,
        limit: int = 100
    ) -> List[LearningRecord]:
        """查询学习记录"""
        query = "SELECT * FROM learnings WHERE user_id = ? AND recurrence_count >= ?"
        params = [self.user_id, min_recurrence]
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.db.execute(query, params)
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def update_status(
        self,
        learning_id: str,
        status: str,
        promoted_to: Optional[str] = None
    ) -> bool:
        """更新学习状态"""
        try:
            self.db.execute(
                """
                UPDATE learnings 
                SET status = ?, promoted_to = ?
                WHERE learning_id = ?
                """,
                (status, promoted_to, learning_id)
            )
            self.db.commit()
            logger.info(f"Updated learning {learning_id} status to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update learning status: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        cursor = self.db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'promoted' THEN 1 ELSE 0 END) as promoted,
                SUM(CASE WHEN status = 'ignored' THEN 1 ELSE 0 END) as ignored,
                SUM(CASE WHEN recurrence_count >= 3 THEN 1 ELSE 0 END) as high_recurrence
            FROM learnings WHERE user_id = ?
            """,
            (self.user_id,)
        )
        row = cursor.fetchone()
        
        cursor = self.db.execute(
            """
            SELECT category, COUNT(*) as count
            FROM learnings 
            WHERE user_id = ?
            GROUP BY category
            """,
            (self.user_id,)
        )
        by_category = {row["category"]: row["count"] for row in cursor.fetchall()}
        
        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "promoted": row["promoted"] or 0,
            "ignored": row["ignored"] or 0,
            "high_recurrence": row["high_recurrence"] or 0,
            "by_category": by_category
        }
    
    def get_promotion_candidates(self) -> List[LearningRecord]:
        """获取晋升候选（recurrence_count >= 3, status = 'pending'）"""
        return self.query_learnings(
            status="pending",
            min_recurrence=3,
            limit=50
        )
    
    def clear_old_learnings(self, days: int = 90) -> int:
        """清理旧学习记录"""
        cursor = self.db.execute(
            """
            DELETE FROM learnings 
            WHERE user_id = ? 
            AND status = 'ignored' 
            AND date(last_seen) < date('now', ?)
            """,
            (self.user_id, f"-{days} days")
        )
        self.db.commit()
        deleted = cursor.rowcount
        logger.info(f"Cleared {deleted} old ignored learnings")
        return deleted
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self._owns_connection and self._db:
            self._db.close()
            self._db = None
