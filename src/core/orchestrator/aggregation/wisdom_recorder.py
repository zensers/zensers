"""
经验记录器

职责：
- 记录执行经验
- 更新 WisdomStore
- 支持经验检索和推荐

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.wisdom import WisdomStore

logger = logging.getLogger(__name__)


@dataclass
class ExperienceRecord:
    """
    经验记录
    
    Attributes:
        task_type: 任务类型
        task_aspect: 任务维度
        skills_used: 使用的Skills
        success: 是否成功
        approach: 使用的方法
        duration_ms: 执行耗时
        confidence_score: 置信度评分
        agent_id: Agent ID
        error: 错误信息（失败时）
        metadata: 元数据
    """
    task_type: str
    task_aspect: str
    skills_used: List[str]
    success: bool
    approach: str
    duration_ms: int
    confidence_score: float = 0.5
    agent_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WisdomRecorderConfig:
    """经验记录器配置"""
    auto_record: bool = True           # 自动记录
    min_duration_ms: int = 100         # 最小记录时长
    record_failures: bool = True       # 记录失败经验
    store_path: Optional[Path] = None  # 存储路径


class WisdomRecorder:
    """
    经验记录器
    
    职责：
    - 记录执行经验
    - 更新 WisdomStore
    - 支持经验检索和推荐
    
    使用示例:
        recorder = WisdomRecorder(wisdom_store, config)
        
        # 开始记录
        recorder.start_recording(
            task_type="research",
            task_aspect="market_analysis",
            skills=["search_skill", "http_skill"]
        )
        
        # 结束记录
        recorder.end_recording(
            success=True,
            approach="multi_source_collection"
        )
    """
    
    def __init__(
        self,
        wisdom_store: Optional["WisdomStore"] = None,
        config: Optional[WisdomRecorderConfig] = None,
    ):
        self.wisdom_store = wisdom_store
        self.config = config or WisdomRecorderConfig()
        
        # 当前记录
        self._current: Optional[ExperienceRecord] = None
        self._start_time: Optional[float] = None
        
        # 统计
        self._total_recorded = 0
        self._total_success = 0
        self._total_failed = 0
    
    def start_recording(
        self,
        task_type: str,
        task_aspect: str,
        skills: List[str],
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        开始记录
        
        Args:
            task_type: 任务类型
            task_aspect: 任务维度
            skills: 使用的Skills
            agent_id: Agent ID
            metadata: 元数据
        """
        self._current = ExperienceRecord(
            task_type=task_type,
            task_aspect=task_aspect,
            skills_used=skills,
            success=False,
            approach="",
            duration_ms=0,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        self._start_time = time.time()
        
        logger.debug(f"Started recording: {task_type}:{task_aspect}")
    
    def end_recording(
        self,
        success: bool,
        approach: str,
        confidence_score: float = 0.5,
        error: Optional[str] = None,
    ) -> Optional[ExperienceRecord]:
        """
        结束记录
        
        Args:
            success: 是否成功
            approach: 使用的方法
            confidence_score: 置信度评分
            error: 错误信息
            
        Returns:
            经验记录，如果未开始记录则返回None
        """
        if not self._current or not self._start_time:
            logger.warning("No recording in progress")
            return None
        
        # 计算耗时
        duration_ms = int((time.time() - self._start_time) * 1000)
        
        # 更新记录
        self._current.success = success
        self._current.approach = approach
        self._current.duration_ms = duration_ms
        self._current.confidence_score = confidence_score
        self._current.error = error
        
        # 检查是否需要记录
        if not self._should_record(self._current):
            self._reset()
            return None
        
        # 存储到 WisdomStore
        if self.wisdom_store and self.config.auto_record:
            self._store_experience(self._current)
        
        # 更新统计
        self._total_recorded += 1
        if success:
            self._total_success += 1
        else:
            self._total_failed += 1
        
        record = self._current
        self._reset()
        
        logger.debug(f"Ended recording: success={success}, duration={duration_ms}ms")
        
        return record
    
    def _should_record(self, record: ExperienceRecord) -> bool:
        """检查是否应该记录"""
        # 时长检查
        if record.duration_ms < self.config.min_duration_ms:
            return False
        
        # 失败记录检查
        if not record.success and not self.config.record_failures:
            return False
        
        return True
    
    def _store_experience(self, record: ExperienceRecord) -> None:
        """存储经验到 WisdomStore"""
        if not self.wisdom_store:
            logger.warning("WisdomStore not configured, skipping experience storage")
            return
        
        try:
            self.wisdom_store.record_experience(
                task_type=record.task_type,
                task_aspect=record.task_aspect,
                skills_used=record.skills_used,
                success=record.success,
                approach=record.approach,
                duration_ms=record.duration_ms,
                confidence_score=record.confidence_score,
            )
        except Exception as e:
            logger.error(f"Failed to store experience: {e}")
    
    def _reset(self) -> None:
        """重置当前记录"""
        self._current = None
        self._start_time = None
    
    def record_directly(
        self,
        task_type: str,
        task_aspect: str,
        skills: List[str],
        success: bool,
        approach: str,
        duration_ms: int,
        confidence_score: float = 0.5,
    ) -> bool:
        """
        直接记录经验（不使用开始/结束模式）
        
        Args:
            task_type: 任务类型
            task_aspect: 任务维度
            skills: 使用的Skills
            success: 是否成功
            approach: 使用的方法
            duration_ms: 执行耗时
            confidence_score: 置信度评分
            
        Returns:
            是否成功记录
        """
        record = ExperienceRecord(
            task_type=task_type,
            task_aspect=task_aspect,
            skills_used=skills,
            success=success,
            approach=approach,
            duration_ms=duration_ms,
            confidence_score=confidence_score,
        )
        
        if not self._should_record(record):
            return False
        
        if self.wisdom_store:
            self._store_experience(record)
        
        self._total_recorded += 1
        if success:
            self._total_success += 1
        else:
            self._total_failed += 1
        
        return True
    
    def get_recommended_skills(
        self,
        task_type: str,
        task_aspect: str,
    ) -> List[str]:
        """
        获取推荐的Skills
        
        Args:
            task_type: 任务类型
            task_aspect: 任务维度
            
        Returns:
            推荐的Skills列表
        """
        if not self.wisdom_store:
            return []
        
        return self.wisdom_store.get_recommended_skills(
            task_type=task_type,
            task_aspect=task_aspect,
        )
    
    def get_best_practice(
        self,
        task_type: str,
        task_aspect: str,
    ) -> Dict[str, Any]:
        """
        获取最佳实践
        
        Args:
            task_type: 任务类型
            task_aspect: 任务维度
            
        Returns:
            最佳实践数据
        """
        if not self.wisdom_store:
            return {}
        
        return self.wisdom_store.get_best_practice(
            task_type=task_type,
            task_aspect=task_aspect,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_recorded": self._total_recorded,
            "total_success": self._total_success,
            "total_failed": self._total_failed,
            "success_rate": (
                self._total_success / self._total_recorded
                if self._total_recorded > 0 else 0
            ),
        }
