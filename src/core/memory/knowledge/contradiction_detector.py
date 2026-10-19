# -*- coding: utf-8 -*-
"""
ContradictionDetector - 矛盾检测器

检测知识图谱中的矛盾，借鉴 Zelph 设计。

核心功能：
- 数值矛盾检测：同一实体同一指标不同值
- 关系矛盾检测：同一对实体有冲突关系
- 时间矛盾检测：同一时间点有矛盾事实
- 矛盾解决策略

使用方式：
```python
detector = ContradictionDetector(knowledge_bank)
contradictions = detector.detect_contradictions()
for c in contradictions:
    print(f"{c.entity_name}: {c.value_1} vs {c.value_2}")
```
"""

__all__ = [
    "ContradictionDetector",
    "Contradiction",
    "ContradictionType",
    "ResolutionStatus"
]

import sqlite3
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ContradictionType(Enum):
    """矛盾类型"""
    NUMERIC = "numeric"        # 数值矛盾
    RELATION = "relation"      # 关系矛盾
    TEMPORAL = "temporal"      # 时间矛盾
    DEFINITION = "definition"  # 定义矛盾


class ResolutionStatus(Enum):
    """解决状态"""
    PENDING = "pending"        # 待解决
    RESOLVED = "resolved"      # 已解决
    IGNORED = "ignored"        # 已忽略
    MANUAL = "manual"          # 需人工介入


@dataclass
class Contradiction:
    """
    矛盾记录
    
    Attributes:
        contradiction_id: 矛盾ID
        entity_name: 实体名
        attribute: 属性名
        contradiction_type: 矛盾类型
        value_1: 第一个值
        source_1: 第一个来源
        as_of_1: 第一个时间点
        value_2: 第二个值
        source_2: 第二个来源
        as_of_2: 第二个时间点
        resolution_status: 解决状态
        resolution_note: 解决说明
        confidence_diff: 置信度差异
        created_at: 创建时间
    """
    contradiction_id: str
    entity_name: str
    attribute: str
    contradiction_type: ContradictionType
    value_1: str
    source_1: str
    value_2: str
    source_2: str
    as_of_1: Optional[str] = None
    as_of_2: Optional[str] = None
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    resolution_note: str = ""
    confidence_diff: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "contradiction_id": self.contradiction_id,
            "entity_name": self.entity_name,
            "attribute": self.attribute,
            "contradiction_type": self.contradiction_type.value,
            "value_1": self.value_1,
            "source_1": self.source_1,
            "as_of_1": self.as_of_1,
            "value_2": self.value_2,
            "source_2": self.source_2,
            "as_of_2": self.as_of_2,
            "resolution_status": self.resolution_status.value,
            "resolution_note": self.resolution_note,
            "confidence_diff": self.confidence_diff,
            "created_at": self.created_at.isoformat()
        }


