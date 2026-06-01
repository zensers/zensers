# -*- coding: utf-8 -*-
"""
RawResearchDataStore - 研究资料暂存区

主任务完成后，将研究资料存入暂存区，
知识提取 Agent 在"做梦模式"中从暂存区读取进行处理。

设计理念：
- 不阻塞主任务：主任务完成后立即返回，资料暂存等待处理
- 主任务优先：用户发起新需求时，暂停知识提取
- 批量处理：积累一定数量后批量提取，提高效率
"""

__all__ = ["RawResearchDataStore", "RawResearchData"]

import sqlite3
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ExtractionStatus(Enum):
    """提取状态"""
    PENDING = "pending"      # 待提取
    IN_PROGRESS = "in_progress"  # 正在提取
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 因主任务而取消


@dataclass
class RawResearchData:
    """研究资料数据结构"""
    data_id: str
    research_id: str
    topic: str
    content: str
    source_info: Dict[str, Any] = field(default_factory=dict)
    domain: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = ExtractionStatus.PENDING.value
    extraction_attempts: int = 0
    last_attempt_at: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RawResearchDataStore:
    """
    研究资料暂存区
    
    职责：
    1. 存储主任务完成后的研究资料
    2. 提供待提取资料的队列
    3. 管理提取状态和进度
    4. 支持提取任务的中断和恢复
    
    设计原则：
    - 主任务优先：如果用户发起新需求，标记当前提取任务为"取消"
    - 异步处理：不阻塞主任务返回
    - 可恢复：提取失败的任务可以重试
    """
    
    # 配置
    MAX_PENDING_ITEMS = 100  # 最大待处理数量
    MAX_RETRY_ATTEMPTS = 3   # 最大重试次数
    BATCH_SIZE = 10          # 批量处理大小
    
    def __init__(
        self,
        user_id: str,
        storage_path: Optional[str] = None
    ):
        """
        初始化研究资料暂存区
        
        Args:
            user_id: 用户ID
            storage_path: 存储路径，默认为 data/users/{user_id}/raw_data.db
        """
        self.user_id = user_id
        
        # 设置数据库路径
        if storage_path is None:
            storage_path = f"data/users/{user_id}/raw_data.db"
        
        self.db_path = Path(storage_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self.db = sqlite3.connect(str(self.db_path))
        self._init_tables()
        
        logger.info(f"RawResearchDataStore initialized for user {user_id}")
    
    def _init_tables(self):
        """初始化数据库表"""
        # 研究资料表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS raw_research_data (
                data_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                topic TEXT,
                content TEXT NOT NULL,
                source_info TEXT,
                domain TEXT,
                created_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                extraction_attempts INTEGER DEFAULT 0,
                last_attempt_at TIMESTAMP,
                error_message TEXT
            )
        """)
        
        # 创建索引
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_raw_status ON raw_research_data(status)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_raw_created ON raw_research_data(created_at)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_raw_research ON raw_research_data(research_id)")
        
        self.db.commit()
    
    # ========== 存入资料 ==========
    
    def store_research_data(
        self,
        research_id: str,
        content: str,
        topic: Optional[str] = None,
        source_info: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None
    ) -> str:
        """
        存储研究资料
        
        主任务完成后调用此方法，将研究资料存入暂存区。
        知识提取将在后续的"做梦模式"中异步执行。
        
        Args:
            research_id: 研究ID
            content: 研究内容（文本）
            topic: 研究主题
            source_info: 来源信息
            domain: 研究领域
        
        Returns:
            数据ID
        """
        data_id = f"raw_{uuid.uuid4().hex[:8]}"
        
        self.db.execute("""
            INSERT INTO raw_research_data 
            (data_id, research_id, topic, content, source_info, domain, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            data_id,
            research_id,
            topic,
            content,
            json.dumps(source_info or {}),
            domain,
            datetime.now().isoformat()
        ))
        
        self.db.commit()
        
        logger.debug(f"Stored research data: {data_id} for research {research_id}")
        
        # 检查是否需要触发提取
        pending_count = self.get_pending_count()
        if pending_count >= self.BATCH_SIZE:
            logger.info(f"Pending data reached batch size ({self.BATCH_SIZE}), ready for extraction")
        
        return data_id
    
    def store_research_batch(
        self,
        research_id: str,
        content_list: List[Dict[str, Any]]
    ) -> List[str]:
        """
        批量存储研究资料
        
        Args:
            research_id: 研究ID
            content_list: 内容列表，每项包含 content, topic, source_info
        
        Returns:
            数据ID列表
        """
        data_ids = []
        
        for item in content_list:
            data_id = self.store_research_data(
                research_id=research_id,
                content=item.get("content", ""),
                topic=item.get("topic"),
                source_info=item.get("source_info"),
                domain=item.get("domain")
            )
            data_ids.append(data_id)
        
        return data_ids
    
    # ========== 获取待提取资料 ==========
    
    def get_pending_data(self, limit: Optional[int] = None) -> List[RawResearchData]:
        """
        获取待提取的研究资料
        
        Args:
            limit: 最大数量，默认为 BATCH_SIZE
        
        Returns:
            待提取资料列表
        """
        if limit is None:
            limit = self.BATCH_SIZE
        
        cursor = self.db.execute("""
            SELECT data_id, research_id, topic, content, source_info, domain,
                   created_at, status, extraction_attempts, last_attempt_at, error_message
            FROM raw_research_data
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            data = RawResearchData(
                data_id=row[0],
                research_id=row[1],
                topic=row[2] or "",
                content=row[3],
                source_info=json.loads(row[4] or "{}"),
                domain=row[5],
                created_at=row[6],
                status=row[7],
                extraction_attempts=row[8],
                last_attempt_at=row[9],
                error_message=row[10]
            )
            results.append(data)
        
        return results
    
    def get_retry_data(self, limit: int = 5) -> List[RawResearchData]:
        """
        获取可重试的失败资料
        
        Args:
            limit: 最大数量
        
        Returns:
            可重试资料列表
        """
        cursor = self.db.execute("""
            SELECT data_id, research_id, topic, content, source_info, domain,
                   created_at, status, extraction_attempts, last_attempt_at, error_message
            FROM raw_research_data
            WHERE status = 'failed' AND extraction_attempts < ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (self.MAX_RETRY_ATTEMPTS, limit))
        
        results = []
        for row in cursor.fetchall():
            data = RawResearchData(
                data_id=row[0],
                research_id=row[1],
                topic=row[2] or "",
                content=row[3],
                source_info=json.loads(row[4] or "{}"),
                domain=row[5],
                created_at=row[6],
                status=row[7],
                extraction_attempts=row[8],
                last_attempt_at=row[9],
                error_message=row[10]
            )
            results.append(data)
        
        return results
    
    # ========== 状态管理 ==========
    
    def mark_in_progress(self, data_id: str) -> bool:
        """
        标记为正在提取
        
        Args:
            data_id: 数据ID
        
        Returns:
            是否成功
        """
        self.db.execute("""
            UPDATE raw_research_data
            SET status = 'in_progress', last_attempt_at = ?
            WHERE data_id = ? AND status = 'pending'
        """, (datetime.now().isoformat(), data_id))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def mark_completed(self, data_id: str) -> bool:
        """
        标记为已完成
        
        Args:
            data_id: 数据ID
        
        Returns:
            是否成功
        """
        self.db.execute("""
            UPDATE raw_research_data
            SET status = 'completed'
            WHERE data_id = ?
        """, (data_id,))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def mark_failed(
        self, 
        data_id: str, 
        error_message: str,
        increment_attempt: bool = True
    ) -> bool:
        """
        标记为失败
        
        Args:
            data_id: 数据ID
            error_message: 错误信息
            increment_attempt: 是否增加尝试次数
        
        Returns:
            是否成功
        """
        if increment_attempt:
            self.db.execute("""
                UPDATE raw_research_data
                SET status = 'failed', 
                    error_message = ?,
                    extraction_attempts = extraction_attempts + 1,
                    last_attempt_at = ?
                WHERE data_id = ?
            """, (error_message, datetime.now().isoformat(), data_id))
        else:
            self.db.execute("""
                UPDATE raw_research_data
                SET status = 'failed', error_message = ?
                WHERE data_id = ?
            """, (error_message, data_id))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def mark_cancelled(self, data_id: str) -> bool:
        """
        标记为取消（因主任务中断）
        
        Args:
            data_id: 数据ID
        
        Returns:
            是否成功
        """
        self.db.execute("""
            UPDATE raw_research_data
            SET status = 'cancelled', error_message = 'Cancelled due to new main task'
            WHERE data_id = ? AND status = 'in_progress'
        """, (data_id,))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def cancel_all_in_progress(self) -> int:
        """
        取消所有正在提取的任务
        
        当用户发起新主任务时调用此方法。
        
        Returns:
            取消的数量
        """
        self.db.execute("""
            UPDATE raw_research_data
            SET status = 'cancelled', error_message = 'Cancelled due to new main task'
            WHERE status = 'in_progress'
        """)
        
        self.db.commit()
        cancelled_count = self.db.total_changes
        
        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} extraction tasks due to new main task")
        
        return cancelled_count
    
    # ========== 统计与清理 ==========
    
    def get_pending_count(self) -> int:
        """获取待处理数量"""
        cursor = self.db.execute("""
            SELECT COUNT(*) FROM raw_research_data WHERE status = 'pending'
        """)
        return cursor.fetchone()[0]
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        stats = {}
        
        for status in ['pending', 'in_progress', 'completed', 'failed', 'cancelled']:
            cursor = self.db.execute(
                "SELECT COUNT(*) FROM raw_research_data WHERE status = ?",
                (status,)
            )
            stats[status] = cursor.fetchone()[0]
        
        stats['total'] = sum(stats.values())
        return stats
    
    def cleanup_completed(self, days_old: int = 7) -> int:
        """
        清理已完成的旧数据
        
        Args:
            days_old: 保留天数
        
        Returns:
            清理数量
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        self.db.execute("""
            DELETE FROM raw_research_data
            WHERE status IN ('completed', 'cancelled')
            AND created_at < ?
        """, (cutoff_date.isoformat()))
        
        self.db.commit()
        return self.db.total_changes
    
    def clear_all(self):
        """清空所有数据"""
        self.db.execute("DELETE FROM raw_research_data")
        self.db.commit()
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()


# 需要导入 timedelta
from datetime import timedelta