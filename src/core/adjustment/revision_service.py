# -*- coding: utf-8 -*-
"""
修订服务
=======

统一修订入口，供多个场景调用：
1. 用户反馈修订（orchestrator）
2. 系统自检修订（QualityCheckAgent）

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/PHASE8_INTEGRATION_ANALYSIS.md
"""

import asyncio
import functools
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .revision_handler import (
    RevisionHandler,
    RevisionRequest,
    RevisionResult,
)
from .section_locator import SectionLocator, SectionLocation
from .content_applier import ContentApplier, ApplyResult
from .revision_manager import RevisionManager

logger = logging.getLogger(__name__)


@dataclass
class QualityIssue:
    """质量问题"""
    issue_type: str  # completeness, accuracy, consistency, format
    severity: str    # high, medium, low
    message: str
    section: Optional[str] = None
    suggestion: Optional[str] = None
    suggested_fix: Optional[str] = None


@dataclass
class RevisionContext:
    """修订上下文"""
    task_id: str
    document_path: str
    revision_type: str = "section"
    section: Optional[str] = None
    user_feedback: Optional[str] = None
    target_content: Optional[str] = None
    keywords: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RevisionService:
    """
    修订服务
    
    统一修订入口，协调 RevisionHandler、SectionLocator、ContentApplier。
    
    使用示例：
        service = RevisionService()
        
        # 用户反馈修订
        result = await service.revise_from_user_feedback(
            document_path="report.md",
            task_id="task_123",
            section="市场规模",
            adjustment="数据需要更新",
        )
        
        # 系统自检修订
        results = await service.revise_from_quality_check(
            document_path="report.md",
            task_id="task_123",
            issues=[...],
        )
    """
    
    def __init__(
        self,
        revision_manager: Optional[RevisionManager] = None,
        storage_path: Optional[str] = None,
    ):
        """
        初始化修订服务
        
        Args:
            revision_manager: 修订历史管理器
            storage_path: 存储路径
        """
        self.revision_manager = revision_manager
        self.storage_path = Path(storage_path) if storage_path else None
        
        # 初始化组件
        self.handler = RevisionHandler(
            revision_manager=revision_manager,
        )
        self.locator = SectionLocator()
        self.applier = ContentApplier(version_suffix=False)
        
        # 内容生成回调（用于需要生成新内容的场景）
        self._content_generator: Optional[Callable] = None
        self._data_collector: Optional[Callable] = None
        
        logger.info("RevisionService initialized")
    
    def set_content_generator(self, callback: Callable) -> None:
        """
        设置内容生成回调
        
        用于需要 LLM 生成新内容的场景
        """
        self._content_generator = callback
    
    def set_data_collector(self, callback: Callable) -> None:
        """
        设置数据收集回调
        
        用于需要重新调研数据的场景
        """
        self._data_collector = callback

    def _route_revision_intent(
        self,
        user_feedback: str,
        section: Optional[str],
        document_path: str,
    ) -> Dict[str, Any]:
        """
        Route revision intent based on keywords and section existence.

        Returns:
            dict with keys: action ("modify"|"add"|"full"), section, confidence
        """
        add_keywords = ["增加", "添加", "新增", "补充", "插入", "add", "insert", "new"]
        modify_keywords = ["修改", "更新", "修正", "改", "update", "modify", "rewrite"]

        is_add = any(k in user_feedback for k in add_keywords)
        is_modify = any(k in user_feedback for k in modify_keywords)

        section_exists = False
        if section:
            try:
                location = self.locator.locate(document_path, section_title=section)
                section_exists = location is not None
            except Exception:
                pass

        if is_add and not section_exists:
            return {"action": "add", "section": section, "confidence": "high"}
        elif is_modify and section_exists:
            return {"action": "modify", "section": section, "confidence": "high"}
        elif section_exists:
            return {"action": "modify", "section": section, "confidence": "medium"}
        elif section:
            return {"action": "add", "section": section, "confidence": "medium"}
        return {"action": "full", "section": None, "confidence": "low"}

    def _find_insertion_point(
        self,
        user_feedback: str,
        document_path: str,
    ) -> Optional[str]:
        """Find the semantic insertion point for a new section based on user feedback."""
        try:
            sections = self.locator.list_sections(document_path)
        except Exception:
            return None
        if not sections:
            return None

        feedback_lower = user_feedback.lower()
        for s in reversed(sections):
            if s.section_title.lower() in feedback_lower:
                return s.section_title
        return sections[-1].section_title

    async def revise_from_user_feedback(
        self,
        document_path: str,
        task_id: str,
        section: Optional[str] = None,
        adjustment: str = "",
        revision_type: str = "section",
        keywords: Optional[List[str]] = None,
        target_content: Optional[str] = None,
    ) -> RevisionResult:
        """
        用户反馈修订
        
        Args:
            document_path: 文档路径
            task_id: 任务ID
            section: 章节名称
            adjustment: 调整说明
            revision_type: 修订类型 (minor/section/phase/full)
            keywords: 关键词（用于定位章节）
            target_content: 目标内容（可选，如无则需生成）
            
        Returns:
            RevisionResult 修订结果
        """
        logger.info(
            f"User feedback revision: task={task_id}, "
            f"type={revision_type}, section={section}"
        )

        # Validate document existence
        if not os.path.exists(document_path):
            return RevisionResult(
                success=False,
                error=f"Document not found: {document_path}",
                error_code="DOCUMENT_NOT_FOUND",
            )

        # Route intent: determine if this is a modify, add, or full operation
        intent = self._route_revision_intent(adjustment, section, document_path)

        # Handle 'add' intent: insert new section
        if intent["action"] == "add" and revision_type in ("section", "add_section"):
            after_section = self._find_insertion_point(adjustment, document_path)

            if not target_content and self._content_generator:
                try:
                    target_content = await self._content_generator(
                        task_id=task_id,
                        section=section or "",
                        original_content="",
                        adjustment=adjustment,
                    )
                except Exception as e:
                    logger.error(f"Content generation for add_section failed: {e}")

            if not target_content:
                return RevisionResult(
                    success=False,
                    error="No target content provided or generated for new section",
                    error_code="NO_TARGET_CONTENT",
                )

            request = RevisionRequest(
                task_id=task_id,
                revision_type="add_section",
                section_title=section,
                user_feedback=adjustment,
                target_content=target_content,
                metadata={"after_section": after_section},
            )
            return await asyncio.to_thread(
                functools.partial(self.handler.handle_revision, document_path, request)
            )

        # Standard revision type dispatch
        if revision_type == "phase":
            return await self._handle_phase_revision(
                document_path, task_id, adjustment
            )
        elif revision_type == "full":
            return await self._handle_full_revision(
                document_path, task_id, adjustment
            )
        elif revision_type == "section":
            return await self._handle_section_revision(
                document_path, task_id, section, adjustment, keywords, target_content
            )
        elif revision_type == "minor":
            return await self._handle_minor_revision(
                document_path, task_id, adjustment
            )
        else:
            return RevisionResult(
                success=False,
                error=f"Unknown revision type: {revision_type}",
                error_code="INVALID_TYPE",
            )
    
    async def _handle_section_revision(
        self,
        document_path: str,
        task_id: str,
        section: Optional[str],
        adjustment: str,
        keywords: Optional[List[str]],
        target_content: Optional[str],
    ) -> RevisionResult:
        """处理章节修订"""
        
        # 1. 定位章节
        location = self.locator.locate(
            document_path,
            section_title=section,
            keywords=keywords,
        )
        
        if not location:
            logger.warning(f"Section not found: {section}")
            return RevisionResult(
                success=False,
                error=f"Section not found: {section}",
                error_code="SECTION_NOT_FOUND",
            )
        
        # 2. 如果没有目标内容，尝试生成
        if not target_content and self._content_generator:
            try:
                target_content = await self._content_generator(
                    task_id=task_id,
                    section=section or location.section_title,
                    original_content=location.content,
                    adjustment=adjustment,
                )
            except Exception as e:
                logger.error(f"Content generation failed: {e}")
                return RevisionResult(
                    success=False,
                    error=f"Content generation failed: {e}",
                    error_code="CONTENT_GENERATION_FAILED",
                )
        
        if not target_content:
            return RevisionResult(
                success=False,
                error="No target content provided or generated",
                error_code="NO_TARGET_CONTENT",
            )
        
        # 3. Execute revision (sync handler wrapped with asyncio.to_thread to avoid blocking)
        request = RevisionRequest(
            task_id=task_id,
            revision_type="section",
            section_title=location.section_title,
            user_feedback=adjustment,
            target_content=target_content,
        )
        
        return await asyncio.to_thread(
            functools.partial(self.handler.handle_revision, document_path, request)
        )
    
    async def _handle_minor_revision(
        self,
        document_path: str,
        task_id: str,
        adjustment: str,
    ) -> RevisionResult:
        """处理微调修订"""
        
        request = RevisionRequest(
            task_id=task_id,
            revision_type="minor",
            user_feedback=adjustment,
        )
        
        return await asyncio.to_thread(
            functools.partial(self.handler.handle_revision, document_path, request)
        )
    
    async def _handle_phase_revision(
        self,
        document_path: str,
        task_id: str,
        adjustment: str,
    ) -> RevisionResult:
        """处理阶段重做"""
        
        # 阶段重做需要外部回调
        if not self._data_collector:
            logger.warning("Data collector not set for phase revision")
            return RevisionResult(
                success=False,
                error="Phase revision requires data collector callback",
                error_code="CALLBACK_NOT_SET",
            )
        
        # 执行修订（使用 handler 的回调机制）
        request = RevisionRequest(
            task_id=task_id,
            revision_type="phase",
            user_feedback=adjustment,
            metadata={"phase_id": "data_collection"},  # 默认数据收集阶段
        )
        
        # 设置回调
        self.handler.set_phase_redo_callback(
            lambda task_id, phase_id, user_feedback: self._data_collector(
                task_id=task_id, phase_id=phase_id, feedback=user_feedback
            )
        )
        
        return await asyncio.to_thread(
            functools.partial(self.handler.handle_revision, document_path, request)
        )
    
    async def _handle_full_revision(
        self,
        document_path: str,
        task_id: str,
        adjustment: str,
    ) -> RevisionResult:
        """处理全部重做"""
        
        if not self._data_collector:
            logger.warning("Data collector not set for full revision")
            return RevisionResult(
                success=False,
                error="Full revision requires data collector callback",
                error_code="CALLBACK_NOT_SET",
            )
        
        request = RevisionRequest(
            task_id=task_id,
            revision_type="full",
            user_feedback=adjustment,
        )
        
        # 设置回调
        self.handler.set_full_redo_callback(
            lambda task_id, user_feedback: self._data_collector(
                task_id=task_id, feedback=user_feedback
            )
        )
        
        return await asyncio.to_thread(
            functools.partial(self.handler.handle_revision, document_path, request)
        )
    
    async def revise_from_quality_check(
        self,
        document_path: str,
        task_id: str,
        issues: List[Dict[str, Any]],
        suggestions: Optional[List[str]] = None,
        auto_fix: bool = True,
    ) -> List[RevisionResult]:
        """
        系统自检修订
        
        Args:
            document_path: 文档路径
            task_id: 任务ID
            issues: 质量问题列表
            suggestions: 改进建议
            auto_fix: 是否自动修复
            
        Returns:
            List[RevisionResult] 修订结果列表
        """
        logger.info(
            f"Quality check revision: task={task_id}, "
            f"issues={len(issues)}, auto_fix={auto_fix}"
        )
        
        # 验证文档存在
        if not os.path.exists(document_path):
            return [RevisionResult(
                success=False,
                error=f"Document not found: {document_path}",
                error_code="DOCUMENT_NOT_FOUND",
            )]
        
        if not auto_fix:
            logger.info("Auto fix disabled, returning empty results")
            return []
        
        results = []
        
        for issue in issues:
            issue_type = issue.get("type", "")
            severity = issue.get("severity", "medium")
            message = issue.get("message", "")
            section = issue.get("section")
            
            # 根据问题类型决定处理方式
            if issue_type == "completeness":
                # 完整性问题 - 需要补充内容
                result = await self._fix_completeness_issue(
                    document_path, task_id, issue
                )
                results.append(result)
                
            elif issue_type == "accuracy":
                # 准确性问题 - 需要重新调研
                result = await self._fix_accuracy_issue(
                    document_path, task_id, issue
                )
                results.append(result)
                
            elif issue_type == "consistency":
                # 一致性问题 - 可以直接修复
                result = await self._fix_consistency_issue(
                    document_path, task_id, issue
                )
                results.append(result)
                
            elif issue_type == "format":
                # 格式问题 - minor 修订
                result = await self._fix_format_issue(
                    document_path, task_id, issue
                )
                results.append(result)
            
            else:
                logger.warning(f"Unknown issue type: {issue_type}")
        
        return results
    
    async def _fix_completeness_issue(
        self,
        document_path: str,
        task_id: str,
        issue: Dict[str, Any],
    ) -> RevisionResult:
        """修复完整性问题"""
        
        message = issue.get("message", "")
        section = issue.get("section")
        
        # 从问题消息中提取关键词，用于章节定位
        keywords = self._extract_keywords_from_message(message)
        
        # 完整性问题通常需要补充内容
        # 如果有内容生成器，尝试生成
        if self._content_generator:
            try:
                target_content = await self._content_generator(
                    task_id=task_id,
                    section=section,
                    adjustment=message,
                )
                
                if target_content:
                    # 如果没有指定章节，尝试通过关键词定位
                    if not section and keywords:
                        logger.info(f"尝试通过关键词定位章节: {keywords}")
                        location = self.locator.locate(
                            document_path,
                            keywords=keywords,
                        )
                        if location:
                            section = location.section_title
                            logger.info(f"定位到章节: {section}")
                    
                    return await self.revise_from_user_feedback(
                        document_path=document_path,
                        task_id=task_id,
                        section=section,
                        adjustment=message,
                        revision_type="section",
                        target_content=target_content,
                        keywords=keywords if not section else None,
                    )
            except Exception as e:
                logger.error(f"Failed to generate content: {e}")
        
        # 无法自动修复
        return RevisionResult(
            success=False,
            error=f"Cannot auto-fix completeness issue: {message}",
            error_code="AUTO_FIX_NOT_SUPPORTED",
        )
    
    def _extract_keywords_from_message(self, message: str) -> List[str]:
        """从问题消息中提取关键词"""
        keywords = []
        
        # 常见章节关键词映射
        keyword_patterns = {
            "摘要": ["摘要", "概要", "总结"],
            "市场规模": ["市场规模", "市场总量", "规模"],
            "竞争格局": ["竞争", "竞争格局", "市场份额"],
            "产业链": ["产业链", "供应链", "价值链"],
            "发展趋势": ["趋势", "发展", "预测"],
            "政策环境": ["政策", "法规", "监管"],
            "技术": ["技术", "创新", "研发"],
            "风险": ["风险", "挑战", "问题"],
            "结论": ["结论", "建议", "展望"],
        }
        
        for keyword, patterns in keyword_patterns.items():
            if any(p in message for p in patterns):
                keywords.append(keyword)
        
        return keywords
    
    async def _fix_accuracy_issue(
        self,
        document_path: str,
        task_id: str,
        issue: Dict[str, Any],
    ) -> RevisionResult:
        """修复准确性问题"""
        
        message = issue.get("message", "")
        section = issue.get("section")
        
        # 准确性问题需要重新调研数据
        if self._data_collector:
            try:
                # 触发数据重新收集
                await self._data_collector(
                    task_id=task_id,
                    section=section,
                    reason=message,
                )
                
                # 返回成功（实际内容由数据收集器处理）
                return RevisionResult(
                    success=True,
                    revision_type="phase",
                    changes=[{
                        "type": "data_refresh",
                        "section": section,
                        "reason": message,
                    }],
                )
            except Exception as e:
                logger.error(f"Failed to collect data: {e}")
        
        return RevisionResult(
            success=False,
            error=f"Cannot auto-fix accuracy issue: {message}",
            error_code="AUTO_FIX_NOT_SUPPORTED",
        )
    
    async def _fix_consistency_issue(
        self,
        document_path: str,
        task_id: str,
        issue: Dict[str, Any],
    ) -> RevisionResult:
        """修复一致性问题"""
        
        message = issue.get("message", "")
        section = issue.get("section")
        
        # 一致性问题通常可以直接修复
        return await self.revise_from_user_feedback(
            document_path=document_path,
            task_id=task_id,
            section=section,
            adjustment=message,
            revision_type="minor",
        )
    
    async def _fix_format_issue(
        self,
        document_path: str,
        task_id: str,
        issue: Dict[str, Any],
    ) -> RevisionResult:
        """修复格式问题"""
        
        message = issue.get("message", "")
        
        # 格式问题使用 minor 修订
        return await self.revise_from_user_feedback(
            document_path=document_path,
            task_id=task_id,
            adjustment=message,
            revision_type="minor",
        )
    
    # ==================== 便捷方法 ====================
    
    def list_sections(
        self,
        document_path: str,
        level: Optional[int] = None,
    ) -> List[SectionLocation]:
        """列出文档章节"""
        return self.locator.list_sections(document_path, level=level)
    
    def locate_section(
        self,
        document_path: str,
        section_title: Optional[str] = None,
        section_id: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Optional[SectionLocation]:
        """定位章节"""
        return self.locator.locate(
            document_path,
            section_id=section_id,
            section_title=section_title,
            keywords=keywords,
        )
    
    def get_revision_count(self, task_id: str) -> int:
        """获取修订次数"""
        return self.handler.get_revision_count(task_id)
    
    def reset_revision_count(self, task_id: str) -> None:
        """重置修订次数"""
        self.handler.reset_revision_count(task_id)


__all__ = [
    "RevisionService",
    "RevisionContext",
    "QualityIssue",
]