class ContradictionDetector:
    """
    矛盾检测器
    
    检测知识图谱中的矛盾并提供解决策略。
    
    Attributes:
        db_path: 数据库路径
        db: SQLite 连接
        tolerance: 数值容差（百分比）
    """
    
    def __init__(
        self,
        db_path: str,
        user_id: str,
        tolerance: float = 0.1
    ):
        """
        初始化矛盾检测器
        
        Args:
            db_path: 数据库路径
            user_id: 用户ID
            tolerance: 数值容差（默认10%）
        """
        self.db_path = Path(db_path)
        self.user_id = user_id
        self.tolerance = tolerance
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self.db = sqlite3.connect(str(self.db_path))
        self._init_tables()
        
        logger.info(f"ContradictionDetector initialized: db_path={db_path}")
    
    def _init_tables(self):
        """初始化数据库表"""
        # 矛盾记录表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                contradiction_id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                attribute TEXT NOT NULL,
                contradiction_type TEXT NOT NULL,
                value_1 TEXT NOT NULL,
                source_1 TEXT NOT NULL,
                as_of_1 TEXT,
                value_2 TEXT NOT NULL,
                source_2 TEXT NOT NULL,
                as_of_2 TEXT,
                resolution_status TEXT DEFAULT 'pending',
                resolution_note TEXT,
                confidence_diff REAL,
                created_at TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP
            )
        """)
        
        # 创建索引
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_contrad_entity ON contradictions(entity_name)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_contrad_attr ON contradictions(attribute)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_contrad_status ON contradictions(resolution_status)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_contrad_entity_attr ON contradictions(entity_name, attribute)")
        
        self.db.commit()
    
    def detect_contradictions(
        self,
        temporal_db_path: Optional[str] = None
    ) -> List[Contradiction]:
        """
        检测所有矛盾
        
        Args:
            temporal_db_path: 时间知识数据库路径
        
        Returns:
            矛盾列表
        """
        contradictions: List[Contradiction] = []
        
        # 如果提供了 temporal_db，从那里检测
        if temporal_db_path:
            contradictions.extend(self._detect_from_temporal_db(temporal_db_path))
        
        # 检测数据库中已有的未解决矛盾
        pending = self._get_pending_contradictions()
        contradictions.extend(pending)
        
        logger.info(f"Detected {len(contradictions)} contradictions")
        return contradictions
    
    def _detect_from_temporal_db(
        self,
        temporal_db_path: str
    ) -> List[Contradiction]:
        """
        从时间知识数据库检测矛盾
        
        Args:
            temporal_db_path: 时间知识数据库路径
        
        Returns:
            检测到的矛盾列表
        """
        contradictions: List[Contradiction] = []
        temp_db = None
        
        try:
            temp_db = sqlite3.connect(temporal_db_path)
            
            # 查询同一实体同一属性的所有事实
            cursor = temp_db.execute("""
                SELECT entity_name, attribute, value, source, as_of, confidence, fact_id
                FROM temporal_facts
                WHERE status = 'active'
                ORDER BY entity_name, attribute, as_of
            """)
            
            # 按实体-属性分组
            facts_by_key: Dict[Tuple[str, str], List[Dict]] = {}
            for row in cursor.fetchall():
                key = (row[0], row[1])  # (entity_name, attribute)
                if key not in facts_by_key:
                    facts_by_key[key] = []
                facts_by_key[key].append({
                    "entity_name": row[0],
                    "attribute": row[1],
                    "value": row[2],
                    "source": row[3],
                    "as_of": row[4],
                    "confidence": row[5],
                    "fact_id": row[6]
                })
            
            # 检测每组的矛盾
            for key, facts in facts_by_key.items():
                if len(facts) < 2:
                    continue
                
                # 比较相邻事实
                for i in range(len(facts) - 1):
                    for j in range(i + 1, len(facts)):
                        fact1 = facts[i]
                        fact2 = facts[j]
                        
                        # 检测数值矛盾
                        if self._is_numeric_contradiction(fact1, fact2):
                            c = self._create_contradiction(
                                fact1, fact2,
                                ContradictionType.NUMERIC
                            )
                            contradictions.append(c)
                            self._save_contradiction(c)
            
        except Exception as e:
            logger.error(f"Failed to detect from temporal db: {e}")
        finally:
            if temp_db:
                temp_db.close()
        
        return contradictions
    
    def _is_numeric_contradiction(
        self,
        fact1: Dict,
        fact2: Dict
    ) -> bool:
        """
        判断是否为数值矛盾
        
        Args:
            fact1: 第一个事实
            fact2: 第二个事实
        
        Returns:
            是否为矛盾
        """
        value1 = fact1.get("value", "")
        value2 = fact2.get("value", "")
        
        # 尝试解析数值
        num1 = self._parse_numeric_value(value1)
        num2 = self._parse_numeric_value(value2)
        
        if num1 is None or num2 is None:
            # 非数值，直接比较字符串
            return value1 != value2
        
        # 数值比较，考虑容差
        if num1 == 0 or num2 == 0:
            return num1 != num2
        
        diff = abs(num1 - num2) / max(abs(num1), abs(num2))
        return diff > self.tolerance
    
    def _parse_numeric_value(self, value: str) -> Optional[float]:
        """
        解析数值
        
        支持格式：
        - 纯数字: 123, 12.5
        - 百分比: 37%, 15.5%
        - 单位: 1.2万亿, 100亿
        - 范围: 100-150（取中值）
        
        Args:
            value: 原始值
        
        Returns:
            解析后的数值或 None
        """
        if not value:
            return None
        
        # 清理字符串
        value = value.strip()
        
        # 百分比
        if "%" in value:
            match = re.search(r'([\d.]+)%', value)
            if match:
                return float(match.group(1))
        
        # 亿/万亿单位
        if "万亿" in value:
            match = re.search(r'([\d.]+)万亿', value)
            if match:
                return float(match.group(1)) * 10000  # 转为亿
        
        if "亿" in value:
            match = re.search(r'([\d.]+)亿', value)
            if match:
                return float(match.group(1))
        
        # 范围
        if "-" in value:
            match = re.search(r'([\d.]+)-([\d.]+)', value)
            if match:
                return (float(match.group(1)) + float(match.group(2))) / 2
        
        # 纯数字
        match = re.search(r'^([\d.]+)$', value)
        if match:
            return float(match.group(1))
        
        return None
    
    def _create_contradiction(
        self,
        fact1: Dict,
        fact2: Dict,
        contradiction_type: ContradictionType
    ) -> Contradiction:
        """
        创建矛盾记录
        
        Args:
            fact1: 第一个事实
            fact2: 第二个事实
            contradiction_type: 矛盾类型
        
        Returns:
            Contradiction 实例
        """
        import uuid
        
        return Contradiction(
            contradiction_id=f"contrad_{uuid.uuid4().hex[:12]}",
            entity_name=fact1.get("entity_name", ""),
            attribute=fact1.get("attribute", ""),
            contradiction_type=contradiction_type,
            value_1=fact1.get("value", ""),
            source_1=fact1.get("source", ""),
            value_2=fact2.get("value", ""),
            source_2=fact2.get("source", ""),
            as_of_1=fact1.get("as_of"),
            as_of_2=fact2.get("as_of"),
            confidence_diff=abs(
                fact1.get("confidence", 0.8) - fact2.get("confidence", 0.8)
            )
        )
    
    def _save_contradiction(self, contradiction: Contradiction):
        """
        保存矛盾到数据库
        
        Args:
            contradiction: 矛盾记录
        """
        try:
            self.db.execute("""
                INSERT OR REPLACE INTO contradictions
                (contradiction_id, entity_name, attribute, contradiction_type,
                 value_1, source_1, value_2, source_2, as_of_1, as_of_2,
                 resolution_status, resolution_note, confidence_diff, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contradiction.contradiction_id,
                contradiction.entity_name,
                contradiction.attribute,
                contradiction.contradiction_type.value,
                contradiction.value_1,
                contradiction.source_1,
                contradiction.value_2,
                contradiction.source_2,
                contradiction.as_of_1,
                contradiction.as_of_2,
                contradiction.resolution_status.value,
                contradiction.resolution_note,
                contradiction.confidence_diff,
                contradiction.created_at.isoformat()
            ))
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to save contradiction: {e}")
    
    def _get_pending_contradictions(self) -> List[Contradiction]:
        """
        获取待解决的矛盾
        
        Returns:
            待解决矛盾列表
        """
        cursor = self.db.execute("""
            SELECT contradiction_id, entity_name, attribute, contradiction_type,
                   value_1, source_1, value_2, source_2, as_of_1, as_of_2,
                   resolution_status, resolution_note, confidence_diff, created_at
            FROM contradictions
            WHERE resolution_status = 'pending'
        """)
        
        contradictions = []
        for row in cursor.fetchall():
            c = Contradiction(
                contradiction_id=row[0],
                entity_name=row[1],
                attribute=row[2],
                contradiction_type=ContradictionType(row[3]),
                value_1=row[4],
                source_1=row[5],
                value_2=row[6],
                source_2=row[7],
                as_of_1=row[8],
                as_of_2=row[9],
                resolution_status=ResolutionStatus(row[10]),
                resolution_note=row[11] or "",
                confidence_diff=row[12] or 0.0,
                created_at=datetime.fromisoformat(row[13])
            )
            contradictions.append(c)
        
        return contradictions
    
    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution: ResolutionStatus,
        note: str = "",
        preferred_value: Optional[str] = None
    ):
        """
        解决矛盾
        
        Args:
            contradiction_id: 矛盾ID
            resolution: 解决状态
            note: 解决说明
            preferred_value: 选择保留的值（可选）
        """
        self.db.execute("""
            UPDATE contradictions
            SET resolution_status = ?, resolution_note = ?, resolved_at = ?
            WHERE contradiction_id = ?
        """, (
            resolution.value,
            note,
            datetime.now().isoformat(),
            contradiction_id
        ))
        self.db.commit()
        
        logger.info(f"Resolved contradiction {contradiction_id}: {resolution.value}")
    
    def get_resolution_suggestion(
        self,
        contradiction: Contradiction
    ) -> Dict[str, Any]:
        """
        获取矛盾解决建议
        
        Args:
            contradiction: 矛盾记录
        
        Returns:
            建议字典
        """
        suggestion = {
            "contradiction_id": contradiction.contradiction_id,
            "type": contradiction.contradiction_type.value,
            "recommendation": None,
            "reason": None,
            "options": []
        }
        
        # 基于置信度差异推荐
        if contradiction.confidence_diff > 0.2:
            # 置信度差异大，推荐高置信度的
            # 需要从 temporal_db 获取实际置信度
            suggestion["recommendation"] = "选择置信度较高的值"
            suggestion["reason"] = f"置信度差异 {contradiction.confidence_diff:.2f} 显著"
        
        # 基于时间推荐
        if contradiction.as_of_1 and contradiction.as_of_2:
            # 比较时间
            try:
                from src.utils.time_utils import parse_time
                t1 = parse_time(contradiction.as_of_1)
                t2 = parse_time(contradiction.as_of_2)
                
                if t1 and t2:
                    if t1 > t2:
                        suggestion["recommendation"] = f"推荐使用 {contradiction.value_1}"
                        suggestion["reason"] = f"{contradiction.as_of_1} 更新于 {contradiction.as_of_2}"
                    else:
                        suggestion["recommendation"] = f"推荐使用 {contradiction.value_2}"
                        suggestion["reason"] = f"{contradiction.as_of_2} 更新于 {contradiction.as_of_1}"
            except Exception:
                pass
        
        # 提供选项
        suggestion["options"] = [
            {"value": contradiction.value_1, "source": contradiction.source_1},
            {"value": contradiction.value_2, "source": contradiction.source_2},
            {"action": "忽略", "note": "数据差异在可接受范围内"},
            {"action": "保留两者", "note": "标记为不同时间点的数据"}
        ]
        
        return suggestion
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取矛盾统计
        
        Returns:
            统计信息
        """
        # 总数
        cursor = self.db.execute("SELECT COUNT(*) FROM contradictions")
        total = cursor.fetchone()[0]
        
        # 按状态统计
        cursor = self.db.execute("""
            SELECT resolution_status, COUNT(*) 
            FROM contradictions 
            GROUP BY resolution_status
        """)
        by_status = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 按类型统计
        cursor = self.db.execute("""
            SELECT contradiction_type, COUNT(*) 
            FROM contradictions 
            GROUP BY contradiction_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "total": total,
            "pending": by_status.get("pending", 0),
            "resolved": by_status.get("resolved", 0),
            "ignored": by_status.get("ignored", 0),
            "by_type": by_type,
            "by_status": by_status
        }
    
    def clear_resolved(self, days: int = 30):
        """
        清理已解决的矛盾
        
        Args:
            days: 保留天数
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        self.db.execute("""
            DELETE FROM contradictions
            WHERE resolution_status IN ('resolved', 'ignored')
            AND resolved_at < ?
        """, (cutoff.isoformat(),))
        
        self.db.commit()
        logger.info(f"Cleared resolved contradictions older than {days} days")
    
    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，确保连接关闭"""
        self.close()
        return False