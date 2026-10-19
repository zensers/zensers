# -*- coding: utf-8 -*-
"""
ProvenanceStore - 来源追溯

实现知识的来源追溯：
- 每个事实追溯到原始文档
- 来源可信度分级
- 审计追踪

设计参考：
- Phase 0 约束层的 SourceWhitelist 和 FactTracer
- Graphiti 的来源管理

使用方式：
```python
# 记录来源
provenance.record_source(
    entity_name="宁德时代",
    attribute="市场份额",
    value="37%",
    source_type="research",
    source_ref="research_2024Q3.md",
    line_number=45
)

# 查询来源
sources = provenance.get_sources("宁德时代", "市场份额")

# 验证来源可信度
trust = provenance.verify_source("research_2024Q3.md")
```
"""

__all__ = [
    "ProvenanceStore",
    "SourceRecord",
    "SourceTrustLevel",
    "AuditEntry"
]

import sqlite3
import json
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SourceTrustLevel(Enum):
    """来源可信度等级"""
    TIER1_OFFICIAL = "tier1"       # 官方来源（财报、公告、官网）
    TIER2_REPUTABLE = "tier2"      # 可信媒体（财经媒体、研究机构）
    TIER3_GENERAL = "tier3"        # 一般来源（新闻报道、博客）
    TIER4_USER = "tier4"           # 用户输入
    TIER5_UNKNOWN = "tier5"        # 未知来源


