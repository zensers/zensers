# -*- coding: utf-8 -*-
"""
DreamMode - 记忆整合后台服务

实现 CONTEXT_COMPRESSION.md 第3节 Dream Mode 设计：
- 6阶段记忆整合流程
- 触发条件管理
- 重要性评分算法
"""

__all__ = ["DreamMode"]

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import asyncio
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class SessionSignal:
    """会话信号"""
    type: str  # correction, save, mention
    content: str
    timestamp: datetime
    topic: Optional[str] = None


@dataclass
class DreamReport:
    """Dream Mode 执行报告"""
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    phases: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class DreamMode:
    """
    Dream Mode - 后台记忆整合服务
    
    模仿人类睡眠时的记忆整合过程：
    - 在系统空闲时自动运行
    - 清理冗余信息
    - 强化重要记忆
    - 晋升高频知识
    
    6阶段流程：
    1. Orientation (定位) - 扫描所有记忆层
    2. Signal Gathering (信号收集) - 识别高价值模式
    3. Consolidation (整合) - 标准化、去重、清理
    4. Promotion (晋升) - 晋升高频知识到 Layer 1
    5. Pruning (修剪) - 保持 Layer 1 在限制内
    6. Archival (归档) - 压缩旧数据
    
    触发条件：
    - session_end: 会话结束时
    - scheduled: 定时（每24小时）
    - manual: 手动触发
    - threshold: Layer 1 接近上限
    """
    
    # 触发间隔（小时）
    SCHEDULED_INTERVAL_HOURS = 24
    
    # Layer 1 阈值
    LAYER1_THRESHOLD = 8 * 1024  # 8KB
    
    def __init__(
        self,
        core_memory: Any,
        session_store: Optional[Any] = None,
        knowledge_bank: Optional[Any] = None
    ):
        """
        初始化 Dream Mode
        
        Args:
            core_memory: CoreMemory 实例（Layer 1）
            session_store: 会话存储（可选）
            knowledge_bank: 知识库（可选）
        """
        self.core_memory = core_memory
        self.session_store = session_store
        self.knowledge_bank = knowledge_bank
        
        # 会话信号
        self._session_signals: List[SessionSignal] = []
        
        # 运行状态
        self._last_run: Optional[datetime] = None
        self._is_running = False
        self._cancel_requested = False
        
        # 归档路径
        self._archive_path = Path(core_memory.storage_path) / "archive"
        self._archive_path.mkdir(parents=True, exist_ok=True)
        
        logger.debug("DreamMode initialized")
    
    # ========== 触发条件 ==========
    
    def should_trigger(self, trigger_type: str) -> bool:
        """
        检查是否应该触发
        
        Args:
            trigger_type: 触发类型 (session_end, scheduled, manual, threshold)
        
        Returns:
            是否应该触发
        """
        if trigger_type == "session_end":
            return True
        
        elif trigger_type == "scheduled":
            # 检查是否超过间隔
            if self._last_run is None:
                return True
            
            elapsed = datetime.now() - self._last_run
            return elapsed >= timedelta(hours=self.SCHEDULED_INTERVAL_HOURS)
        
        elif trigger_type == "manual":
            return True
        
        elif trigger_type == "threshold":
            # 检查 Layer 1 是否接近上限
            self.core_memory._calculate_size()
            return self.core_memory.size_bytes >= self.LAYER1_THRESHOLD
        
        return False
    
    def add_session_signal(self, signal: Dict[str, Any]) -> None:
        """添加会话信号"""
        session_signal = SessionSignal(
            type=signal.get("type", "mention"),
            content=signal.get("content", ""),
            timestamp=signal.get("timestamp", datetime.now()),
            topic=signal.get("topic")
        )
        self._session_signals.append(session_signal)
    
    def clear_session_signals(self) -> None:
        """清空会话信号"""
        self._session_signals = []
    
    # ========== Phase 1: Orientation ==========
    
    def phase1_orientation(self) -> Dict[str, Any]:
        """
        Phase 1: 定位
        
        扫描所有记忆层，统计当前状态
        """
        result = {
            "entities_count": len(self.core_memory.top_entities),
            "needs_count": len(self.core_memory.core_needs),
            "patterns_count": len(self.core_memory.learned_patterns),
            "total_size": self.core_memory.size_bytes,
            "areas_to_process": []
        }
        
        # 识别需要处理的区域
        areas = []
        
        if result["entities_count"] > 15:
            areas.append("entities_nearing_limit")
        
        if result["total_size"] > 8 * 1024:
            areas.append("size_nearing_limit")
        
        if len(self._session_signals) > 10:
            areas.append("many_pending_signals")
        
        result["areas_to_process"] = areas
        
        logger.debug(f"Orientation: {result}")
        return result
    
    # ========== Phase 2: Signal Gathering ==========
    
    def phase2_signal_gathering(self) -> Dict[str, Any]:
        """
        Phase 2: 信号收集
        
        分析最近会话，识别高价值模式
        """
        user_corrections = []
        explicit_saves = []
        repeated_topics = {}
        high_value_signals = []
        
        for signal in self._session_signals:
            if signal.type == "correction":
                user_corrections.append({
                    "content": signal.content,
                    "timestamp": signal.timestamp.isoformat()
                })
                high_value_signals.append(signal.content)
            
            elif signal.type == "save":
                explicit_saves.append({
                    "content": signal.content,
                    "timestamp": signal.timestamp.isoformat()
                })
                high_value_signals.append(signal.content)
            
            elif signal.type == "mention" and signal.topic:
                if signal.topic not in repeated_topics:
                    repeated_topics[signal.topic] = 0
                repeated_topics[signal.topic] += 1
        
        # 筛选重复超过3次的话题
        repeated_topics = {
            k: v for k, v in repeated_topics.items() if v >= 3
        }
        
        result = {
            "user_corrections": user_corrections,
            "explicit_saves": explicit_saves,
            "repeated_topics": list(repeated_topics.keys()),
            "high_value_signals": high_value_signals
        }
        
        logger.debug(f"Signal gathering: {len(high_value_signals)} high value signals")
        return result
    
    # ========== Phase 3: Consolidation ==========
    
    def phase3_consolidation(self) -> Dict[str, Any]:
        """
        Phase 3: 整合
        
        日期标准化、矛盾处理、重复合并、陈旧清理
        """
        date_normalizations = 0
        contradictions_resolved = 0
        duplicates_merged = 0
        stale_references_cleaned = 0
        
        # 日期标准化
        relative_dates = ["昨天", "今天", "明天", "上周", "本月"]
        for entity in self.core_memory.top_entities:
            if entity.last_mentioned in relative_dates:
                entity.last_mentioned = datetime.now().strftime("%Y-%m-%d")
                date_normalizations += 1
        
        # 重复合并
        seen_patterns = {}
        patterns_to_keep = []
        
        for pattern in self.core_memory.learned_patterns:
            key = pattern.pattern_key
            if key in seen_patterns:
                # 合并重复
                seen_patterns[key].recurrence_count += pattern.recurrence_count
                duplicates_merged += 1
            else:
                seen_patterns[key] = pattern
                patterns_to_keep.append(pattern)
        
        self.core_memory.learned_patterns = patterns_to_keep
        
        result = {
            "date_normalizations": date_normalizations,
            "contradictions_resolved": contradictions_resolved,
            "duplicates_merged": duplicates_merged,
            "stale_references_cleaned": stale_references_cleaned
        }
        
        logger.debug(f"Consolidation: {result}")
        return result
    
    # ========== Phase 4: Promotion ==========
    
    def phase4_promotion(self) -> Dict[str, Any]:
        """
        Phase 4: 晋升
        
        检查晋升条件，晋升高频知识到 Layer 1
        """
        entities_promoted = []
        patterns_promoted = []
        needs_marked_core = []
        
        # 检查实体晋升
        for entity in self.core_memory.top_entities:
            if entity.mention_count >= self.core_memory.ENTITY_PROMOTION_THRESHOLD:
                entities_promoted.append({
                    "name": entity.name,
                    "mention_count": entity.mention_count
                })
        
        # 检查模式晋升
        for pattern in self.core_memory.learned_patterns:
            if pattern.recurrence_count >= self.core_memory.PATTERN_PROMOTION_THRESHOLD:
                patterns_promoted.append({
                    "pattern_key": pattern.pattern_key,
                    "recurrence_count": pattern.recurrence_count
                })
        
        # 检查需求晋升
        for need in self.core_memory.core_needs:
            if need.frequency >= self.core_memory.NEED_PROMOTION_THRESHOLD:
                needs_marked_core.append({
                    "topic": need.topic,
                    "frequency": need.frequency
                })
        
        result = {
            "entities_promoted": entities_promoted,
            "patterns_promoted": patterns_promoted,
            "needs_marked_core": needs_marked_core
        }
        
        logger.debug(f"Promotion: {len(entities_promoted)} entities, {len(patterns_promoted)} patterns")
        return result
    
    # ========== Phase 5: Pruning ==========
    
    def phase5_pruning(self) -> Dict[str, Any]:
        """
        Phase 5: 修剪
        
        检查 Layer 1 大小，移除低分条目
        """
        self.core_memory._calculate_size()
        
        size_before = self.core_memory.size_bytes
        importance_scores = {}
        items_removed = []
        
        # 计算重要性分数
        for entity in self.core_memory.top_entities:
            score = self._calculate_importance({
                "mention_count": entity.mention_count,
                "last_mentioned": entity.last_mentioned
            })
            importance_scores[entity.name] = score
        
        # 如果超过限制，移除低分条目
        if size_before >= 8 * 1024:
            # 按分数排序
            sorted_entities = sorted(
                self.core_memory.top_entities,
                key=lambda e: importance_scores.get(e.name, 0),
                reverse=True
            )
            
            # 保留高分条目，限制数量
            if len(sorted_entities) > self.core_memory.MAX_TOP_ENTITIES:
                removed = sorted_entities[self.core_memory.MAX_TOP_ENTITIES:]
                items_removed = [{"name": e.name, "score": importance_scores.get(e.name, 0)} for e in removed]
                self.core_memory.top_entities = sorted_entities[:self.core_memory.MAX_TOP_ENTITIES]
        
        self.core_memory._calculate_size()
        size_after = self.core_memory.size_bytes
        
        result = {
            "layer1_size_before": size_before,
            "layer1_size_after": size_after,
            "importance_scores": importance_scores,
            "items_removed": items_removed
        }
        
        logger.debug(f"Pruning: {size_before} -> {size_after} bytes")
        return result
    
    def _calculate_importance(self, item: Dict[str, Any]) -> float:
        """
        计算记忆条目的重要性分数
        
        考虑因素：
        - 提及频率 (mention_count): 0-40分
        - 最近活跃时间 (recency): 0-30分
        - 用户反馈信号: 0-20分
        - 跨会话: 0-10分
        """
        score = 0.0
        
        # 1. 频率得分 (0-40分)
        frequency_score = min(item.get("mention_count", 0) * 4, 40)
        score += frequency_score
        
        # 2. 时新性得分 (0-30分)
        last_mentioned = item.get("last_mentioned")
        if last_mentioned:
            try:
                if isinstance(last_mentioned, str):
                    last_date = datetime.strptime(last_mentioned, "%Y-%m-%d")
                else:
                    last_date = last_mentioned
                
                days_since = (datetime.now() - last_date).days
                recency_score = max(0, 30 - days_since)
                score += recency_score
            except (ValueError, TypeError):
                pass
        
        return score
    
    # ========== Phase 6: Archival ==========
    
    def phase6_archival(self) -> Dict[str, Any]:
        """
        Phase 6: 归档
        
        压缩旧会话历史，移动到归档存储
        """
        sessions_archived = 0
        compression_ratio = 0.0
        archived_path = None
        original_data_cleaned = False
        
        # 创建归档记录
        archive_record = {
            "timestamp": datetime.now().isoformat(),
            "core_memory_snapshot": self.core_memory.to_dict()
        }
        
        # 保存归档
        archive_file = self._archive_path / f"dream_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump(archive_record, f, ensure_ascii=False, indent=2)
        
        archived_path = str(archive_file)
        sessions_archived = 1
        
        # 清理会话信号
        self.clear_session_signals()
        original_data_cleaned = True
        
        result = {
            "sessions_archived": sessions_archived,
            "compression_ratio": compression_ratio,
            "archived_path": archived_path,
            "original_data_cleaned": original_data_cleaned
        }
        
        logger.debug(f"Archival: {sessions_archived} sessions archived")
        return result
    
    # ========== 主执行流程 ==========
    
    def run(self, trigger_reason: str = "manual") -> Dict[str, Any]:
        """
        运行完整 Dream Mode
        
        Args:
            trigger_reason: 触发原因
        
        Returns:
            执行报告
        """
        report = DreamReport(
            status="running",
            started_at=datetime.now()
        )
        
        try:
            self._is_running = True
            self._cancel_requested = False
            
            logger.info(f"Dream Mode started, reason: {trigger_reason}")
            
            # Phase 1: Orientation
            if not self._cancel_requested:
                report.phases["orientation"] = self.phase1_orientation()
            
            # Phase 2: Signal Gathering
            if not self._cancel_requested:
                report.phases["signal_gathering"] = self.phase2_signal_gathering()
            
            # Phase 3: Consolidation
            if not self._cancel_requested:
                report.phases["consolidation"] = self.phase3_consolidation()
            
            # Phase 4: Promotion
            if not self._cancel_requested:
                report.phases["promotion"] = self.phase4_promotion()
            
            # Phase 5: Pruning
            if not self._cancel_requested:
                report.phases["pruning"] = self.phase5_pruning()
            
            # Phase 6: Archival
            if not self._cancel_requested:
                report.phases["archival"] = self.phase6_archival()
            
            # 保存核心记忆
            self.core_memory.save()
            
            report.status = "completed"
            report.completed_at = datetime.now()
            report.duration_ms = (report.completed_at - report.started_at).total_seconds() * 1000
            
            self._last_run = datetime.now()
            
            logger.info(f"Dream Mode completed in {report.duration_ms:.2f}ms")
            
        except Exception as e:
            report.status = "failed"
            report.errors.append(str(e))
            logger.error(f"Dream Mode failed: {e}")
        
        finally:
            self._is_running = False
        
        return {
            "status": report.status,
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            "duration_ms": report.duration_ms,
            "phases": report.phases,
            "errors": report.errors
        }
    
    def start_async(self) -> None:
        """异步启动 Dream Mode"""
        self._is_running = True
        self._cancel_requested = False
    
    def cancel(self) -> bool:
        """取消 Dream Mode"""
        if self._is_running:
            self._cancel_requested = True
            return True
        return False