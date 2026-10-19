"""
存储管理器

职责：
- 持久化研究结果
- 支持恢复
- 管理存储生命周期

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# task_id 格式验证正则（防止路径遍历攻击）
# 允许：字母、数字、下划线、连字符
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_task_id(task_id: str) -> bool:
    """
    验证 task_id 格式是否安全
    
    Args:
        task_id: 任务ID
        
    Returns:
        是否有效
        
    安全考虑：
    - 防止路径遍历攻击（禁止 / \\ .. 等字符）
    - 防止特殊字符注入
    """
    if not task_id:
        return False
    if len(task_id) > 128:  # 防止过长
        return False
    return bool(TASK_ID_PATTERN.match(task_id))


@dataclass
class StorageConfig:
    """存储配置"""
    # P0-5修复：使用统一输出路径
    base_path: Path = field(default_factory=lambda: Path("output/reports"))
    max_age_days: int = 30           # 最大保留天数
    auto_cleanup: bool = True         # 自动清理
    compress: bool = False            # 压缩存储
    backup_enabled: bool = True       # 备份


@dataclass
class ResearchRecord:
    """
    研究记录
    
    Attributes:
        task_id: 任务ID
        topic: 研究主题
        status: 状态
        created_at: 创建时间
        completed_at: 完成时间
        result_path: 结果路径
        metadata: 元数据
    """
    task_id: str
    topic: str
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    result_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_path": str(self.result_path) if self.result_path else None,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchRecord":
        """从字典创建"""
        return cls(
            task_id=data["task_id"],
            topic=data["topic"],
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result_path=Path(data["result_path"]) if data.get("result_path") else None,
            metadata=data.get("metadata", {}),
        )


class StorageManager:
    """
    存储管理器
    
    职责：
    - 持久化研究结果
    - 支持恢复
    - 管理存储生命周期
    
    使用示例:
        manager = StorageManager(StorageConfig())
        
        # 保存结果
        record = manager.save(
            task_id="research_001",
            topic="新能源汽车市场",
            result={"market_size": "100亿"}
        )
        
        # 加载结果
        loaded = manager.load("research_001")
        
        # 列出所有记录
        records = manager.list_records()
    """
    
    INDEX_FILE = "index.json"
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        
        # 确保目录存在
        self.config.base_path.mkdir(parents=True, exist_ok=True)
        
        # 索引
        self._index: Dict[str, ResearchRecord] = {}
        self._load_index()
        
        # 统计
        self._total_saved = 0
        self._total_loaded = 0
    
    def _load_index(self) -> None:
        """加载索引"""
        index_path = self.config.base_path / self.INDEX_FILE
        
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for task_id, record_data in data.get("records", {}).items():
                    self._index[task_id] = ResearchRecord.from_dict(record_data)
                
                logger.info(f"Loaded {len(self._index)} records from index")
                
            except Exception as e:
                logger.error(f"Failed to load index: {e}")
    
    def _save_index(self) -> None:
        """保存索引"""
        index_path = self.config.base_path / self.INDEX_FILE
        
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "records": {
                    task_id: record.to_dict()
                    for task_id, record in self._index.items()
                }
            }
            
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def save(
        self,
        task_id: str,
        topic: str,
        result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResearchRecord:
        """
        保存研究结果
        
        Args:
            task_id: 任务ID（必须是安全的文件名格式）
            topic: 研究主题
            result: 研究结果
            metadata: 元数据
            
        Returns:
            ResearchRecord: 研究记录
            
        Raises:
            ValueError: task_id 格式不安全
        """
        # 安全验证：防止路径遍历攻击
        if not validate_task_id(task_id):
            raise ValueError(
                f"Invalid task_id: '{task_id}'. "
                "Task ID must contain only alphanumeric characters, "
                "underscores, and hyphens."
            )
        
        metadata = metadata or {}
        record_status = "completed"
        if (
            metadata.get("formal_complete") is False
            or metadata.get("delivery_class") == "available_with_warnings"
            or metadata.get("quality_gate_status") == "degraded"
        ):
            record_status = "completed_with_warnings"

        # 创建记录。文件仍然照常保存；该状态只反映质量告警，不是交付闸门。
        record = ResearchRecord(
            task_id=task_id,
            topic=topic,
            status=record_status,
            completed_at=datetime.now(),
            metadata=metadata,
        )
        
        # 保存结果文件（task_id 已验证，可安全拼接）
        result_path = self.config.base_path / f"{task_id}.json"
        
        try:
            result_data = {
                "task_id": task_id,
                "topic": topic,
                "result": result,
                "saved_at": datetime.now().isoformat(),
                "metadata": metadata,
            }
            
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            
            record.result_path = result_path
            
        except (PermissionError, OSError) as e:
            logger.error(f"Permission denied or IO error saving result: {e}")
            record.status = "failed"
        except (TypeError, ValueError) as e:
            logger.error(f"Data serialization error: {e}")
            record.status = "failed"
        except Exception as e:
            logger.error(f"Unexpected error saving result: {e}")
            record.status = "failed"
        
        # 更新索引
        self._index[task_id] = record
        self._save_index()
        
        self._total_saved += 1
        
        logger.info(f"Saved research result: {task_id}")
        
        return record
    
    def load(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载研究结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            研究结果，不存在返回None
            
        Raises:
            ValueError: task_id 格式不安全
        """
        # 安全验证
        if not validate_task_id(task_id):
            raise ValueError(
                f"Invalid task_id: '{task_id}'. "
                "Task ID must contain only alphanumeric characters, "
                "underscores, and hyphens."
            )
        
        record = self._index.get(task_id)
        
        if not record or not record.result_path:
            return None
        
        try:
            with open(record.result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._total_loaded += 1
            
            return data.get("result")
            
        except FileNotFoundError:
            logger.warning(f"Result file not found: {record.result_path}")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading result: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in result file: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading result: {e}")
            return None
    
    def get_record(self, task_id: str) -> Optional[ResearchRecord]:
        """
        获取研究记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            研究记录
            
        Raises:
            ValueError: task_id 格式不安全
        """
        # 安全验证
        if not validate_task_id(task_id):
            raise ValueError(
                f"Invalid task_id: '{task_id}'. "
                "Task ID must contain only alphanumeric characters, "
                "underscores, and hyphens."
            )
        return self._index.get(task_id)
    
    def list_records(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ResearchRecord]:
        """
        列出研究记录
        
        Args:
            status: 状态过滤
            limit: 最大数量
            
        Returns:
            研究记录列表
        """
        records = list(self._index.values())
        
        if status:
            records = [r for r in records if r.status == status]
        
        # 按创建时间倒序
        records.sort(key=lambda r: r.created_at, reverse=True)
        
        return records[:limit]

    # Transitional aliases for the pre-redesign result-store interface.
    def load_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.load(task_id)

    def list_results(self, limit: int = 100) -> List[ResearchRecord]:
        return self.list_records(limit=limit)
    
    def delete(self, task_id: str) -> bool:
        """
        删除研究记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功删除
            
        Raises:
            ValueError: task_id 格式不安全
        """
        # 安全验证
        if not validate_task_id(task_id):
            raise ValueError(
                f"Invalid task_id: '{task_id}'. "
                "Task ID must contain only alphanumeric characters, "
                "underscores, and hyphens."
            )
        
        record = self._index.get(task_id)
        
        if not record:
            return False
        
        # 删除结果文件
        if record.result_path and record.result_path.exists():
            try:
                record.result_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete result file: {e}")
        
        # 从索引中移除
        del self._index[task_id]
        self._save_index()
        
        logger.info(f"Deleted research record: {task_id}")
        
        return True
    
    def cleanup(self, max_age_days: Optional[int] = None) -> int:
        """
        清理过期记录
        
        Args:
            max_age_days: 最大保留天数，None使用配置值
            
        Returns:
            清理的记录数量
        """
        max_age = max_age_days or self.config.max_age_days
        cutoff = datetime.now()
        
        to_delete = []
        
        for task_id, record in self._index.items():
            if record.completed_at:
                age = (cutoff - record.completed_at).days
                if age > max_age:
                    to_delete.append(task_id)
        
        for task_id in to_delete:
            self.delete(task_id)
        
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} expired records")
        
        return len(to_delete)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_records": len(self._index),
            "total_saved": self._total_saved,
            "total_loaded": self._total_loaded,
            "base_path": str(self.config.base_path),
        }
