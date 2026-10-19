# -*- coding: utf-8 -*-
"""
LearningManager - 学习晋升机制

Phase 3.7 核心功能: 管理学习记录的晋升

功能:
- 检测晋升候选
- 自动晋升机制
- 跨会话检测
- 与 CoreMemory 集成
"""

__all__ = ["LearningManager"]

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Set

from .learning_store import LearningStore, LearningRecord

logger = logging.getLogger(__name__)


class LearningManager:
    """
    学习管理器
    
    管理学习记录的晋升和 CoreMemory 集成。
    
    晋升规则:
    - recurrence_count >= 3
    - 跨至少 2 个会话
    - 晋升到 CoreMemory.core_learnings
    """
    
    # 晋升阈值
    PROMOTION_THRESHOLD = 3  # 重复次数阈值
    MIN_SESSIONS = 2          # 最少会话数
    
    def __init__(
        self,
        learning_store: LearningStore,
        core_memory: Optional[Any] = None
    ):
        """
        初始化学习管理器
        
        Args:
            learning_store: 学习记录存储
            core_memory: 核心记忆（可选）
        """
        self.learning_store = learning_store
        self.core_memory = core_memory
        
        logger.info("LearningManager initialized")
    
    def check_promotion_eligible(self, record: LearningRecord) -> bool:
        """
        检查学习记录是否符合晋升条件
        
        Args:
            record: 学习记录
            
        Returns:
            是否符合晋升条件
        """
        # 检查重复次数
        if record.recurrence_count < self.PROMOTION_THRESHOLD:
            return False
        
        # 检查是否跨会话
        if record.session_id:
            # 查询相同 pattern_key 的不同会话
            sessions = self._get_sessions_for_pattern(record.pattern_key)
            if len(sessions) < self.MIN_SESSIONS:
                return False
        
        return True
    
    def _get_sessions_for_pattern(self, pattern_key: Optional[str]) -> Set[str]:
        """
        获取相同 pattern_key 的会话列表
        
        Args:
            pattern_key: 模式键
            
        Returns:
            会话ID集合
        """
        if not pattern_key:
            return set()
        
        # 查询数据库，从 session_ids 字段读取
        import json
        cursor = self.learning_store.db.execute(
            """
            SELECT session_ids FROM learnings 
            WHERE pattern_key = ? AND user_id = ?
            """,
            (pattern_key, self.learning_store.user_id)
        )
        
        row = cursor.fetchone()
        if row and row["session_ids"]:
            return set(json.loads(row["session_ids"]))
        
        return set()
    
    def get_promotion_candidates(self) -> List[LearningRecord]:
        """
        获取所有晋升候选
        
        Returns:
            符合晋升条件的学习记录列表
        """
        candidates = []
        
        # 获取高重复次数的待处理记录
        pending_records = self.learning_store.query_learnings(
            status="pending",
            min_recurrence=self.PROMOTION_THRESHOLD,
            limit=100
        )
        
        for record in pending_records:
            if self.check_promotion_eligible(record):
                candidates.append(record)
        
        logger.info(f"Found {len(candidates)} promotion candidates")
        return candidates
    
    def promote_learning(
        self,
        record: LearningRecord,
        promote_to_core_memory: bool = True
    ) -> bool:
        """
        晋升学习记录
        
        Args:
            record: 学习记录
            promote_to_core_memory: 是否晋升到 CoreMemory
            
        Returns:
            是否成功
        """
        try:
            # 更新学习记录状态
            self.learning_store.update_status(
                learning_id=record.learning_id,
                status="promoted",
                promoted_to="core_memory" if promote_to_core_memory else "marked"
            )
            
            # 晋升到 CoreMemory
            if promote_to_core_memory and self.core_memory:
                self._add_to_core_memory(record)
            
            logger.info(f"Promoted learning {record.learning_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to promote learning: {e}")
            return False
    
    def _add_to_core_memory(self, record: LearningRecord):
        """
        添加学习记录到 CoreMemory
        
        Args:
            record: 学习记录
        """
        if not self.core_memory:
            logger.warning("CoreMemory not available")
            return
        
        # 创建核心学习记录
        core_learning = {
            "learning_id": record.learning_id,
            "category": record.category,
            "pattern_key": record.pattern_key,
            "content": record.content,
            "recurrence_count": record.recurrence_count,
            "promoted_at": datetime.now().isoformat()
        }
        
        # 添加到 CoreMemory
        if hasattr(self.core_memory, "add_core_learning"):
            self.core_memory.add_core_learning(core_learning)
        else:
            logger.warning("CoreMemory does not support add_core_learning")
    
    def auto_promote(self) -> List[LearningRecord]:
        """
        自动晋升所有符合条件的记录
        
        Returns:
            晋升的记录列表
        """
        candidates = self.get_promotion_candidates()
        promoted = []
        
        for record in candidates:
            if self.promote_learning(record):
                promoted.append(record)
        
        if promoted:
            logger.info(f"Auto-promoted {len(promoted)} learnings")
        
        return promoted
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """
        获取学习摘要
        
        Returns:
            学习摘要信息
        """
        stats = self.learning_store.get_stats()
        candidates = self.get_promotion_candidates()
        
        # 按类别分组
        by_category = {}
        for candidate in candidates:
            cat = candidate.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(candidate.to_dict())
        
        return {
            "stats": stats,
            "promotion_candidates": len(candidates),
            "candidates_by_category": by_category,
            "promotion_threshold": self.PROMOTION_THRESHOLD,
            "min_sessions": self.MIN_SESSIONS
        }
    
    def process_user_feedback(
        self,
        feedback_type: str,
        content: str,
        session_id: Optional[str] = None
    ) -> LearningRecord:
        """
        处理用户反馈
        
        Args:
            feedback_type: 反馈类型 (correction/error/pattern/preference)
            content: 反馈内容
            session_id: 会话ID
            
        Returns:
            学习记录
        """
        return self.learning_store.record_learning(
            category=feedback_type,
            content=content,
            session_id=session_id
        )
    
    def get_recommended_actions(self) -> List[Dict[str, Any]]:
        """
        获取推荐的行动建议
        
        Returns:
            行动建议列表
        """
        actions = []
        
        # 检查待晋升的学习
        candidates = self.get_promotion_candidates()
        if candidates:
            actions.append({
                "type": "promotion",
                "message": f"发现 {len(candidates)} 条学习记录符合晋升条件",
                "details": [c.to_dict() for c in candidates[:5]]
            })
        
        # 检查高频错误
        error_records = self.learning_store.query_learnings(
            category="error",
            min_recurrence=2,
            limit=5
        )
        if error_records:
            actions.append({
                "type": "error_pattern",
                "message": f"发现 {len(error_records)} 个重复错误模式",
                "details": [r.to_dict() for r in error_records]
            })
        
        # 检查用户偏好
        preference_records = self.learning_store.query_learnings(
            category="preference",
            min_recurrence=2,
            limit=5
        )
        if preference_records:
            actions.append({
                "type": "preference",
                "message": f"发现 {len(preference_records)} 个稳定偏好",
                "details": [r.to_dict() for r in preference_records]
            })
        
        return actions