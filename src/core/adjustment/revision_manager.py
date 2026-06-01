# -*- coding: utf-8 -*-
"""
修订历史管理器
============

管理文档修订历史，支持：
1. 修订记录存储
2. 版本对比
3. 修订回滚
4. 多轮修订追踪

设计文档: docs/USER_INTERACTION_INTEGRATION_PLAN.md
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常量定义
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_REVISIONS_PER_TASK = 100  # 每个任务最大修订次数


@dataclass
class RevisionRecord:
    """修订记录"""
    revision_id: str
    task_id: str
    version_id: str
    revision_type: str  # "minor", "section", "phase", "full"
    section: Optional[str] = None
    adjustment: str = ""
    original_content: Optional[str] = None
    revised_content: Optional[str] = None
    document_path: Optional[str] = None
    revised_document_path: Optional[str] = None
    user_feedback: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "revision_id": self.revision_id,
            "task_id": self.task_id,
            "version_id": self.version_id,
            "revision_type": self.revision_type,
            "section": self.section,
            "adjustment": self.adjustment,
            "original_content": self.original_content,
            "revised_content": self.revised_content,
            "document_path": self.document_path,
            "revised_document_path": self.revised_document_path,
            "user_feedback": self.user_feedback,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RevisionRecord":
        """从字典创建"""
        return cls(
            revision_id=data.get("revision_id", ""),
            task_id=data.get("task_id", ""),
            version_id=data.get("version_id", ""),
            revision_type=data.get("revision_type", "minor"),
            section=data.get("section"),
            adjustment=data.get("adjustment", ""),
            original_content=data.get("original_content"),
            revised_content=data.get("revised_content"),
            document_path=data.get("document_path"),
            revised_document_path=data.get("revised_document_path"),
            user_feedback=data.get("user_feedback"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            created_by=data.get("created_by", "system"),
        )


@dataclass
class RevisionDiff:
    """修订差异"""
    revision_id: str
    section: str
    changes: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "revision_id": self.revision_id,
            "section": self.section,
            "changes": self.changes,
            "summary": self.summary,
        }


class RevisionManager:
    """
    修订历史管理器
    
    功能：
    1. 记录每次修订的详细信息
    2. 支持多轮修订追踪
    3. 版本对比与回滚
    4. 持久化存储
    
    使用示例：
        manager = RevisionManager(storage_path="data/revisions")
        
        # 记录修订
        record = manager.create_revision(
            task_id="research_xxx",
            revision_type="section",
            section="竞争格局",
            adjustment="补充宁德时代数据"
        )
        
        # 获取修订历史
        history = manager.get_revision_history(task_id="research_xxx")
        
        # 对比版本
        diff = manager.compare_revisions(revision_id_1, revision_id_2)
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化修订管理器
        
        Args:
            storage_path: 存储路径
        """
        self._storage_path = Path(storage_path) if storage_path else Path("data/revisions")
        
        try:
            self._storage_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Failed to create revisions directory: {e}") from e
        
        # 修订记录缓存
        self._revisions: Dict[str, RevisionRecord] = {}
        
        # 加载已有记录
        self._load_existing_revisions()
    
    def _load_existing_revisions(self) -> None:
        """加载已有的修订记录"""
        try:
            for file_path in self._storage_path.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        record = RevisionRecord.from_dict(data)
                        self._revisions[record.revision_id] = record
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to load revision file {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Failed to scan revisions directory: {e}")
    
    def _generate_revision_id(self) -> str:
        """生成修订ID"""
        return f"rev_{uuid.uuid4().hex[:8]}"
    
    def _is_valid_task_id(self, task_id: str) -> bool:
        """验证task_id"""
        return bool(TASK_ID_PATTERN.match(task_id))
    
    def _get_task_revision_count(self, task_id: str) -> int:
        """获取任务的修订次数"""
        return sum(1 for r in self._revisions.values() if r.task_id == task_id)
    
    def create_revision(
        self,
        task_id: str,
        revision_type: str,
        section: Optional[str] = None,
        adjustment: str = "",
        original_content: Optional[str] = None,
        revised_content: Optional[str] = None,
        document_path: Optional[str] = None,
        revised_document_path: Optional[str] = None,
        user_feedback: Optional[str] = None,
        created_by: str = "system",
    ) -> RevisionRecord:
        """
        创建修订记录
        
        Args:
            task_id: 任务ID
            revision_type: 修订类型（minor/section/phase/full）
            section: 章节名称（section类型时必需）
            adjustment: 调整说明
            original_content: 原始内容
            revised_content: 修订后内容
            document_path: 原文档路径
            revised_document_path: 修订后文档路径
            user_feedback: 用户反馈
            created_by: 创建者
            
        Returns:
            RevisionRecord 修订记录
        """
        # 验证task_id
        if not self._is_valid_task_id(task_id):
            raise ValueError(f"Invalid task_id: {task_id}")
        
        # 验证revision_type
        valid_types = ["minor", "section", "phase", "full", "rollback"]
        if revision_type not in valid_types:
            raise ValueError(f"Invalid revision_type: {revision_type}. Valid types: {valid_types}")
        
        # 检查修订次数限制
        current_count = self._get_task_revision_count(task_id)
        if current_count >= MAX_REVISIONS_PER_TASK:
            raise RuntimeError(f"Task {task_id} reached max revisions limit ({MAX_REVISIONS_PER_TASK})")
        
        # 生成版本ID（基于修订次数）
        version_id = f"v{current_count + 1}"
        
        # 创建记录
        revision_id = self._generate_revision_id()
        record = RevisionRecord(
            revision_id=revision_id,
            task_id=task_id,
            version_id=version_id,
            revision_type=revision_type,
            section=section,
            adjustment=adjustment,
            original_content=original_content,
            revised_content=revised_content,
            document_path=document_path,
            revised_document_path=revised_document_path,
            user_feedback=user_feedback,
            created_by=created_by,
        )
        
        # 保存到缓存和文件
        self._revisions[revision_id] = record
        self._save_revision(record)
        
        logger.info(f"Created revision: {revision_id} for task {task_id}")
        
        return record
    
    def _save_revision(self, record: RevisionRecord) -> None:
        """保存修订记录到文件"""
        file_path = self._storage_path / f"{record.revision_id}.json"
        
        try:
            # 使用原子写入
            temp_path = file_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
            
            # 重命名完成写入
            os.replace(temp_path, file_path)
        except OSError as e:
            logger.error(f"Failed to save revision {record.revision_id}: {e}")
            raise
    
    def get_revision(self, revision_id: str) -> Optional[RevisionRecord]:
        """
        获取指定修订记录
        
        Args:
            revision_id: 修订ID
            
        Returns:
            RevisionRecord 或 None
        """
        return self._revisions.get(revision_id)
    
    def get_revision_history(
        self,
        task_id: str,
        limit: int = 20,
    ) -> List[RevisionRecord]:
        """
        获取任务的修订历史
        
        Args:
            task_id: 任务ID
            limit: 最大返回数量
            
        Returns:
            修订记录列表（按时间倒序）
        """
        # 过滤并排序
        task_revisions = [
            r for r in self._revisions.values()
            if r.task_id == task_id
        ]
        
        # 按时间倒序
        task_revisions.sort(key=lambda r: r.created_at, reverse=True)
        
        return task_revisions[:limit]
    
    def get_latest_revision(self, task_id: str) -> Optional[RevisionRecord]:
        """
        获取任务最新的修订记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            最新修订记录或None
        """
        history = self.get_revision_history(task_id, limit=1)
        return history[0] if history else None
    
    def compare_revisions(
        self,
        revision_id_1: str,
        revision_id_2: str,
    ) -> RevisionDiff:
        """
        对比两个修订
        
        Args:
            revision_id_1: 第一个修订ID
            revision_id_2: 第二个修订ID
            
        Returns:
            RevisionDiff 差异结果
        """
        record_1 = self.get_revision(revision_id_1)
        record_2 = self.get_revision(revision_id_2)
        
        if not record_1 or not record_2:
            raise ValueError(f"Revision not found: {revision_id_1 if not record_1 else revision_id_2}")
        
        # 对比内容差异
        changes = []
        
        # 内容对比
        if record_1.original_content and record_2.revised_content:
            changes.append({
                "type": "content_change",
                "original": record_1.original_content[:500] if record_1.original_content else "",
                "revised": record_2.revised_content[:500] if record_2.revised_content else "",
            })
        
        # 章节对比
        if record_1.section != record_2.section:
            changes.append({
                "type": "section_change",
                "from": record_1.section,
                "to": record_2.section,
            })
        
        # 文档路径对比
        if record_1.document_path != record_2.document_path:
            changes.append({
                "type": "path_change",
                "from": record_1.document_path,
                "to": record_2.document_path,
            })
        
        # 生成摘要
        summary = f"对比 {revision_id_1} 和 {revision_id_2}: {len(changes)} 处差异"
        
        return RevisionDiff(
            revision_id=f"{revision_id_1}_vs_{revision_id_2}",
            section=record_1.section or record_2.section or "",
            changes=changes,
            summary=summary,
        )
    
    def rollback_to_revision(
        self,
        task_id: str,
        target_revision_id: str,
    ) -> RevisionRecord:
        """
        回滚到指定修订
        
        Args:
            task_id: 任务ID
            target_revision_id: 目标修订ID
            
        Returns:
            新的修订记录（标记为回滚）
        """
        target_record = self.get_revision(target_revision_id)
        
        if not target_record:
            raise ValueError(f"Target revision not found: {target_revision_id}")
        
        if target_record.task_id != task_id:
            raise ValueError(f"Revision {target_revision_id} does not belong to task {task_id}")
        
        # 创建回滚记录
        rollback_record = self.create_revision(
            task_id=task_id,
            revision_type="rollback",
            section=target_record.section,
            adjustment=f"回滚到 {target_revision_id}",
            document_path=target_record.revised_document_path,
            revised_document_path=target_record.document_path,
            user_feedback=f"用户请求回滚到版本 {target_record.version_id}",
            created_by="rollback",
        )
        
        logger.info(f"Rolled back task {task_id} to revision {target_revision_id}")
        
        return rollback_record
    
    def get_revision_stats(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务修订统计
        
        Args:
            task_id: 任务ID
            
        Returns:
            统计信息
        """
        history = self.get_revision_history(task_id, limit=MAX_REVISIONS_PER_TASK)
        
        # 统计各类型修订数量
        type_counts = {}
        for r in history:
            type_counts[r.revision_type] = type_counts.get(r.revision_type, 0) + 1
        
        return {
            "task_id": task_id,
            "total_revisions": len(history),
            "type_counts": type_counts,
            "latest_revision": history[0].revision_id if history else None,
            "first_revision": history[-1].revision_id if history else None,
        }
    
    def clear_task_revisions(self, task_id: str) -> int:
        """
        清理任务的修订记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            清理的记录数量
        """
        # 找到所有相关记录
        task_revisions = [
            r for r in self._revisions.values()
            if r.task_id == task_id
        ]
        
        # 删除文件和缓存
        count = 0
        for record in task_revisions:
            # 删除文件
            file_path = self._storage_path / f"{record.revision_id}.json"
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete revision file {file_path}: {e}")
            
            # 删除缓存
            del self._revisions[record.revision_id]
            count += 1
        
        logger.info(f"Cleared {count} revisions for task {task_id}")
        
        return count


# 导出
__all__ = ["RevisionRecord", "RevisionDiff", "RevisionManager"]