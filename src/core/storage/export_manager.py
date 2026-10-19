# -*- coding: utf-8 -*-
"""
文档导出管理器
============

提供文档导出功能：
1. 导出文档到指定位置
2. 记录导出历史
3. 列出导出记录
4. 导出路径验证

存储结构:
data/exports/
├── exports_index.json        # 全局导出索引
└── {task_id}/
    └── export_history.json   # 任务导出历史
"""

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常量定义
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
VERSION_ID_PATTERN = re.compile(r'^v[0-9]+$')  # v1, v2, v3...
VALID_FORMATS = ['docx', 'pptx', 'pdf', 'html']
MAX_EXPORT_PATH_LENGTH = 500  # 最大导出路径长度
MAX_EXPORT_HISTORY = 1000  # 最大导出历史记录数


class ExportError(Exception):
    """导出操作异常"""
    pass


@dataclass
class ExportRecord:
    """导出记录"""
    export_id: str
    task_id: str
    version_id: str
    format: str
    source_path: str
    export_path: str
    file_size: int
    exported_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "export_id": self.export_id,
            "task_id": self.task_id,
            "version_id": self.version_id,
            "format": self.format,
            "source_path": self.source_path,
            "export_path": self.export_path,
            "file_size": self.file_size,
            "exported_at": self.exported_at.isoformat(),
            "metadata": self.metadata,
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExportRecord":
        """从字典创建"""
        return cls(
            export_id=data.get("export_id", ""),
            task_id=data.get("task_id", ""),
            version_id=data.get("version_id", ""),
            format=data.get("format", ""),
            source_path=data.get("source_path", ""),
            export_path=data.get("export_path", ""),
            file_size=data.get("file_size", 0),
            exported_at=datetime.fromisoformat(data.get("exported_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {}),
            checksum=data.get("checksum")
        )


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    export_id: Optional[str] = None
    export_path: Optional[str] = None
    file_size: Optional[int] = None
    exported_at: Optional[datetime] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "export_id": self.export_id,
            "export_path": self.export_path,
            "file_size": self.file_size,
            "exported_at": self.exported_at.isoformat() if self.exported_at else None,
            "error": self.error,
            "error_code": self.error_code
        }


class ExportManager:
    """
    文档导出管理器
    
    管理文档的导出操作和导出历史。
    
    使用示例：
        manager = ExportManager(storage_dir="data/exports")
        
        # 导出文档
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path="/path/to/source.docx",
            export_path="D:/Reports/output.docx"
        )
        
        # 列出导出历史
        exports = manager.list_exports("research_001")
    """
    
    def __init__(self, storage_dir: str = "data/exports"):
        """
        初始化导出管理器
        
        Args:
            storage_dir: 导出记录存储目录
        """
        self.storage_dir = Path(storage_dir)
        
        # 创建存储目录
        if not self.storage_dir.exists():
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created export storage directory: {self.storage_dir}")
    
    def _is_valid_task_id(self, task_id: str) -> bool:
        """验证task_id格式"""
        return bool(TASK_ID_PATTERN.match(task_id))
    
    def _is_valid_version_id(self, version_id: str) -> bool:
        """验证version_id格式"""
        return bool(VERSION_ID_PATTERN.match(version_id))
    
    def _is_valid_format(self, format: str) -> bool:
        """验证格式"""
        return format in VALID_FORMATS
    
    def _is_safe_path(self, path: str) -> bool:
        """
        验证路径安全性
        
        Args:
            path: 文件路径
            
        Returns:
            是否安全
        """
        if '..' in path:
            return False
        try:
            Path(path).resolve()
            return True
        except (OSError, ValueError):
            return False
    
    def _is_safe_export_path(self, export_path: str) -> bool:
        """
        验证导出路径安全性
        
        Args:
            export_path: 导出路径
            
        Returns:
            是否安全
        """
        # 检查路径长度
        if len(export_path) > MAX_EXPORT_PATH_LENGTH:
            return False
        
        # 检查路径遍历
        if '..' in export_path:
            return False
        
        # 检查危险路径
        dangerous_paths = ['/etc', '/root', '/sys', '/proc', 'C:\\Windows', 'C:\\System']
        for dp in dangerous_paths:
            if export_path.startswith(dp):
                return False
        
        # 检查路径解析
        try:
            Path(export_path).resolve()
            return True
        except (OSError, ValueError):
            return False
    
    def _get_task_export_dir(self, task_id: str) -> Path:
        """获取任务导出目录"""
        return self.storage_dir / task_id
    
    def _get_export_history_file(self, task_id: str) -> Path:
        """获取导出历史文件路径"""
        return self._get_task_export_dir(task_id) / "export_history.json"
    
    def _load_export_history(self, task_id: str) -> List[ExportRecord]:
        """加载导出历史"""
        history_file = self._get_export_history_file(task_id)
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [ExportRecord.from_dict(r) for r in data.get("exports", [])]
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load export history: {e}")
                return []
        
        return []
    
    def _save_export_history(self, task_id: str, records: List[ExportRecord]) -> None:
        """保存导出历史"""
        task_dir = self._get_task_export_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        history_file = self._get_export_history_file(task_id)
        
        data = {
            "task_id": task_id,
            "exports": [r.to_dict() for r in records],
            "updated_at": datetime.now().isoformat()
        }
        
        # 原子写入
        fd, temp_path = tempfile.mkstemp(suffix='.json', dir=str(task_dir))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, history_file)
        except (OSError, IOError):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    
    def _generate_export_id(self) -> str:
        """生成导出ID"""
        return f"export_{uuid.uuid4().hex[:8]}"
    
    def export_document(
        self,
        task_id: str,
        version_id: str,
        format: str,
        source_path: str,
        export_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExportResult:
        """
        导出文档到指定位置
        
        Args:
            task_id: 任务ID
            version_id: 版本ID
            format: 文档格式
            source_path: 源文件路径
            export_path: 导出目标路径
            metadata: 导出元数据
            
        Returns:
            ExportResult 导出结果
        """
        # 验证task_id
        if not self._is_valid_task_id(task_id):
            logger.warning(f"Invalid task_id: {task_id}")
            return ExportResult(
                success=False,
                error="Invalid task_id format",
                error_code="INVALID_TASK_ID"
            )
        
        # 验证version_id
        if not self._is_valid_version_id(version_id):
            logger.warning(f"Invalid version_id: {version_id}")
            return ExportResult(
                success=False,
                error="Invalid version_id format",
                error_code="INVALID_VERSION_ID"
            )
        
        # 验证格式
        if not self._is_valid_format(format):
            logger.warning(f"Invalid format: {format}")
            return ExportResult(
                success=False,
                error=f"Invalid format: {format}",
                error_code="INVALID_FORMAT"
            )
        
        # 验证导出路径
        if not self._is_safe_export_path(export_path):
            logger.warning(f"Unsafe export path: {export_path}")
            return ExportResult(
                success=False,
                error="Unsafe export path",
                error_code="UNSAFE_EXPORT_PATH"
            )
        
        # 验证源文件路径安全
        if not self._is_safe_path(source_path):
            logger.warning(f"Unsafe source path: {source_path}")
            return ExportResult(
                success=False,
                error="Unsafe source path",
                error_code="UNSAFE_SOURCE_PATH"
            )
        
        # 验证源文件存在
        if not os.path.exists(source_path):
            logger.warning(f"Source file not found: {source_path}")
            return ExportResult(
                success=False,
                error="Source file not found",
                error_code="SOURCE_NOT_FOUND"
            )
        
        try:
            # 创建导出目录
            export_dir = os.path.dirname(export_path)
            if export_dir and not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)
            
            # 复制文件
            shutil.copy2(source_path, export_path)
            
            # 获取文件大小
            file_size = os.path.getsize(export_path)
            
            # 生成导出ID
            export_id = self._generate_export_id()
            exported_at = datetime.now()
            
            # 创建导出记录
            record = ExportRecord(
                export_id=export_id,
                task_id=task_id,
                version_id=version_id,
                format=format,
                source_path=source_path,
                export_path=export_path,
                file_size=file_size,
                exported_at=exported_at,
                metadata=metadata or {}
            )
            
            # 加载历史并添加记录
            history = self._load_export_history(task_id)
            history.append(record)
            self._save_export_history(task_id, history)
            
            logger.info(f"Exported document: {export_path}, size={file_size}")
            
            return ExportResult(
                success=True,
                export_id=export_id,
                export_path=export_path,
                file_size=file_size,
                exported_at=exported_at
            )
            
        except (OSError, IOError, shutil.Error) as e:
            logger.error(f"Export failed: {e}")
            return ExportResult(
                success=False,
                error=f"File operation failed: {e}",
                error_code="FILE_ERROR"
            )
    
    def list_exports(
        self,
        task_id: str,
        format: Optional[str] = None,
        limit: int = 100
    ) -> List[ExportRecord]:
        """
        列出导出历史
        
        Args:
            task_id: 任务ID
            format: 格式过滤（可选）
            limit: 最大返回数量（1-1000）
            
        Returns:
            导出记录列表
        """
        if not self._is_valid_task_id(task_id):
            return []
        
        # 验证limit范围
        limit = max(1, min(limit, MAX_EXPORT_HISTORY))
        
        records = self._load_export_history(task_id)
        
        # 格式过滤
        if format and self._is_valid_format(format):
            records = [r for r in records if r.format == format]
        
        # 限制数量（按时间倒序）
        records = sorted(records, key=lambda r: r.exported_at, reverse=True)
        
        return records[:limit]
    
    def get_export(self, export_id: str) -> Optional[ExportRecord]:
        """
        获取特定导出记录
        
        Args:
            export_id: 导出ID
            
        Returns:
            ExportRecord 或 None
        """
        # 搜索所有任务的导出历史
        for task_dir in self.storage_dir.iterdir():
            if task_dir.is_dir() and TASK_ID_PATTERN.match(task_dir.name):
                records = self._load_export_history(task_dir.name)
                for r in records:
                    if r.export_id == export_id:
                        return r
        
        return None
    
    def delete_export_record(
        self,
        task_id: str,
        export_id: str
    ) -> bool:
        """
        删除导出记录（不删除文件）
        
        Args:
            task_id: 任务ID
            export_id: 导出ID
            
        Returns:
            是否成功
        """
        records = self._load_export_history(task_id)
        
        new_records = [r for r in records if r.export_id != export_id]
        
        if len(new_records) == len(records):
            return False  # 记录不存在
        
        self._save_export_history(task_id, new_records)
        
        logger.info(f"Deleted export record: {export_id}")
        
        return True
    
    def get_export_stats(self, task_id: str) -> Dict[str, Any]:
        """
        获取导出统计
        
        Args:
            task_id: 任务ID
            
        Returns:
            统计信息
        """
        records = self._load_export_history(task_id)
        
        if not records:
            return {
                "total_exports": 0,
                "total_size": 0,
                "formats": {}
            }
        
        format_counts = {}
        total_size = 0
        
        for r in records:
            format_counts[r.format] = format_counts.get(r.format, 0) + 1
            total_size += r.file_size
        
        return {
            "total_exports": len(records),
            "total_size": total_size,
            "formats": format_counts,
            "first_export": records[0].exported_at.isoformat() if records else None,
            "last_export": records[-1].exported_at.isoformat() if records else None
        }


# 导出
__all__ = ["ExportManager", "ExportRecord", "ExportResult", "ExportError"]