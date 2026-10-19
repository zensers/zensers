# -*- coding: utf-8 -*-
"""
文档版本管理器
============

提供文档版本控制功能：
1. 创建版本记录
2. 列出历史版本
3. 获取特定版本
4. 版本对比
5. 版本回滚

存储结构:
data/versions/{task_id}/{format}/
├── versions.json         # 版本列表
└── v1/
│   ├── metadata.json     # 版本元数据
│   └── document.docx     # 文档文件（可选存储）
└── v2/
    └── ...
"""

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 常量定义
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
VALID_FORMATS = ['docx', 'pptx', 'pdf', 'html']
VALID_CREATED_BY = ['initial', 'regenerate', 'adjustment', 'rollback', 'interim', 'final']
MAX_VERSIONS = 100  # 最大版本数限制
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB - 单文件最大大小


class VersionError(Exception):
    """版本操作异常"""
    pass


@dataclass
class VersionInfo:
    """版本信息（简化版，用于内部）"""
    version_id: str
    format: str
    file_path: str
    file_size: int
    created_at: datetime
    created_by: str
    template: Optional[str] = None
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    parent_version: Optional[str] = None
    change_summary: str = ""
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version_id": self.version_id,
            "format": self.format,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "template": self.template,
            "adjustments": self.adjustments,
            "parent_version": self.parent_version,
            "change_summary": self.change_summary,
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionInfo":
        """从字典创建"""
        return cls(
            version_id=data.get("version_id", ""),
            format=data.get("format", ""),
            file_path=data.get("file_path", ""),
            file_size=data.get("file_size", 0),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            created_by=data.get("created_by", ""),
            template=data.get("template"),
            adjustments=data.get("adjustments", []),
            parent_version=data.get("parent_version"),
            change_summary=data.get("change_summary", ""),
            checksum=data.get("checksum")
        )


