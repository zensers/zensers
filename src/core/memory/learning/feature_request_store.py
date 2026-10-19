# -*- coding: utf-8 -*-
"""
FeatureRequestStore - 功能请求管理

Phase 3.7 核心功能: 管理用户功能请求

功能:
- 记录功能请求
- 请求优先级管理
- 请求状态跟踪
- 请求统计
"""

__all__ = [
    "FeatureRequestStore",
    "FeatureRequest",
    "RequestStatus",
    "RequestComplexity"
]

import sqlite3
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class RequestStatus(Enum):
    """请求状态"""
    PENDING = "pending"          # 待评估
    APPROVED = "approved"        # 已批准
    IN_PROGRESS = "in_progress"  # 开发中
    COMPLETED = "completed"      # 已完成
    REJECTED = "rejected"        # 已拒绝


class RequestComplexity(Enum):
    """请求复杂度"""
    LOW = "low"            # 低复杂度（< 1天）
    MEDIUM = "medium"      # 中等复杂度（1-3天）
    HIGH = "high"          # 高复杂度（3-7天）
    VERY_HIGH = "very_high"  # 极高复杂度（> 7天）


@dataclass
class FeatureRequest:
    """
    功能请求
    
    Attributes:
        request_id: 请求ID
        user_id: 用户ID
        session_id: 会话ID
        capability: 能力描述
        user_context: 用户上下文
        complexity: 复杂度
        status: 状态
        frequency: 频率 (first_time/recurring)
        priority: 优先级
        assigned_to: 分配给
        estimated_effort: 预估工作量
        notes: 备注
        created_at: 创建时间
        updated_at: 更新时间
    """
    request_id: str
    user_id: str
    capability: str
    session_id: Optional[str] = None
    user_context: Optional[str] = None
    complexity: str = "medium"
    status: str = "pending"
    frequency: str = "first_time"
    priority: str = "medium"
    assigned_to: Optional[str] = None
    estimated_effort: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class FeatureRequestStore:
    """
    功能请求存储
    
    管理功能请求的存储、查询和统计。
    """
    
    def __init__(self, db_path: str, user_id: str):
        """
        初始化功能请求存储
        
        Args:
            db_path: 数据库路径
            user_id: 用户ID
        """
        self.db_path = db_path
        self.user_id = user_id
        self.db: Optional[sqlite3.Connection] = None
        
        self._init_db()
        logger.info(f"FeatureRequestStore initialized for user {user_id}")
    
    def _init_db(self):
        """初始化数据库表"""
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS feature_requests (
                request_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                capability TEXT NOT NULL,
                user_context TEXT,
                complexity TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'pending',
                frequency TEXT DEFAULT 'first_time',
                priority TEXT DEFAULT 'medium',
                assigned_to TEXT,
                estimated_effort TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # 创建索引
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_feature_requests_user 
            ON feature_requests(user_id)
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_feature_requests_status 
            ON feature_requests(status)
        """)
        
        self.db.commit()
    
    def generate_request_id(self) -> str:
        """生成请求ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        import random
        random_suffix = random.randint(1000, 9999)
        return f"REQ-{timestamp}-{random_suffix}"
    
    def record_request(
        self,
        capability: str,
        session_id: Optional[str] = None,
        user_context: Optional[str] = None,
        complexity: str = "medium",
        priority: str = "medium"
    ) -> FeatureRequest:
        """
        记录功能请求
        
        如果相同 capability 已存在，更新 frequency 为 recurring。
        
        Args:
            capability: 能力描述
            session_id: 会话ID
            user_context: 用户上下文
            complexity: 复杂度
            priority: 优先级
            
        Returns:
            功能请求
        """
        # 检查是否已存在相同的请求
        cursor = self.db.execute(
            """
            SELECT * FROM feature_requests 
            WHERE user_id = ? AND capability = ?
            """,
            (self.user_id, capability)
        )
        existing = cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        if existing:
            # 更新为 recurring
            self.db.execute(
                """
                UPDATE feature_requests 
                SET frequency = 'recurring', updated_at = ?
                WHERE request_id = ?
                """,
                (now, existing["request_id"])
            )
            self.db.commit()
            
            request = FeatureRequest(
                request_id=existing["request_id"],
                user_id=existing["user_id"],
                session_id=existing["session_id"],
                capability=existing["capability"],
                user_context=existing["user_context"],
                complexity=existing["complexity"],
                status=existing["status"],
                frequency="recurring",
                priority=existing["priority"],
                assigned_to=existing["assigned_to"],
                estimated_effort=existing["estimated_effort"],
                notes=existing["notes"],
                created_at=existing["created_at"],
                updated_at=now
            )
            
            logger.info(f"Updated feature request {request.request_id} as recurring")
            return request
        else:
            # 创建新请求
            request_id = self.generate_request_id()
            
            self.db.execute(
                """
                INSERT INTO feature_requests (
                    request_id, user_id, session_id, capability, user_context,
                    complexity, status, frequency, priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id, self.user_id, session_id, capability, user_context,
                    complexity, "pending", "first_time", priority, now, now
                )
            )
            self.db.commit()
            
            request = FeatureRequest(
                request_id=request_id,
                user_id=self.user_id,
                session_id=session_id,
                capability=capability,
                user_context=user_context,
                complexity=complexity,
                status="pending",
                frequency="first_time",
                priority=priority,
                created_at=now,
                updated_at=now
            )
            
            logger.info(f"Created feature request {request_id}: {capability}")
            return request
    
    def get_request(self, request_id: str) -> Optional[FeatureRequest]:
        """获取功能请求"""
        cursor = self.db.execute(
            "SELECT * FROM feature_requests WHERE request_id = ?",
            (request_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return FeatureRequest(
                request_id=row["request_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                capability=row["capability"],
                user_context=row["user_context"],
                complexity=row["complexity"],
                status=row["status"],
                frequency=row["frequency"],
                priority=row["priority"],
                assigned_to=row["assigned_to"],
                estimated_effort=row["estimated_effort"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
        return None
    
    def update_status(
        self,
        request_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        更新请求状态
        
        Args:
            request_id: 请求ID
            status: 新状态
            notes: 备注
            
        Returns:
            是否成功
        """
        try:
            now = datetime.now().isoformat()
            self.db.execute(
                """
                UPDATE feature_requests 
                SET status = ?, notes = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status, notes, now, request_id)
            )
            self.db.commit()
            logger.info(f"Updated feature request {request_id} status to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update feature request status: {e}")
            return False
    
    def query_requests(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100
    ) -> List[FeatureRequest]:
        """
        查询功能请求
        
        Args:
            status: 状态过滤
            priority: 优先级过滤
            limit: 返回数量限制
            
        Returns:
            功能请求列表
        """
        query = "SELECT * FROM feature_requests WHERE user_id = ?"
        params = [self.user_id]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append(FeatureRequest(
                request_id=row["request_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                capability=row["capability"],
                user_context=row["user_context"],
                complexity=row["complexity"],
                status=row["status"],
                frequency=row["frequency"],
                priority=row["priority"],
                assigned_to=row["assigned_to"],
                estimated_effort=row["estimated_effort"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            ))
        
        return records
    
    def get_stats(self) -> Dict[str, Any]:
        """获取请求统计"""
        cursor = self.db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN frequency = 'recurring' THEN 1 ELSE 0 END) as recurring
            FROM feature_requests WHERE user_id = ?
            """,
            (self.user_id,)
        )
        row = cursor.fetchone()
        
        # 按优先级统计
        cursor = self.db.execute(
            """
            SELECT priority, COUNT(*) as count
            FROM feature_requests 
            WHERE user_id = ?
            GROUP BY priority
            """,
            (self.user_id,)
        )
        by_priority = {row["priority"]: row["count"] for row in cursor.fetchall()}
        
        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "approved": row["approved"] or 0,
            "in_progress": row["in_progress"] or 0,
            "completed": row["completed"] or 0,
            "recurring": row["recurring"] or 0,
            "by_priority": by_priority
        }
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()
            self.db = None
            logger.info("FeatureRequestStore closed")