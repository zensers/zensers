# -*- coding: utf-8 -*-
"""
TemporalKnowledge - 时间有效性追踪

实现知识的时间维度管理：
- 事实带时间戳：每个值都有 as_of 时间
- 时间范围：valid_from, valid_until
- 自动过期检测
- 版本历史追踪

设计参考：
- Graphiti/Zep: 时间窗口和事实有效性追踪
- Zelph: 知识版本管理

使用方式：
```python
# 存储带时间的事实
temporal.store_fact(
    entity_name="宁德时代",
    attribute="市场份额",
    value="37%",
    as_of="2024-Q3",
    source="财报"
)

# 查询特定时间点的值
value = temporal.get_value("宁德时代", "市场份额", as_of="2024-Q3")

# 查询历史版本
history = temporal.get_history("宁德时代", "市场份额")
```
"""

__all__ = [
    "TemporalKnowledge",
    "TemporalFact",
    "FactVersion",
    "TemporalQuery",
    "FactStatus"
]

import sqlite3
import json
import uuid
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

# 从 utils 模块导入时间解析函数（分层架构）
from src.utils.time_utils import parse_time

logger = logging.getLogger(__name__)


class FactStatus(Enum):
    """事实状态"""
    ACTIVE = "active"           # 当前有效
    EXPIRED = "expired"         # 已过期
    SUPERSEDED = "superseded"   # 被新值取代
    DISPUTED = "disputed"       # 有争议
    RETRACTED = "retracted"     # 已撤回


@dataclass
class TemporalFact:
    """带时间戳的事实"""
    fact_id: str
    entity_name: str
    attribute: str
    value: str
    as_of: str                          # 事实时间点（如 "2024-Q3"）
    valid_from: Optional[str] = None    # 有效期开始
    valid_until: Optional[str] = None   # 有效期结束
    status: str = FactStatus.ACTIVE.value
    confidence: float = 0.8
    source: str = ""
    source_id: str = ""                 # 来源ID（链接到 provenance）
    superseded_by: Optional[str] = None # 被哪个事实取代
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def is_valid_at(self, query_time: str) -> bool:
        """检查在指定时间点是否有效"""
        if self.status != FactStatus.ACTIVE.value:
            return False
        
        # 使用统一的时间解析
        query_dt = parse_time(query_time)
        if query_dt is None:
            return False
        
        if self.valid_from:
            valid_from_dt = parse_time(self.valid_from)
            if valid_from_dt and query_dt < valid_from_dt:
                return False
        if self.valid_until:
            valid_until_dt = parse_time(self.valid_until)
            if valid_until_dt and query_dt > valid_until_dt:
                return False
        return True


@dataclass
class FactVersion:
    """事实版本记录"""
    version_id: str
    fact_id: str
    old_value: Optional[str]
    new_value: str
    change_reason: str
    changed_at: str
    changed_by: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalQuery:
    """时间查询条件"""
    entity_name: str
    attribute: str
    as_of: Optional[str] = None     # 查询特定时间点
    as_of_range: Optional[Tuple[str, str]] = None  # 时间范围
    include_expired: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "entity_name": self.entity_name,
            "attribute": self.attribute,
            "include_expired": self.include_expired
        }
        if self.as_of:
            result["as_of"] = self.as_of
        if self.as_of_range:
            result["as_of_range"] = self.as_of_range
        return result