class DocumentVersionManager:
    """
    文档版本管理器
    
    管理文档的版本历史，支持创建、查询、对比、回滚。
    
    使用示例：
        manager = DocumentVersionManager(storage_dir="data/versions")
        
        # 创建版本
        version = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/document.docx",
            file_size=10240,
            created_by="initial"
        )
        
        # 列出版本
        versions = manager.list_versions("research_001", "docx")
        
        # 回滚
        new_version = manager.rollback_to_version(
            task_id="research_001",
            format="docx",
            target_version_id="v1"
        )
    """
    
    def __init__(self, storage_dir: str = "data/versions"):
        """
        初始化版本管理器
        
        Args:
            storage_dir: 版本存储目录
        """
        self.storage_dir = Path(storage_dir)
        
        # 创建存储目录
        if not self.storage_dir.exists():
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created version storage directory: {self.storage_dir}")
        
        # 版本缓存: key="task_id:format" -> List[VersionInfo]
        self._cache: Dict[str, List[VersionInfo]] = {}
    
    def _is_valid_task_id(self, task_id: str) -> bool:
        """验证task_id格式"""
        return bool(TASK_ID_PATTERN.match(task_id))
    
    def _is_valid_format(self, format: str) -> bool:
        """验证格式"""
        return format in VALID_FORMATS
    
    def _get_version_dir(self, task_id: str, format: str) -> Path:
        """获取版本目录路径"""
        return self.storage_dir / task_id / format
    
    def _get_versions_file(self, task_id: str, format: str) -> Path:
        """获取版本列表文件路径"""
        return self._get_version_dir(task_id, format) / "versions.json"
    
    def _load_versions(self, task_id: str, format: str) -> List[VersionInfo]:
        """加载版本列表"""
        versions_file = self._get_versions_file(task_id, format)
        
        if versions_file.exists():
            try:
                with open(versions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [VersionInfo.from_dict(v) for v in data.get("versions", [])]
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load versions: {e}")
                return []
        
        return []
    
    def _save_versions(self, task_id: str, format: str, versions: List[VersionInfo]) -> None:
        """保存版本列表"""
        version_dir = self._get_version_dir(task_id, format)
        version_dir.mkdir(parents=True, exist_ok=True)
        
        versions_file = self._get_versions_file(task_id, format)
        
        data = {
            "task_id": task_id,
            "format": format,
            "versions": [v.to_dict() for v in versions],
            "updated_at": datetime.now().isoformat()
        }
        
        # 原子写入
        fd, temp_path = tempfile.mkstemp(suffix='.json', dir=str(version_dir))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, versions_file)
        except (OSError, IOError):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        
        # 更新缓存
        cache_key = f"{task_id}:{format}"
        self._cache[cache_key] = versions
    
    def _get_next_version_id(self, versions: List[VersionInfo]) -> str:
        """获取下一个版本ID"""
        if not versions:
            return "v1"
        
        # 解析现有版本号
        max_num = 0
        for v in versions:
            if v.version_id.startswith("v"):
                try:
                    num = int(v.version_id[1:])
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        
        return f"v{max_num + 1}"
    
    def _calculate_checksum(self, file_path: str) -> Optional[str]:
        """计算文件校验码"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
        except (OSError, IOError):
            pass
        return None
    
    def create_version(
        self,
        task_id: str,
        format: str,
        file_path: str,
        file_size: int,
        created_by: str,
        template: Optional[str] = None,
        adjustments: Optional[List[Dict[str, Any]]] = None,
        change_summary: str = "",
        copy_file: bool = False
    ) -> Optional[VersionInfo]:
        """
        创建新版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            file_path: 文档路径
            file_size: 文件大小
            created_by: 创建类型
            template: 模板名称
            adjustments: 调整记录
            change_summary: 变更摘要
            copy_file: 是否复制文件到版本目录
            
        Returns:
            VersionInfo 版本信息
        """
        # 验证
        if not self._is_valid_task_id(task_id):
            logger.warning(f"Invalid task_id: {task_id}")
            return None
        
        if not self._is_valid_format(format):
            logger.warning(f"Invalid format: {format}")
            return None
        
        # file_size 验证
        if not isinstance(file_size, int) or file_size < 0:
            logger.warning(f"Invalid file_size: {file_size}")
            return None
        
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"File size too large: {file_size} > {MAX_FILE_SIZE}")
            return None
        
        # created_by 验证
        if created_by not in VALID_CREATED_BY:
            logger.warning(f"Invalid created_by: {created_by}")
            return None
        
        # 加载现有版本
        versions = self._load_versions(task_id, format)
        
        # 检查版本数量限制
        if len(versions) >= MAX_VERSIONS:
            logger.warning(f"Max versions reached for {task_id}/{format}")
            return None
        
        # 获取新版本ID
        version_id = self._get_next_version_id(versions)
        
        # 获取父版本
        parent_version = versions[-1].version_id if versions else None
        
        # 计算校验码
        checksum = self._calculate_checksum(file_path)
        
        # 创建版本信息
        version = VersionInfo(
            version_id=version_id,
            format=format,
            file_path=file_path,
            file_size=file_size,
            created_at=datetime.now(),
            created_by=created_by,
            template=template,
            adjustments=adjustments or [],
            parent_version=parent_version,
            change_summary=change_summary,
            checksum=checksum
        )
        
        # 可选：复制文件
        if copy_file and os.path.exists(file_path):
            version_dir = self._get_version_dir(task_id, format) / version_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            dest_path = version_dir / os.path.basename(file_path)
            shutil.copy2(file_path, dest_path)
            version.file_path = str(dest_path)
        
        # 添加到列表
        versions.append(version)
        
        # 保存
        self._save_versions(task_id, format, versions)
        
        logger.info(f"Created version {version_id} for {task_id}/{format}")
        
        return version
    
    def list_versions(
        self,
        task_id: str,
        format: str
    ) -> List[VersionInfo]:
        """
        列出所有版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            
        Returns:
            版本列表（按版本号排序）
        """
        if not self._is_valid_task_id(task_id):
            return []
        
        if not self._is_valid_format(format):
            return []
        
        # 检查缓存
        cache_key = f"{task_id}:{format}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        versions = self._load_versions(task_id, format)
        self._cache[cache_key] = versions
        
        return versions
    
    def get_version(
        self,
        task_id: str,
        format: str,
        version_id: str
    ) -> Optional[VersionInfo]:
        """
        获取特定版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            version_id: 版本ID
            
        Returns:
            VersionInfo 或 None
        """
        versions = self.list_versions(task_id, format)
        
        for v in versions:
            if v.version_id == version_id:
                return v
        
        return None
    
    def get_latest_version(
        self,
        task_id: str,
        format: str
    ) -> Optional[VersionInfo]:
        """
        获取最新版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            
        Returns:
            VersionInfo 或 None
        """
        versions = self.list_versions(task_id, format)
        
        if versions:
            return versions[-1]
        
        return None
    
    def compare_versions(
        self,
        task_id: str,
        format: str,
        version_id_1: str,
        version_id_2: str
    ) -> Optional[Dict[str, Any]]:
        """
        对比两个版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            version_id_1: 版本1
            version_id_2: 版本2
            
        Returns:
            对比结果字典
        """
        v1 = self.get_version(task_id, format, version_id_1)
        v2 = self.get_version(task_id, format, version_id_2)
        
        if not v1 or not v2:
            return None
        
        # 相同版本
        if version_id_1 == version_id_2:
            return {
                "identical": True,
                "v1": v1.to_dict(),
                "v2": v2.to_dict()
            }
        
        # 版本差异
        return {
            "identical": False,
            "v1": v1.to_dict(),
            "v2": v2.to_dict(),
            "diff": {
                "file_size": v2.file_size - v1.file_size,
                "created_by_diff": v2.created_by != v1.created_by,
                "template_diff": v2.template != v1.template,
                "adjustments_count_diff": len(v2.adjustments) - len(v1.adjustments),
                "change_summary": v2.change_summary
            }
        }
    
    def rollback_to_version(
        self,
        task_id: str,
        format: str,
        target_version_id: str
    ) -> Optional[VersionInfo]:
        """
        回滚到指定版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            target_version_id: 目标版本ID
            
        Returns:
            新创建的回滚版本
        """
        # 获取目标版本
        target_version = self.get_version(task_id, format, target_version_id)
        
        if not target_version:
            logger.warning(f"Target version not found: {target_version_id}")
            return None
        
        # 获取当前最新版本
        latest = self.get_latest_version(task_id, format)
        
        if not latest:
            logger.warning(f"No latest version to rollback from")
            return None
        
        # 创建回滚版本
        rollback_version = self.create_version(
            task_id=task_id,
            format=format,
            file_path=target_version.file_path,
            file_size=target_version.file_size,
            created_by="rollback",
            template=target_version.template,
            adjustments=[{"type": "rollback", "target": target_version_id}],
            change_summary=f"回滚到 {target_version_id}"
        )
        
        if rollback_version:
            # 设置父版本为当前最新
            versions = self._load_versions(task_id, format)
            if versions:
                versions[-1].parent_version = latest.version_id
                self._save_versions(task_id, format, versions)
            
            logger.info(f"Rolled back to {target_version_id}, created {rollback_version.version_id}")
        
        return rollback_version
    
    def delete_version(
        self,
        task_id: str,
        format: str,
        version_id: str
    ) -> bool:
        """
        删除指定版本
        
        Args:
            task_id: 任务ID
            format: 文档格式
            version_id: 版本ID
            
        Returns:
            是否成功
        """
        versions = self._load_versions(task_id, format)
        
        new_versions = [v for v in versions if v.version_id != version_id]
        
        if len(new_versions) == len(versions):
            return False  # 版本不存在
        
        self._save_versions(task_id, format, new_versions)
        
        # 删除版本目录
        version_dir = self._get_version_dir(task_id, format) / version_id
        if version_dir.exists():
            shutil.rmtree(version_dir)
        
        logger.info(f"Deleted version {version_id} for {task_id}/{format}")
        
        return True
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache.clear()


# 导出
__all__ = ["DocumentVersionManager", "VersionInfo", "VersionError"]