@dataclass
class SourceRecord:
    """来源记录"""
    provenance_id: str
    entity_name: str
    attribute: str
    value: str
    source_type: str              # research, wiki, external, user
    source_ref: str               # 文件路径或URL
    trust_level: str = SourceTrustLevel.TIER3_GENERAL.value
    confidence: float = 0.8
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    line_number: Optional[int] = None
    context: Optional[str] = None  # 原始上下文
    fact_id: Optional[str] = None  # 关联到 TemporalFact
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEntry:
    """审计条目"""
    audit_id: str
    action: str                    # create, update, verify, dispute, retract
    entity_name: str
    attribute: str
    old_value: Optional[str]
    new_value: str
    source_ref: str
    actor: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProvenanceStore:
    """
    来源追溯存储
    
    核心功能：
    1. 记录每个事实的来源
    2. 来源可信度验证
    3. 审计追踪
    4. 来源统计分析
    
    设计参考：
    - Phase 0 SourceWhitelist: 来源分级
    - Phase 0 FactTracer: 事实溯源
    """
    
    # 来源类型到信任等级的映射
    SOURCE_TRUST_MAPPING = {
        "official_report": SourceTrustLevel.TIER1_OFFICIAL.value,
        "official_announcement": SourceTrustLevel.TIER1_OFFICIAL.value,
        "official_website": SourceTrustLevel.TIER1_OFFICIAL.value,
        "financial_report": SourceTrustLevel.TIER1_OFFICIAL.value,
        "reputable_media": SourceTrustLevel.TIER2_REPUTABLE.value,
        "research_institute": SourceTrustLevel.TIER2_REPUTABLE.value,
        "news_article": SourceTrustLevel.TIER3_GENERAL.value,
        "blog_post": SourceTrustLevel.TIER3_GENERAL.value,
        "user_input": SourceTrustLevel.TIER4_USER.value,
        "unknown": SourceTrustLevel.TIER5_UNKNOWN.value,
    }
    
    def __init__(
        self,
        db_path: str,
        user_id: str = "default"
    ):
        """
        初始化来源追溯存储
        
        Args:
            db_path: 数据库路径
            user_id: 用户ID
        """
        self.db_path = Path(db_path)
        self.user_id = user_id
        
        # 初始化数据库
        self.db = sqlite3.connect(str(self.db_path))
        self._init_tables()
        
        logger.info(f"ProvenanceStore initialized for user {user_id}")
    
    def _init_tables(self):
        """初始化数据库表"""
        # 来源记录表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS provenance (
                provenance_id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                trust_level TEXT DEFAULT 'tier3',
                confidence REAL DEFAULT 0.8,
                extracted_at TIMESTAMP NOT NULL,
                verified_at TIMESTAMP,
                verified_by TEXT,
                line_number INTEGER,
                context TEXT,
                fact_id TEXT
            )
        """)
        
        # 审计日志表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                attribute TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                source_ref TEXT,
                actor TEXT DEFAULT 'system',
                timestamp TIMESTAMP NOT NULL,
                notes TEXT
            )
        """)
        
        # 来源可信度表（自定义来源规则）
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS source_trust_rules (
                rule_id TEXT PRIMARY KEY,
                source_pattern TEXT NOT NULL,
                trust_level TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)
        
        # 创建索引
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_prov_entity ON provenance(entity_name)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_prov_source ON provenance(source_ref)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_prov_fact ON provenance(fact_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_name)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
        
        # 复合索引 - 优化常用查询
        # get_sources 查询: WHERE entity_name = ? AND attribute = ?
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_prov_entity_attr ON provenance(entity_name, attribute)")
        # get_audit_trail 查询: WHERE entity_name = ? AND attribute = ?
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity_attr ON audit_log(entity_name, attribute)")
        
        self.db.commit()
        
        # 初始化默认来源规则
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认的来源可信度规则"""
        default_rules = [
            ("*财报*", SourceTrustLevel.TIER1_OFFICIAL.value, "财务报告"),
            ("*公告*", SourceTrustLevel.TIER1_OFFICIAL.value, "官方公告"),
            ("*.gov.cn*", SourceTrustLevel.TIER1_OFFICIAL.value, "政府网站"),
            ("*.cn*", SourceTrustLevel.TIER2_REPUTABLE.value, "国内媒体"),
            ("*.com*", SourceTrustLevel.TIER3_GENERAL.value, "一般网站"),
        ]
        
        for pattern, level, desc in default_rules:
            try:
                rule_id = f"rule_{hashlib.md5(pattern.encode(), usedforsecurity=False).hexdigest()[:8]}"
                self.db.execute("""
                    INSERT OR IGNORE INTO source_trust_rules
                    (rule_id, source_pattern, trust_level, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (rule_id, pattern, level, desc, datetime.now().isoformat()))
            except Exception:
                pass
        
        self.db.commit()
    
    # ========== 记录来源 ==========
    
    def record_source(
        self,
        entity_name: str,
        attribute: str,
        value: str,
        source_type: str,
        source_ref: str,
        confidence: float = 0.8,
        line_number: Optional[int] = None,
        context: Optional[str] = None,
        fact_id: Optional[str] = None
    ) -> str:
        """
        记录来源
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            value: 值
            source_type: 来源类型
            source_ref: 来源引用
            confidence: 置信度
            line_number: 行号
            context: 原始上下文
            fact_id: 关联的事实ID
        
        Returns:
            来源记录ID
        """
        provenance_id = f"prov_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        # 确定信任等级
        trust_level = self._determine_trust_level(source_type, source_ref)
        
        self.db.execute("""
            INSERT INTO provenance
            (provenance_id, entity_name, attribute, value, source_type, source_ref,
             trust_level, confidence, extracted_at, line_number, context, fact_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            provenance_id, entity_name, attribute, value, source_type, source_ref,
            trust_level, confidence, now, line_number, context, fact_id
        ))
        
        self.db.commit()
        
        # 记录审计日志
        self._log_audit(
            action="create",
            entity_name=entity_name,
            attribute=attribute,
            old_value=None,
            new_value=value,
            source_ref=source_ref
        )
        
        logger.debug(f"Recorded provenance: {entity_name}.{attribute} <- {source_ref}")
        return provenance_id
    
    def _determine_trust_level(
        self,
        source_type: str,
        source_ref: str
    ) -> str:
        """确定来源信任等级"""
        # 1. 检查来源类型
        if source_type in self.SOURCE_TRUST_MAPPING:
            return self.SOURCE_TRUST_MAPPING[source_type]
        
        # 2. 检查自定义规则
        cursor = self.db.execute("""
            SELECT trust_level FROM source_trust_rules
            WHERE ? LIKE source_pattern
            ORDER BY LENGTH(source_pattern) DESC
            LIMIT 1
        """, (source_ref,))
        
        row = cursor.fetchone()
        if row:
            return row[0]
        
        # 3. 默认等级
        return SourceTrustLevel.TIER5_UNKNOWN.value
    
    def _log_audit(
        self,
        action: str,
        entity_name: str,
        attribute: str,
        old_value: Optional[str],
        new_value: str,
        source_ref: str,
        notes: Optional[str] = None
    ):
        """记录审计日志"""
        audit_id = f"audit_{uuid.uuid4().hex[:8]}"
        
        self.db.execute("""
            INSERT INTO audit_log
            (audit_id, action, entity_name, attribute, old_value, new_value,
             source_ref, timestamp, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id, action, entity_name, attribute, old_value, new_value,
            source_ref, datetime.now().isoformat(), notes
        ))
        
        self.db.commit()
    
    # ========== 查询来源 ==========
    
    def get_sources(
        self,
        entity_name: str,
        attribute: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取来源列表
        
        Args:
            entity_name: 实体名称
            attribute: 属性名（可选）
        
        Returns:
            来源记录列表
        """
        if attribute:
            cursor = self.db.execute("""
                SELECT provenance_id, attribute, value, source_type, source_ref,
                       trust_level, confidence, extracted_at, verified_at, context
                FROM provenance
                WHERE entity_name = ? AND attribute = ?
                ORDER BY extracted_at DESC
            """, (entity_name, attribute))
        else:
            cursor = self.db.execute("""
                SELECT provenance_id, attribute, value, source_type, source_ref,
                       trust_level, confidence, extracted_at, verified_at, context
                FROM provenance
                WHERE entity_name = ?
                ORDER BY extracted_at DESC
            """, (entity_name,))
        
        return [
            {
                "provenance_id": row[0],
                "attribute": row[1],
                "value": row[2],
                "source_type": row[3],
                "source_ref": row[4],
                "trust_level": row[5],
                "confidence": row[6],
                "extracted_at": row[7],
                "verified_at": row[8],
                "context": row[9]
            }
            for row in cursor.fetchall()
        ]
    
    def get_fact_provenance(
        self,
        fact_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取事实的来源"""
        cursor = self.db.execute("""
            SELECT provenance_id, entity_name, attribute, value, source_type,
                   source_ref, trust_level, confidence, context
            FROM provenance
            WHERE fact_id = ?
        """, (fact_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                "provenance_id": row[0],
                "entity_name": row[1],
                "attribute": row[2],
                "value": row[3],
                "source_type": row[4],
                "source_ref": row[5],
                "trust_level": row[6],
                "confidence": row[7],
                "context": row[8]
            }
        return None
    
    # ========== 验证来源 ==========
    
    def verify_source(
        self,
        provenance_id: str,
        verified_by: str = "user"
    ) -> bool:
        """
        验证来源
        
        Args:
            provenance_id: 来源记录ID
            verified_by: 验证者
        
        Returns:
            是否成功
        """
        now = datetime.now().isoformat()
        
        self.db.execute("""
            UPDATE provenance
            SET verified_at = ?, verified_by = ?
            WHERE provenance_id = ?
        """, (now, verified_by, provenance_id))
        
        self.db.commit()
        return self.db.total_changes > 0
    
    def get_trust_summary(
        self,
        entity_name: str
    ) -> Dict[str, Any]:
        """
        获取实体的来源可信度摘要
        
        Args:
            entity_name: 实体名称
        
        Returns:
            可信度摘要
        """
        cursor = self.db.execute("""
            SELECT trust_level, COUNT(*), AVG(confidence)
            FROM provenance
            WHERE entity_name = ?
            GROUP BY trust_level
        """, (entity_name,))
        
        trust_summary = {}
        total_count = 0
        total_confidence = 0.0
        
        for row in cursor.fetchall():
            trust_level, count, avg_conf = row
            trust_summary[trust_level] = {
                "count": count,
                "avg_confidence": avg_conf or 0
            }
            total_count += count
            total_confidence += (avg_conf or 0) * count
        
        return {
            "entity_name": entity_name,
            "total_sources": total_count,
            "avg_confidence": total_confidence / total_count if total_count > 0 else 0,
            "trust_distribution": trust_summary
        }
    
    # ========== 审计追踪 ==========
    
    def get_audit_trail(
        self,
        entity_name: str,
        attribute: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取审计追踪
        
        Args:
            entity_name: 实体名称
            attribute: 属性名（可选）
            limit: 最大返回数量
        
        Returns:
            审计条目列表
        """
        if attribute:
            cursor = self.db.execute("""
                SELECT audit_id, action, attribute, old_value, new_value,
                       source_ref, actor, timestamp, notes
                FROM audit_log
                WHERE entity_name = ? AND attribute = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (entity_name, attribute, limit))
        else:
            cursor = self.db.execute("""
                SELECT audit_id, action, attribute, old_value, new_value,
                       source_ref, actor, timestamp, notes
                FROM audit_log
                WHERE entity_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (entity_name, limit))
        
        return [
            {
                "audit_id": row[0],
                "action": row[1],
                "attribute": row[2],
                "old_value": row[3],
                "new_value": row[4],
                "source_ref": row[5],
                "actor": row[6],
                "timestamp": row[7],
                "notes": row[8]
            }
            for row in cursor.fetchall()
        ]
    
    # ========== 统计 ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {}
        
        # 来源总数
        cursor = self.db.execute("SELECT COUNT(*) FROM provenance")
        stats["total_provenance"] = cursor.fetchone()[0]
        
        # 按信任等级统计
        cursor = self.db.execute("""
            SELECT trust_level, COUNT(*)
            FROM provenance
            GROUP BY trust_level
        """)
        stats["by_trust_level"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 审计条目数
        cursor = self.db.execute("SELECT COUNT(*) FROM audit_log")
        stats["total_audits"] = cursor.fetchone()[0]
        
        # 已验证来源数
        cursor = self.db.execute("""
            SELECT COUNT(*) FROM provenance WHERE verified_at IS NOT NULL
        """)
        stats["verified_count"] = cursor.fetchone()[0]
        
        return stats
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()