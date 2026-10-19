# -*- coding: utf-8 -*-
"""
修订处理器
=========

统一处理文档修订操作，支持：
1. minor - 微调修订（格式、样式）
2. section - 章节修订（定位+替换）
3. phase - 阶段重做（重新执行某阶段）
4. full - 全部重做

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/PHASE8_DEVELOPMENT_PLAN.md
"""

import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .content_applier import ContentApplier, ApplyResult
from .revision_manager import RevisionManager, RevisionRecord
from .section_locator import SectionLocator, SectionLocation

logger = logging.getLogger(__name__)

# 常量定义
MAX_REVISION_ROUNDS = 10  # 最大修订轮次
VALID_REVISION_TYPES = ['minor', 'section', 'phase', 'full', 'add_section']


class RevisionStatus(str, Enum):
    """修订状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RevisionRequest:
    """修订请求"""
    task_id: str
    revision_type: str
    user_feedback: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    keywords: Optional[List[str]] = None
    target_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "revision_type": self.revision_type,
            "user_feedback": self.user_feedback,
            "section_id": self.section_id,
            "section_title": self.section_title,
            "keywords": self.keywords,
            "target_content": self.target_content,
            "metadata": self.metadata,
        }


@dataclass
class RevisionResult:
    """修订结果"""
    success: bool
    revision_id: Optional[str] = None
    revision_type: Optional[str] = None
    document_path: Optional[str] = None
    backup_path: Optional[str] = None
    section_id: Optional[str] = None
    changes: List[Dict[str, Any]] = field(default_factory=list)
    revision_count: int = 0
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "revision_id": self.revision_id,
            "revision_type": self.revision_type,
            "document_path": self.document_path,
            "backup_path": self.backup_path,
            "section_id": self.section_id,
            "changes": self.changes,
            "revision_count": self.revision_count,
            "error": self.error,
            "error_code": self.error_code,
        }


class RevisionHandler:
    """
    修订处理器
    
    统一处理各类文档修订，协调 SectionLocator 和 ContentApplier。
    
    使用示例：
        handler = RevisionHandler()
        
        # 章节修订
        result = handler.handle_revision(
            document_path="report.md",
            request=RevisionRequest(
                task_id="task_123",
                revision_type="section",
                section_title="市场规模",
                user_feedback="数据需要更新",
                target_content="新的内容...",
            )
        )
    """
    
    def __init__(
        self,
        revision_manager: Optional[RevisionManager] = None,
        section_locator: Optional[SectionLocator] = None,
        content_applier: Optional[ContentApplier] = None,
        history_dir: Optional[str] = None,
    ):
        """
        初始化修订处理器
        
        Args:
            revision_manager: 修订历史管理器
            section_locator: 章节定位器
            content_applier: 内容应用器
            history_dir: 历史记录存储目录
        """
        self.revision_manager = revision_manager or RevisionManager()
        self.section_locator = section_locator or SectionLocator()
        self.content_applier = content_applier or ContentApplier()
        
        self.history_dir = Path(history_dir) if history_dir else None
        if self.history_dir and not self.history_dir.exists():
            self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # 修订计数器（线程安全）
        self._revision_counts: Dict[str, int] = {}
        self._counts_lock = threading.Lock()
        
        # 阶段重做回调（由外部注入）
        self._phase_redo_callback: Optional[Callable] = None
        self._full_redo_callback: Optional[Callable] = None
    
    def set_phase_redo_callback(self, callback: Callable) -> None:
        """设置阶段重做回调"""
        self._phase_redo_callback = callback
    
    def set_full_redo_callback(self, callback: Callable) -> None:
        """设置全部重做回调"""
        self._full_redo_callback = callback
    
    def _generate_revision_id(self) -> str:
        """生成修订ID"""
        return f"rev_{uuid.uuid4().hex[:8]}"
    
    def _validate_revision_type(self, revision_type: str) -> bool:
        """验证修订类型"""
        return revision_type in VALID_REVISION_TYPES
    
    def _check_revision_limit(self, task_id: str) -> bool:
        """检查修订次数限制"""
        with self._counts_lock:
            count = self._revision_counts.get(task_id, 0)
            return count < MAX_REVISION_ROUNDS
    
    def _increment_revision_count(self, task_id: str) -> int:
        """增加修订计数"""
        with self._counts_lock:
            count = self._revision_counts.get(task_id, 0) + 1
            self._revision_counts[task_id] = count
            return count
    
    def get_revision_count(self, task_id: str) -> int:
        """获取修订计数"""
        with self._counts_lock:
            return self._revision_counts.get(task_id, 0)
    
    def reset_revision_count(self, task_id: str) -> None:
        """重置修订计数"""
        with self._counts_lock:
            self._revision_counts[task_id] = 0
    
    def handle_revision(
        self,
        document_path: str,
        request: RevisionRequest,
    ) -> RevisionResult:
        """
        处理修订请求
        
        Args:
            document_path: 文档路径
            request: 修订请求
            
        Returns:
            RevisionResult 修订结果
        """
        # 验证修订类型
        if not self._validate_revision_type(request.revision_type):
            logger.warning(f"Invalid revision type: {request.revision_type}")
            return RevisionResult(
                success=False,
                error=f"Invalid revision type: {request.revision_type}",
                error_code="INVALID_TYPE",
            )
        
        # 检查修订次数限制
        if not self._check_revision_limit(request.task_id):
            logger.warning(f"Revision limit reached for task: {request.task_id}")
            return RevisionResult(
                success=False,
                error=f"Maximum revision rounds ({MAX_REVISION_ROUNDS}) reached",
                error_code="LIMIT_EXCEEDED",
            )
        
        # 验证文档存在
        if not os.path.exists(document_path):
            logger.error(f"Document not found: {document_path}")
            return RevisionResult(
                success=False,
                error=f"Document not found: {document_path}",
                error_code="DOCUMENT_NOT_FOUND",
            )
        
        revision_id = self._generate_revision_id()
        
        try:
            # 根据修订类型分发处理
            if request.revision_type == "minor":
                result = self._handle_minor_revision(document_path, request, revision_id)
            elif request.revision_type == "section":
                result = self._handle_section_revision(document_path, request, revision_id)
            elif request.revision_type == "phase":
                result = self._handle_phase_revision(document_path, request, revision_id)
            elif request.revision_type == "full":
                result = self._handle_full_revision(document_path, request, revision_id)
            elif request.revision_type == "add_section":
                result = self._handle_add_section_revision(document_path, request, revision_id)
            else:
                result = RevisionResult(
                    success=False,
                    error=f"Unhandled revision type: {request.revision_type}",
                    error_code="UNHANDLED_TYPE",
                )
            
            # 记录修订历史
            if result.success:
                self._record_revision(document_path, request, result, revision_id)
                # full 类型已经在 _handle_full_revision 中重置了计数，不再增加
                if request.revision_type != "full":
                    result.revision_count = self._increment_revision_count(request.task_id)
                logger.info(
                    f"Revision completed: {revision_id} "
                    f"(task={request.task_id}, type={request.revision_type}, "
                    f"count={result.revision_count})"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Revision failed: {e}")
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error=str(e),
                error_code="REVISION_ERROR",
            )
    
    def _handle_minor_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        revision_id: str,
    ) -> RevisionResult:
        """
        处理微调修订
        
        微调修订通常不改变内容结构，只调整格式、样式等。
        当前实现为占位，实际需要与格式处理器配合。
        """
        logger.info(f"Handling minor revision: {revision_id}")
        
        # 微调修订通常是格式相关的，这里简化处理
        # 实际实现可能需要调用格式处理器
        
        return RevisionResult(
            success=True,
            revision_id=revision_id,
            revision_type="minor",
            document_path=document_path,
            changes=[{
                "type": "minor_adjustment",
                "feedback": request.user_feedback,
            }],
        )
    
    def _handle_section_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        revision_id: str,
    ) -> RevisionResult:
        """
        处理章节修订
        
        1. 定位目标章节
        2. 应用新内容
        3. 创建备份
        """
        logger.info(f"Handling section revision: {revision_id}")
        
        # 1. 定位章节
        section_location = self.section_locator.locate(
            document_path,
            section_id=request.section_id,
            section_title=request.section_title,
            keywords=request.keywords,
        )
        
        if not section_location:
            logger.warning(
                f"Section not found: id={request.section_id}, "
                f"title={request.section_title}"
            )
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error="Section not found",
                error_code="SECTION_NOT_FOUND",
            )
        
        # 2. 检查是否有目标内容
        if not request.target_content:
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error="target_content is required for section revision",
                error_code="MISSING_CONTENT",
            )
        
        # 3. 应用内容替换
        apply_result = self.content_applier.apply(
            document_path=document_path,
            location=section_location,
            new_content=request.target_content,
        )
        
        if not apply_result.success:
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error=apply_result.error,
                error_code="APPLY_FAILED",
            )
        
        return RevisionResult(
            success=True,
            revision_id=revision_id,
            revision_type="section",
            document_path=document_path,
            backup_path=apply_result.backup_path,
            section_id=section_location.section_id,
            changes=[{
                "type": "section_replace",
                "section_id": section_location.section_id,
                "section_title": section_location.section_title,
                "old_length": len(section_location.content) if section_location.content else 0,
                "new_length": len(request.target_content),
            }],
        )
    
    def _handle_phase_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        revision_id: str,
    ) -> RevisionResult:
        """
        处理阶段重做
        
        需要调用外部回调来重新执行特定阶段。
        """
        logger.info(f"Handling phase revision: {revision_id}")
        
        if not self._phase_redo_callback:
            logger.warning("Phase redo callback not set")
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error="Phase redo not supported - callback not configured",
                error_code="CALLBACK_NOT_SET",
            )
        
        # 调用阶段重做回调
        try:
            phase_id = request.metadata.get("phase_id")
            if not phase_id:
                return RevisionResult(
                    success=False,
                    revision_id=revision_id,
                    error="phase_id is required for phase revision",
                    error_code="MISSING_PHASE_ID",
                )
            
            # 执行回调
            callback_result = self._phase_redo_callback(
                task_id=request.task_id,
                phase_id=phase_id,
                user_feedback=request.user_feedback,
            )
            
            return RevisionResult(
                success=True,
                revision_id=revision_id,
                revision_type="phase",
                document_path=document_path,
                changes=[{
                    "type": "phase_redo",
                    "phase_id": phase_id,
                    "result": callback_result,
                }],
            )
            
        except Exception as e:
            logger.error(f"Phase redo failed: {e}")
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error=str(e),
                error_code="PHASE_REDO_ERROR",
            )
    
    def _handle_full_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        revision_id: str,
    ) -> RevisionResult:
        """
        处理全部重做
        
        需要调用外部回调来重新执行整个研究流程。
        """
        logger.info(f"Handling full revision: {revision_id}")
        
        if not self._full_redo_callback:
            logger.warning("Full redo callback not set")
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error="Full redo not supported - callback not configured",
                error_code="CALLBACK_NOT_SET",
            )
        
        try:
            # 执行回调
            callback_result = self._full_redo_callback(
                task_id=request.task_id,
                user_feedback=request.user_feedback,
            )
            
            # 重置修订计数（全部重做后重置）
            self.reset_revision_count(request.task_id)
            
            return RevisionResult(
                success=True,
                revision_id=revision_id,
                revision_type="full",
                document_path=document_path,
                changes=[{
                    "type": "full_redo",
                    "result": callback_result,
                }],
                revision_count=0,  # 全部重做后重置计数
            )
            
        except Exception as e:
            logger.error(f"Full redo failed: {e}")
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error=str(e),
                error_code="FULL_REDO_ERROR",
            )
    
    def _handle_add_section_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        revision_id: str,
    ) -> RevisionResult:
        """
        Handle add_section revision: insert a new section into the document.

        Uses ContentApplier.insert_section() to add the new section HTML,
        then rebuilds the TOC via ContentApplier.rebuild_toc().
        """
        logger.info(f"Handling add_section revision: {revision_id}")

        if not request.target_content:
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error="target_content is required for add_section revision",
                error_code="MISSING_CONTENT",
            )

        # Determine insertion point (after which existing section)
        after_section = request.metadata.get("after_section") if request.metadata else None
        insert_location = None
        if after_section:
            insert_location = self.section_locator.locate(
                document_path,
                section_title=after_section,
            )

        level = request.metadata.get("level", 2) if request.metadata else 2

        # Insert the new section
        apply_result = self.content_applier.insert_section(
            document_path=document_path,
            new_content=request.target_content,
            section_title=request.section_title or "",
            location=insert_location,
            level=level,
        )

        if not apply_result.success:
            return RevisionResult(
                success=False,
                revision_id=revision_id,
                error=apply_result.error or "Insert failed",
                error_code="INSERT_FAILED",
            )

        # Rebuild TOC
        new_doc_path = apply_result.new_document_path or document_path
        try:
            self.content_applier.rebuild_toc(new_doc_path)
        except Exception as e:
            logger.warning(f"TOC rebuild failed after add_section: {e}")

        return RevisionResult(
            success=True,
            revision_id=revision_id,
            revision_type="add_section",
            document_path=new_doc_path,
            backup_path=apply_result.backup_path,
            section_id=f"section_{request.section_title}" if request.section_title else None,
            changes=[{
                "type": "add_section",
                "section_title": request.section_title,
                "after_section": after_section,
            }],
        )

    def _record_revision(
        self,
        document_path: str,
        request: RevisionRequest,
        result: RevisionResult,
        revision_id: str,
    ) -> None:
        """记录修订历史"""
        try:
            self.revision_manager.create_revision(
                task_id=request.task_id,
                revision_type=request.revision_type,
                section=result.section_id,
                adjustment=request.user_feedback,
                document_path=document_path,
                revised_document_path=document_path,
                user_feedback=request.user_feedback,
            )
            logger.debug(f"Recorded revision: {revision_id}")
            
        except Exception as e:
            logger.warning(f"Failed to record revision: {e}")
    
    def get_revision_history(
        self,
        task_id: str,
    ) -> List[RevisionRecord]:
        """获取修订历史"""
        return self.revision_manager.get_revision_history(task_id)
    
    def rollback_revision(
        self,
        document_path: str,
        backup_path: str,
    ) -> bool:
        """
        回滚到备份版本
        
        Args:
            document_path: 当前文档路径
            backup_path: 备份文件路径
            
        Returns:
            是否成功
        """
        try:
            if not os.path.exists(backup_path):
                logger.error(f"Backup not found: {backup_path}")
                return False
            
            # 恢复备份
            import shutil
            shutil.copy(backup_path, document_path)
            logger.info(f"Rolled back to: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    def list_sections(
        self,
        document_path: str,
        level: Optional[int] = None,
    ) -> List[SectionLocation]:
        """
        列出文档章节
        
        便捷方法，代理到 SectionLocator
        """
        return self.section_locator.list_sections(document_path, level=level)
    
    def locate_section(
        self,
        document_path: str,
        section_id: Optional[str] = None,
        section_title: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Optional[SectionLocation]:
        """
        定位章节
        
        便捷方法，代理到 SectionLocator
        """
        return self.section_locator.locate(
            document_path,
            section_id=section_id,
            section_title=section_title,
            keywords=keywords,
        )


__all__ = [
    "RevisionStatus",
    "RevisionRequest",
    "RevisionResult",
    "RevisionHandler",
]
