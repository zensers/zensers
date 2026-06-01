# -*- coding: utf-8 -*-
"""
ErrorTracker - 错误追踪

Phase 3.7 核心功能: 追踪和管理错误记录

功能:
- 记录错误
- 错误分类
- 错误统计
- 错误关联学习记录
"""

__all__ = [
    "ErrorTracker",
    "ErrorRecord",
    "ErrorSeverity"
]

import sqlite3
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorRecord:
    """
    错误记录
    
    Attributes:
        error_id: 错误ID
        user_id: 用户ID
        session_id: 会话ID
        error_type: 错误类型
        error_message: 错误信息
        severity: 严重程度
        context: 错误上下文
        stack_trace: 堆栈跟踪
        resolved: 是否已解决
        resolution: 解决方案
        learning_id: 关联的学习记录ID
        created_at: 创建时间
    """
    error_id: str
    user_id: str
    error_type: str
    error_message: str
    session_id: Optional[str] = None
    severity: str = "medium"
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution: Optional[str] = None
    learning_id: Optional[str] = None
    created_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ErrorTracker:
    """
    错误追踪器
    
    管理错误的记录、分类和统计。
    支持与 LearningStore 关联。
    """
    
    def __init__(self, db_path: str, user_id: str):
        """
        初始化错误追踪器
        
        Args:
            db_path: 数据库路径
            user_id: 用户ID
        """
        self.db_path = db_path
        self.user_id = user_id
        self.db: Optional[sqlite3.Connection] = None
        
        self._init_db()
        logger.info(f"ErrorTracker initialized for user {user_id}")
    
    def _init_db(self):
        """初始化数据库表"""
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                error_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                context TEXT,
                stack_trace TEXT,
                resolved INTEGER DEFAULT 0,
                resolution TEXT,
                learning_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 创建索引
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_user 
            ON errors(user_id)
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_type 
            ON errors(error_type)
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_resolved 
            ON errors(resolved)
        """)
        
        self.db.commit()
    
    def generate_error_id(self) -> str:
        """生成错误ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        import random
        random_suffix = random.randint(1000, 9999)
        return f"ERR-{timestamp}-{random_suffix}"
    
    def record_error(
        self,
        error_type: str,
        error_message: str,
        session_id: Optional[str] = None,
        severity: str = "medium",
        context: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None
    ) -> ErrorRecord:
        """
        记录错误
        
        Args:
            error_type: 错误类型
            error_message: 错误信息
            session_id: 会话ID
            severity: 严重程度
            context: 错误上下文
            stack_trace: 堆栈跟踪
            
        Returns:
            错误记录
        """
        error_id = self.generate_error_id()
        now = datetime.now().isoformat()
        context_json = json.dumps(context or {})
        
        self.db.execute(
            """
            INSERT INTO errors (
                error_id, user_id, session_id, error_type, error_message,
                severity, context, stack_trace, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                error_id, self.user_id, session_id, error_type, error_message,
                severity, context_json, stack_trace, now
            )
        )
        self.db.commit()
        
        record = ErrorRecord(
            error_id=error_id,
            user_id=self.user_id,
            session_id=session_id,
            error_type=error_type,
            error_message=error_message,
            severity=severity,
            context=context or {},
            stack_trace=stack_trace,
            created_at=now
        )
        
        logger.warning(f"Recorded error {error_id}: {error_type} - {error_message}")
        return record
    
    def get_error(self, error_id: str) -> Optional[ErrorRecord]:
        """获取错误记录"""
        cursor = self.db.execute(
            "SELECT * FROM errors WHERE error_id = ?",
            (error_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return ErrorRecord(
                error_id=row["error_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                error_type=row["error_type"],
                error_message=row["error_message"],
                severity=row["severity"],
                context=json.loads(row["context"] or "{}"),
                stack_trace=row["stack_trace"],
                resolved=bool(row["resolved"]),
                resolution=row["resolution"],
                learning_id=row["learning_id"],
                created_at=row["created_at"]
            )
        return None
    
    def resolve_error(
        self,
        error_id: str,
        resolution: str,
        learning_id: Optional[str] = None
    ) -> bool:
        """
        解决错误
        
        Args:
            error_id: 错误ID
            resolution: 解决方案
            learning_id: 关联的学习记录ID
            
        Returns:
            是否成功
        """
        try:
            self.db.execute(
                """
                UPDATE errors 
                SET resolved = 1, resolution = ?, learning_id = ?
                WHERE error_id = ?
                """,
                (resolution, learning_id, error_id)
            )
            self.db.commit()
            logger.info(f"Resolved error {error_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resolve error: {e}")
            return False
    
    def query_errors(
        self,
        error_type: Optional[str] = None,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[ErrorRecord]:
        """
        查询错误记录
        
        Args:
            error_type: 错误类型过滤
            resolved: 是否已解决过滤
            severity: 严重程度过滤
            limit: 返回数量限制
            
        Returns:
            错误记录列表
        """
        query = "SELECT * FROM errors WHERE user_id = ?"
        params = [self.user_id]
        
        if error_type:
            query += " AND error_type = ?"
            params.append(error_type)
        
        if resolved is not None:
            query += " AND resolved = ?"
            params.append(1 if resolved else 0)
        
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append(ErrorRecord(
                error_id=row["error_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                error_type=row["error_type"],
                error_message=row["error_message"],
                severity=row["severity"],
                context=json.loads(row["context"] or "{}"),
                stack_trace=row["stack_trace"],
                resolved=bool(row["resolved"]),
                resolution=row["resolution"],
                learning_id=row["learning_id"],
                created_at=row["created_at"]
            ))
        
        return records
    
    def get_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        cursor = self.db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN resolved = 0 THEN 1 ELSE 0 END) as unresolved,
                SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high
            FROM errors WHERE user_id = ?
            """,
            (self.user_id,)
        )
        row = cursor.fetchone()
        
        # 按类型统计
        cursor = self.db.execute(
            """
            SELECT error_type, COUNT(*) as count
            FROM errors 
            WHERE user_id = ?
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
            """,
            (self.user_id,)
        )
        by_type = {row["error_type"]: row["count"] for row in cursor.fetchall()}
        
        return {
            "total": row["total"] or 0,
            "unresolved": row["unresolved"] or 0,
            "critical": row["critical"] or 0,
            "high": row["high"] or 0,
            "by_type": by_type
        }
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()
            self.db = None
            logger.info("ErrorTracker closed")