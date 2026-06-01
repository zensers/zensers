# -*- coding: utf-8 -*-
"""
研究结果存储模块
==================

提供研究结果的持久化存储功能：
1. 保存研究结果
2. 加载研究结果
3. 更新研究结果状态
4. 列出研究结果
5. 记录文档生成请求

存储结构:
data/results/{task_id}/
├── result.json          # 研究结果内容
└── metadata.json        # 元数据（状态、格式等）
"""

import os
import re
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# task_id 验证正则：仅允许字母、数字、下划线、连字符
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


class ResearchStatus(Enum):
    """研究结果状态"""
    IN_PROGRESS = "in_progress"                 # 研究中（replan/reanalyze 中间状态）
    ANALYZING = "analyzing"                     # 需求分析中
    COLLECTING = "collecting"                   # 数据收集中
    REPORTING = "reporting"                     # 报告生成中
    COMPLETED = "completed"                     # 研究完成（可生成文档）
    DOCUMENT_PENDING = "document_pending"       # 文档待生成
    DOCUMENT_GENERATED = "document_generated"   # 文档已生成


class ResearchResultError(Exception):
    """研究结果操作异常基类"""
    pass


class ResearchResultNotFoundError(ResearchResultError):
    """研究结果不存在"""
    pass


class InvalidTaskIdError(ResearchResultError):
    """无效的任务ID"""
    pass


@dataclass
class ResearchResultMeta:
    """研究结果元数据"""
    task_id: str
    title: str
    topic: str
    status: ResearchStatus
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 文档生成相关
    output_format: Optional[str] = None              # 首次指定的格式
    generated_formats: List[str] = field(default_factory=list)  # 已生成的格式列表
    document_requests: List[Dict] = field(default_factory=list)  # 文档生成请求历史
    document_paths: List[str] = field(default_factory=list)  # 生成的文档路径列表
    
    # 用户信息
    user_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "topic": self.topic,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output_format": self.output_format,
            "generated_formats": self.generated_formats,
            "document_requests": self.document_requests,
            "document_paths": self.document_paths,
            "user_id": self.user_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchResultMeta":
        """从字典创建"""
        # 验证必需字段
        required_fields = ["task_id", "title", "topic", "status"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(f"Missing required field: {field_name}")
        
        # 验证 status 值
        try:
            status = ResearchStatus(data["status"])
        except ValueError as e:
            raise ValueError(f"Invalid status value: {data['status']}") from e
        
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            topic=data["topic"],
            status=status,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            output_format=data.get("output_format"),
            generated_formats=data.get("generated_formats", []),
            document_requests=data.get("document_requests", []),
            document_paths=data.get("document_paths", []),
            user_id=data.get("user_id")
        )


