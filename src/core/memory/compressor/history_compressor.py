# -*- coding: utf-8 -*-
"""
历史压缩器

实现 Layer 2 工作上下文的差分存储和压缩策略：
- 保留最近5步完整记录
- 中间10-15步压缩为摘要
- 更早记录归档到 gzip 文件
"""

__all__ = ["HistoryCompressor"]

import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class HistoryCompressor:
    """
    历史压缩器
    
    核心功能：
    - 差分存储：最近历史完整保留，中间历史压缩摘要
    - 归档管理：超过阈值的历史自动归档
    - 大小控制：确保历史数据不超过预算
    
    压缩策略：
    - 最近 5 步：完整保留
    - 中间 10-15 步：压缩为摘要
    - 更早历史：归档到 gzip 文件
    
    参考：CONTEXT_COMPRESSION.md 第 2.2 节 Layer 2 设计
    """
    
    # 默认配置
    DEFAULT_FULL_STEPS = 5      # 保留完整记录的步数
    DEFAULT_SUMMARY_STEPS = 15  # 生成摘要的步数阈值
    DEFAULT_SIZE_LIMIT_KB = 50  # 大小限制 (KB)
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        max_full_steps: int = DEFAULT_FULL_STEPS,
        max_summary_steps: int = DEFAULT_SUMMARY_STEPS,
        size_limit_kb: int = DEFAULT_SIZE_LIMIT_KB,
        archive_path: Optional[str] = None
    ):
        """
        初始化历史压缩器
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            max_full_steps: 保留完整记录的最大步数
            max_summary_steps: 生成摘要的最大步数
            size_limit_kb: 大小限制 (KB)
            archive_path: 归档路径，默认为 data/users/{user_id}/archives/
        """
        self.user_id = user_id
        self.session_id = session_id
        self.max_full_steps = max_full_steps
        self.max_summary_steps = max_summary_steps
        self.size_limit_kb = size_limit_kb
        
        # 设置归档路径
        if archive_path is None:
            safe_user_id = user_id if user_id else "default"
            archive_path = f"data/users/{safe_user_id}/archives"
        self.archive_path = Path(archive_path)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        
        # 滚动摘要器（延迟加载）
        self._summarizer = None
        
        logger.info(
            f"HistoryCompressor initialized: "
            f"user={user_id}, session={session_id}, "
            f"full_steps={max_full_steps}, summary_steps={max_summary_steps}"
        )
    
    @property
    def summarizer(self):
        """延迟加载滚动摘要器"""
        if self._summarizer is None:
            from .rolling_summarizer import RollingSummarizer
            self._summarizer = RollingSummarizer()
        return self._summarizer
    
    # ========== 压缩接口 ==========
    
    def compress(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        压缩历史记录
        
        压缩策略：
        1. 如果历史 <= max_full_steps: 不压缩，完整保留
        2. 如果历史 <= max_summary_steps: 保留最近5步，中间压缩摘要
        3. 如果历史 > max_summary_steps: 保留最近5步，中间摘要，早期归档
        
        Args:
            history: 原始历史记录列表
            
        Returns:
            压缩结果，包含：
            - history: 压缩后的历史
            - archived: 是否触发归档
            - archive_path: 归档路径（如果归档）
            - compression_ratio: 压缩率
        """
        if not history:
            return {
                "history": [],
                "archived": False,
                "compression_ratio": 0.0
            }
        
        history_len = len(history)
        
        # 判断是否需要压缩
        if history_len <= self.max_full_steps:
            # 不需要压缩
            return {
                "history": history,
                "archived": False,
                "compression_ratio": 0.0
            }
        
        # 需要压缩：保留最近完整记录
        recent_full = history[-self.max_full_steps:]
        
        # 判断是否需要归档
        if history_len <= self.max_summary_steps:
            # 中间部分压缩为摘要，不归档
            middle_part = history[:-self.max_full_steps]
            middle_summary = self._create_summary(middle_part)
            
            compressed_history = [middle_summary] + recent_full
            
            compression_ratio = self._calculate_compression_ratio(
                history, compressed_history
            )
            
            return {
                "history": compressed_history,
                "archived": False,
                "compression_ratio": compression_ratio
            }
        
        # 需要归档
        # 中间部分：最近15步之前、最近5步之后
        middle_part = history[-self.max_summary_steps:-self.max_full_steps]
        middle_summary = self._create_summary(middle_part)
        
        # 早期部分：归档
        old_part = history[:-self.max_summary_steps]
        archive_path = self.archive_history(old_part)
        
        # 构建压缩后的历史
        compressed_history = [middle_summary] + recent_full
        
        compression_ratio = self._calculate_compression_ratio(
            history, compressed_history
        )
        
        logger.info(
            f"History compressed: {history_len} -> {len(compressed_history)} steps, "
            f"ratio={compression_ratio:.2%}, archived={len(old_part)} steps"
        )
        
        return {
            "history": compressed_history,
            "archived": True,
            "archive_path": str(archive_path),
            "compression_ratio": compression_ratio
        }
    
    def compress_if_needed(
        self, 
        history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        按需压缩历史（基于大小限制）
        
        如果历史大小超过限制，自动触发压缩
        
        Args:
            history: 原始历史
            
        Returns:
            压缩后的历史
        """
        if not self.is_within_limit(history):
            result = self.compress(history)
            return result["history"]
        return history
    
    # ========== 归档接口 ==========
    
    def archive_history(
        self, 
        history: List[Dict[str, Any]]
    ) -> Optional[Path]:
        """
        归档历史记录
        
        使用 gzip 压缩存储
        
        Args:
            history: 要归档的历史
            
        Returns:
            归档文件路径
        """
        if not history:
            return None
        
        # 生成归档文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f"history_{self.session_id}_{timestamp}.json.gz"
        archive_file = self.archive_path / archive_name
        
        try:
            # gzip 压缩存储
            with gzip.open(archive_file, 'wt', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False)
            
            logger.info(f"Archived {len(history)} steps to {archive_file}")
            return archive_file
            
        except Exception as e:
            logger.error(f"Failed to archive history: {e}")
            return None
    
    def restore_archive(self, archive_path: Path) -> Optional[List[Dict[str, Any]]]:
        """
        从归档恢复历史
        
        Args:
            archive_path: 归档文件路径
            
        Returns:
            恢复的历史记录
        """
        if not archive_path.exists():
            logger.warning(f"Archive file not found: {archive_path}")
            return None
        
        try:
            with gzip.open(archive_path, 'rt', encoding='utf-8') as f:
                history = json.load(f)
            
            logger.info(f"Restored {len(history)} steps from {archive_path}")
            return history
            
        except Exception as e:
            logger.error(f"Failed to restore archive: {e}")
            return None
    
    # ========== 大小计算 ==========
    
    def calculate_size(self, history: List[Dict[str, Any]]) -> float:
        """
        计算历史大小 (KB)
        
        Args:
            history: 历史记录
            
        Returns:
            大小 (KB)
        """
        if not history:
            return 0.0
        
        # JSON 序列化后计算大小
        json_str = json.dumps(history, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        size_kb = size_bytes / 1024
        
        return size_kb
    
    def is_within_limit(self, history: List[Dict[str, Any]]) -> bool:
        """
        检查历史是否在大小限制内
        
        Args:
            history: 历史记录
            
        Returns:
            是否在限制内
        """
        size_kb = self.calculate_size(history)
        return size_kb <= self.size_limit_kb
    
    # ========== 压缩率计算 ==========
    
    def compression_ratio(
        self, 
        original: List[Dict[str, Any]], 
        compressed: List[Dict[str, Any]]
    ) -> float:
        """
        计算压缩率
        
        Args:
            original: 原始历史
            compressed: 压缩后历史
            
        Returns:
            压缩率 (0.0 - 1.0)
        """
        original_size = self.calculate_size(original)
        compressed_size = self.calculate_size(compressed)
        
        if original_size == 0:
            return 0.0
        
        return 1.0 - (compressed_size / original_size)
    
    # ========== 私有方法 ==========
    
    def _create_summary(
        self, 
        history_part: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        创建历史摘要
        
        Args:
            history_part: 要摘要的历史部分
            
        Returns:
            摘要条目
        """
        if not history_part:
            return {
                "type": "summary",
                "content": "",
                "steps_covered": 0,
                "created_at": datetime.now().isoformat()
            }
        
        # 使用滚动摘要器生成摘要
        summary_text = self.summarizer.summarize(history_part)
        
        return {
            "type": "summary",
            "content": summary_text,
            "steps_covered": len(history_part),
            "step_range": {
                "start": history_part[0].get("step", 1),
                "end": history_part[-1].get("step", len(history_part))
            },
            "created_at": datetime.now().isoformat()
        }
    
    def _calculate_compression_ratio(
        self, 
        original: List[Dict[str, Any]], 
        compressed: List[Dict[str, Any]]
    ) -> float:
        """内部压缩率计算"""
        return self.compression_ratio(original, compressed)