class TemporalKnowledge:
    """
    时间知识管理器
    
    核心功能：
    1. 存储带时间戳的事实
    2. 查询特定时间点的值
    3. 追踪版本历史
    4. 自动过期检测
    
    设计参考：
    - Graphiti: 时间窗口
    - Zelph: 版本追踪
    """
    
    def __init__(
        self,
        db_path: str,
        user_id: str = "default"
    ):
        """
        初始化时间知识管理器
        
        Args:
            db_path: 数据库路径
            user_id: 用户ID
        """
        self.db_path = Path(db_path)
        self.user_id = user_id
        
        # 初始化数据库
        self.db = sqlite3.connect(str(self.db_path))
        self._init_tables()
        
        logger.info(f"TemporalKnowledge initialized for user {user_id}")
    
    def _init_tables(self):
        """初始化数据库表"""
        # 时间事实表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS temporal_facts (
                fact_id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                as_of TEXT NOT NULL,
                valid_from TEXT,
                valid_until TEXT,
                status TEXT DEFAULT 'active',
                confidence REAL DEFAULT 0.8,
                source TEXT,
                source_id TEXT,
                superseded_by TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)
        
        # 版本历史表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS fact_versions (
                version_id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                change_reason TEXT,
                changed_at TIMESTAMP NOT NULL,
                changed_by TEXT DEFAULT 'system',
                FOREIGN KEY (fact_id) REFERENCES temporal_facts(fact_id)
            )
        """)
        
        # 创建索引
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_entity ON temporal_facts(entity_name)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_attribute ON temporal_facts(attribute)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_as_of ON temporal_facts(as_of)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_valid ON temporal_facts(valid_from, valid_until)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_status ON temporal_facts(status)")
        
        # 复合索引 - 优化常用查询
        # get_value 查询: WHERE entity_name = ? AND attribute = ? AND as_of <= ?
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_entity_attr_asof ON temporal_facts(entity_name, attribute, as_of)")
        # get_history 查询: WHERE entity_name = ? AND attribute = ?
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_temporal_entity_attr_status ON temporal_facts(entity_name, attribute, status)")
        
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_versions_fact ON fact_versions(fact_id)")
        
        self.db.commit()
    
    # ========== 存储事实 ==========
    
    def store_fact(
        self,
        entity_name: str,
        attribute: str,
        value: str,
        as_of: str,
        source: str = "",
        source_id: str = "",
        confidence: float = 0.8,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        auto_supersede: bool = True
    ) -> str:
        """
        存储带时间戳的事实
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            value: 值
            as_of: 事实时间点
            source: 来源描述
            source_id: 来源ID
            confidence: 置信度 (0-1)
            valid_from: 有效期开始
            valid_until: 有效期结束
            auto_supersede: 是否自动取代旧值
        
        Returns:
            事实ID
        
        Raises:
            ValueError: 参数验证失败
            sqlite3.Error: 数据库操作失败
        """
        # 参数验证
        if not entity_name or not entity_name.strip():
            raise ValueError("entity_name cannot be empty")
        if not attribute or not attribute.strip():
            raise ValueError("attribute cannot be empty")
        if not value:
            raise ValueError("value cannot be empty")
        if not as_of:
            raise ValueError("as_of cannot be empty")
        if not 0 <= confidence <= 1:
            raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
        
        # 验证时间格式
        if parse_time(as_of) is None:
            raise ValueError(f"Invalid as_of format: {as_of}")
        
        fact_id = f"fact_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        try:
            # 检查是否有需要取代的旧事实
            if auto_supersede:
                old_facts = self._find_active_facts(entity_name, attribute)
                for old_fact in old_facts:
                    # 只取代时间较早的事实
                    if old_fact["as_of"] < as_of:
                        # 标记旧事实为已取代
                        self._supersede_fact(old_fact["fact_id"], fact_id)
                        # 记录版本变更
                        self._record_version(
                            fact_id=old_fact["fact_id"],
                            old_value=old_fact["value"],
                            new_value=value,
                            reason="superseded_by_newer_data"
                        )
            
            # 插入新事实
            self.db.execute("""
                INSERT INTO temporal_facts 
                (fact_id, entity_name, attribute, value, as_of, valid_from, valid_until,
                 status, confidence, source, source_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """, (
                fact_id, entity_name, attribute, value, as_of,
                valid_from, valid_until,
                confidence, source, source_id, now
            ))
            
            self.db.commit()
            
            logger.debug(f"Stored temporal fact: {entity_name}.{attribute} = {value} (as_of={as_of})")
            return fact_id
            
        except sqlite3.IntegrityError as e:
            logger.error(f"Database integrity error: {e}")
            self.db.rollback()
            raise
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error: {e}")
            self.db.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing fact: {e}")
            self.db.rollback()
            raise
    
    def _find_active_facts(
        self,
        entity_name: str,
        attribute: str
    ) -> List[Dict[str, Any]]:
        """查找活跃的事实"""
        cursor = self.db.execute("""
            SELECT fact_id, value, as_of, confidence, source
            FROM temporal_facts
            WHERE entity_name = ? AND attribute = ? AND status = 'active'
            ORDER BY as_of DESC
        """, (entity_name, attribute))
        
        return [
            {
                "fact_id": row[0],
                "value": row[1],
                "as_of": row[2],
                "confidence": row[3],
                "source": row[4]
            }
            for row in cursor.fetchall()
        ]
    
    def _supersede_fact(self, old_fact_id: str, new_fact_id: str):
        """标记事实为已取代"""
        # 先检查旧事实是否存在且为活跃状态
        cursor = self.db.execute("""
            SELECT status FROM temporal_facts WHERE fact_id = ?
        """, (old_fact_id,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Fact {old_fact_id} not found, skipping supersede")
            return
        
        if row[0] != 'active':
            logger.debug(f"Fact {old_fact_id} is not active (status={row[0]}), skipping supersede")
            return
        
        self.db.execute("""
            UPDATE temporal_facts
            SET status = 'superseded', superseded_by = ?
            WHERE fact_id = ? AND status = 'active'
        """, (new_fact_id, old_fact_id))
    
    def _record_version(
        self,
        fact_id: str,
        old_value: Optional[str],
        new_value: str,
        reason: str
    ):
        """记录版本变更"""
        version_id = f"ver_{uuid.uuid4().hex[:8]}"
        
        self.db.execute("""
            INSERT INTO fact_versions
            (version_id, fact_id, old_value, new_value, change_reason, changed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (version_id, fact_id, old_value, new_value, reason, datetime.now().isoformat()))
    
    # ========== 查询事实 ==========
    
    def get_value(
        self,
        entity_name: str,
        attribute: str,
        as_of: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取特定时间点的值
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            as_of: 时间点（None 表示最新）
        
        Returns:
            事实字典或 None
        """
        if as_of:
            # 查询特定时间点
            cursor = self.db.execute("""
                SELECT fact_id, value, as_of, confidence, source, status
                FROM temporal_facts
                WHERE entity_name = ? AND attribute = ?
                AND as_of <= ?
                AND (valid_from IS NULL OR valid_from <= ?)
                AND (valid_until IS NULL OR valid_until >= ?)
                AND status = 'active'
                ORDER BY as_of DESC
                LIMIT 1
            """, (entity_name, attribute, as_of, as_of, as_of))
        else:
            # 查询最新值
            cursor = self.db.execute("""
                SELECT fact_id, value, as_of, confidence, source, status
                FROM temporal_facts
                WHERE entity_name = ? AND attribute = ?
                AND status = 'active'
                ORDER BY as_of DESC
                LIMIT 1
            """, (entity_name, attribute))
        
        row = cursor.fetchone()
        if row:
            return {
                "fact_id": row[0],
                "value": row[1],
                "as_of": row[2],
                "confidence": row[3],
                "source": row[4],
                "status": row[5]
            }
        return None
    
    def get_history(
        self,
        entity_name: str,
        attribute: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取历史版本
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            limit: 最大返回数量
        
        Returns:
            历史事实列表
        """
        cursor = self.db.execute("""
            SELECT fact_id, value, as_of, confidence, source, status, superseded_by
            FROM temporal_facts
            WHERE entity_name = ? AND attribute = ?
            ORDER BY as_of DESC
            LIMIT ?
        """, (entity_name, attribute, limit))
        
        return [
            {
                "fact_id": row[0],
                "value": row[1],
                "as_of": row[2],
                "confidence": row[3],
                "source": row[4],
                "status": row[5],
                "superseded_by": row[6]
            }
            for row in cursor.fetchall()
        ]
    
    def get_all_temporal(
        self,
        entity_name: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取实体的所有带时间的属性
        
        Args:
            entity_name: 实体名称
        
        Returns:
            属性 -> 事实列表
        """
        cursor = self.db.execute("""
            SELECT attribute, fact_id, value, as_of, confidence, source, status
            FROM temporal_facts
            WHERE entity_name = ?
            ORDER BY attribute, as_of DESC
        """, (entity_name,))
        
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in cursor.fetchall():
            attr = row[0]
            if attr not in result:
                result[attr] = []
            result[attr].append({
                "fact_id": row[1],
                "value": row[2],
                "as_of": row[3],
                "confidence": row[4],
                "source": row[5],
                "status": row[6]
            })
        
        return result
    
    # ========== 状态管理 ==========
    
    def mark_expired(
        self,
        fact_id: str,
        reason: str = "time_based"
    ) -> bool:
        """标记事实为已过期"""
        self.db.execute("""
            UPDATE temporal_facts
            SET status = 'expired'
            WHERE fact_id = ? AND status = 'active'
        """, (fact_id,))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def mark_disputed(
        self,
        fact_id: str,
        reason: str = ""
    ) -> bool:
        """标记事实为有争议"""
        self.db.execute("""
            UPDATE temporal_facts
            SET status = 'disputed'
            WHERE fact_id = ?
        """, (fact_id,))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def retract_fact(
        self,
        fact_id: str,
        reason: str = ""
    ) -> bool:
        """撤回事实"""
        self.db.execute("""
            UPDATE temporal_facts
            SET status = 'retracted'
            WHERE fact_id = ?
        """, (fact_id,))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    # ========== 过期检测 ==========
    
    def check_expired(
        self,
        current_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检查并标记过期的事实
        
        Args:
            current_time: 当前时间（None 使用系统时间）
        
        Returns:
            过期的事实列表
        """
        if current_time is None:
            current_time = datetime.now().isoformat()
        
        # 查找已过期但仍标记为活跃的事实
        cursor = self.db.execute("""
            SELECT fact_id, entity_name, attribute, value, as_of
            FROM temporal_facts
            WHERE status = 'active'
            AND valid_until IS NOT NULL
            AND valid_until < ?
        """, (current_time,))
        
        expired_facts = []
        for row in cursor.fetchall():
            fact = {
                "fact_id": row[0],
                "entity_name": row[1],
                "attribute": row[2],
                "value": row[3],
                "as_of": row[4]
            }
            expired_facts.append(fact)
            
            # 标记为过期
            self.mark_expired(row[0])
        
        if expired_facts:
            logger.info(f"Marked {len(expired_facts)} facts as expired")
        
        return expired_facts
    
    # ========== 统计 ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {}
        
        # 按状态统计
        cursor = self.db.execute("""
            SELECT status, COUNT(*)
            FROM temporal_facts
            GROUP BY status
        """)
        for row in cursor.fetchall():
            stats[f"status_{row[0]}"] = row[1]
        
        # 总数
        cursor = self.db.execute("SELECT COUNT(*) FROM temporal_facts")
        stats["total_facts"] = cursor.fetchone()[0]
        
        # 版本数
        cursor = self.db.execute("SELECT COUNT(*) FROM fact_versions")
        stats["total_versions"] = cursor.fetchone()[0]
        
        # 实体数
        cursor = self.db.execute("SELECT COUNT(DISTINCT entity_name) FROM temporal_facts")
        stats["total_entities"] = cursor.fetchone()[0]
        
        return stats
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()