class ResearchResultStore:
    """
    研究结果存储器
    
    提供研究结果的持久化存储和管理功能。
    
    使用示例:
        store = ResearchResultStore("data")
        
        # 保存研究结果
        result_id = store.save_result(
            task_id="research_xxx",
            result={"title": "...", "sections": [...]},
            status=ResearchStatus.COMPLETED
        )
        
        # 加载研究结果
        result = store.load_result("research_xxx")
        
        # 更新状态
        store.update_result(
            task_id="research_xxx",
            status=ResearchStatus.DOCUMENT_GENERATED,
            generated_format="docx"
        )
    """
    
    def __init__(self, storage_path: str):
        """
        初始化存储器
        
        Args:
            storage_path: 存储根目录路径
        """
        self.storage_path = Path(storage_path)
        self.results_dir = self.storage_path / "results"
        
        # 确保目录存在
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ResearchResultStore initialized at {self.results_dir}")
    
    def _validate_task_id(self, task_id: str) -> None:
        """
        验证任务ID是否有效
        
        Args:
            task_id: 任务ID
            
        Raises:
            InvalidTaskIdError: 如果任务ID无效
        """
        if not task_id:
            raise InvalidTaskIdError("task_id cannot be empty")
        
        if not TASK_ID_PATTERN.match(task_id):
            raise InvalidTaskIdError(
                f"Invalid task_id: '{task_id}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )
    
    def _get_task_dir(self, task_id: str) -> Path:
        """
        获取任务目录路径，并进行安全验证
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务目录路径
            
        Raises:
            InvalidTaskIdError: 如果路径遍历检测到
        """
        self._validate_task_id(task_id)
        
        task_dir = self.results_dir / task_id
        
        # 验证路径安全：确保解析后的路径仍在 results_dir 内
        real_task_dir = task_dir.resolve()
        real_results_dir = self.results_dir.resolve()
        
        if not str(real_task_dir).startswith(str(real_results_dir)):
            raise InvalidTaskIdError(
                f"Path traversal detected in task_id: '{task_id}'"
            )
        
        return task_dir
    
    def _atomic_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """
        原子写入JSON文件
        
        使用临时文件+原子替换确保写入安全性
        
        Args:
            path: 目标文件路径
            data: 要写入的数据
        """
        # 在同一目录下创建临时文件
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            suffix='.tmp',
            prefix='.tmp_'
        )
        
        try:
            # 写入临时文件
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 原子替换
            os.replace(temp_path, path)
            
        except Exception:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    def save_result(
        self,
        task_id: str,
        result: Dict[str, Any],
        status: ResearchStatus = ResearchStatus.COMPLETED,
        user_id: Optional[str] = None
    ) -> str:
        """
        保存研究结果
        
        Args:
            task_id: 任务ID
            result: 研究结果内容
            status: 研究状态
            user_id: 用户ID（可选）
            
        Returns:
            任务ID
            
        Raises:
            InvalidTaskIdError: 如果任务ID无效
        """
        # 创建任务目录（已包含安全验证）
        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存研究结果内容
        result_path = task_dir / "result.json"
        result_data = {
            "task_id": task_id,
            "title": result.get("title", ""),
            "topic": result.get("topic", ""),
            "sections": result.get("sections", []),
            "key_findings": result.get("key_findings", []),
            "data_points": result.get("data_points", []),
            "sources": result.get("sources", []),       # A-1/A-2修复：持久化数据来源
            "completed_agents": result.get("completed_agents", []),  # resume: agent完成状态追踪
            "saved_at": datetime.now().isoformat()
        }
        
        self._atomic_write_json(result_path, result_data)
        
        # 保存元数据
        metadata = ResearchResultMeta(
            task_id=task_id,
            title=result.get("title", ""),
            topic=result.get("topic", ""),
            status=status,
            created_at=datetime.now(),
            completed_at=datetime.now() if status == ResearchStatus.COMPLETED else None,
            user_id=user_id
        )
        
        self._save_metadata(task_id, metadata)
        
        logger.info(f"Saved research result: {task_id}, status: {status.value}")
        
        return task_id
    
    def load_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载研究结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            研究结果内容，如果不存在则返回 None
        """
        try:
            task_dir = self._get_task_dir(task_id)
            result_path = task_dir / "result.json"
            
            if not result_path.exists():
                return None
            
            with open(result_path, "r", encoding="utf-8") as f:
                return json.load(f)
                
        except (InvalidTaskIdError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load result for task {task_id}: {e}")
            return None
    
    def load_metadata(self, task_id: str) -> Optional[ResearchResultMeta]:
        """
        加载研究结果元数据
        
        Args:
            task_id: 任务ID
            
        Returns:
            元数据对象，如果不存在则返回 None
        """
        try:
            task_dir = self._get_task_dir(task_id)
            metadata_path = task_dir / "metadata.json"
            
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return ResearchResultMeta.from_dict(data)
            
        except (InvalidTaskIdError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load metadata for task {task_id}: {e}")
            return None
    
    def update_result(
        self,
        task_id: str,
        status: Optional[ResearchStatus] = None,
        generated_format: Optional[str] = None,
        document_path: Optional[str] = None
    ) -> None:
        """
        更新研究结果状态
        
        Args:
            task_id: 任务ID
            status: 新状态（可选）
            generated_format: 生成的格式（可选）
            document_path: 文档路径（可选）
            
        Raises:
            ResearchResultNotFoundError: 如果研究结果不存在
            InvalidTaskIdError: 如果任务ID无效
        """
        metadata = self.load_metadata(task_id)
        
        if metadata is None:
            raise ResearchResultNotFoundError(f"Research result not found: {task_id}")
        
        # 更新状态
        if status:
            metadata.status = status
        
        # 添加生成的格式
        if generated_format and generated_format not in metadata.generated_formats:
            metadata.generated_formats.append(generated_format)
        
        # 添加文档路径
        if document_path and document_path not in metadata.document_paths:
            metadata.document_paths.append(document_path)
        
        # 保存更新后的元数据
        self._save_metadata(task_id, metadata)
        
        logger.info(f"Updated research result: {task_id}, status: {metadata.status.value}")
    
    def record_document_request(
        self,
        task_id: str,
        request: Dict[str, Any]
    ) -> None:
        """
        记录文档生成请求
        
        Args:
            task_id: 任务ID
            request: 请求信息
            
        Raises:
            ResearchResultNotFoundError: 如果研究结果不存在
            InvalidTaskIdError: 如果任务ID无效
        """
        metadata = self.load_metadata(task_id)
        
        if metadata is None:
            raise ResearchResultNotFoundError(f"Research result not found: {task_id}")
        
        # 添加请求记录
        metadata.document_requests.append(request)
        
        # 保存更新后的元数据
        self._save_metadata(task_id, metadata)
        
        logger.info(f"Recorded document request for: {task_id}, format: {request.get('output_format')}")
    
    def list_results(
        self,
        status: Optional[ResearchStatus] = None,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[ResearchResultMeta]:
        """
        列出研究结果
        
        Args:
            status: 过滤状态（可选）
            user_id: 过滤用户ID（可选）
            limit: 返回数量限制
            
        Returns:
            元数据列表
        """
        results = []
        
        # 遍历所有任务目录
        if not self.results_dir.exists():
            return results
        
        for task_dir in self.results_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            metadata_path = task_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                metadata = ResearchResultMeta.from_dict(data)
                
                # 过滤
                if status and metadata.status != status:
                    continue
                
                if user_id and metadata.user_id != user_id:
                    continue
                
                results.append(metadata)
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
                continue
            
            # 限制数量
            if len(results) >= limit:
                break
        
        # 按完成时间倒序排序
        results.sort(
            key=lambda x: x.completed_at or datetime.min,
            reverse=True
        )
        
        return results[:limit]
    
    def result_exists(self, task_id: str) -> bool:
        """
        检查研究结果是否存在
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否存在
        """
        try:
            task_dir = self._get_task_dir(task_id)
            result_path = task_dir / "result.json"
            return result_path.exists()
        except InvalidTaskIdError:
            return False
    
    def delete_result(self, task_id: str) -> bool:
        """
        删除研究结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功删除
        """
        try:
            task_dir = self._get_task_dir(task_id)
            
            if not task_dir.exists():
                return False
            
            shutil.rmtree(task_dir)
            
            logger.info(f"Deleted research result: {task_id}")
            
            return True
            
        except InvalidTaskIdError:
            return False
    
    def _save_metadata(self, task_id: str, metadata: ResearchResultMeta) -> None:
        """
        保存元数据到文件
        
        Args:
            task_id: 任务ID
            metadata: 元数据对象
        """
        task_dir = self._get_task_dir(task_id)
        metadata_path = task_dir / "metadata.json"
        
        self._atomic_write_json(metadata_path, metadata.to_dict())
