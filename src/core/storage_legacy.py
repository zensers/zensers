"""
TaskStorage + WAL 存储层实现
简化版：JSON文件 + WAL机制

配置系统集成:
- 默认存储路径从 settings.system.data_dir 读取
- 支持从 settings.database 读取数据库配置（未来扩展）
"""
import json
import os
import glob
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from threading import Lock
import logging

# 配置系统
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


class WriteAheadLog:
    """
    预写日志（WAL）实现
    
    保证数据持久性，支持崩溃恢复
    """
    
    def __init__(self, wal_path: str):
        self.wal_path = Path(wal_path)
        self.wal_dir = self.wal_path / "wal"
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = Lock()
        self._current_file = self._get_current_wal_file()
    
    def _get_current_wal_file(self) -> Path:
        """获取当前WAL文件"""
        timestamp = datetime.now().strftime("%Y%m%d")
        return self.wal_dir / f"{timestamp}.wal"
    
    def append(self, entry: Dict[str, Any]) -> None:
        """
        追加日志条目
        
        Args:
            entry: 日志条目字典
        """
        with self._lock:
            # 确保时间戳
            if "timestamp" not in entry:
                entry["timestamp"] = datetime.now().isoformat()
            
            # 追加写入（行级JSON）
            with open(self._current_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                # 强制刷盘（确保持久性）
                f.flush()
                os.fsync(f.fileno())
    
    def read_all(self) -> List[Dict[str, Any]]:
        """
        读取所有日志条目
        
        Returns:
            日志条目列表
        """
        logs = []
        
        # 读取所有.wal文件
        wal_files = sorted(self.wal_dir.glob("*.wal"))
        
        for wal_file in wal_files:
            try:
                with open(wal_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                logs.append(json.loads(line))
                            except json.JSONDecodeError:
                                # 跳过损坏的行
                                continue
            except FileNotFoundError:
                continue
        
        return logs
    
    def truncate(self) -> None:
        """
        截断日志（checkpoint后调用）
        """
        with self._lock:
            # 删除所有WAL文件
            for wal_file in self.wal_dir.glob("*.wal"):
                try:
                    wal_file.unlink()
                except OSError:
                    pass
            
            # 重置当前文件
            self._current_file = self._get_current_wal_file()


class TaskStorage:
    """
    任务存储管理器
    
    使用JSON文件存储，支持WAL机制保证数据安全
    
    配置来源（settings.system）:
    - data_dir: 数据存储根目录
    - cache_dir: 缓存目录
    - temp_dir: 临时文件目录
    """
    
    def __init__(self, base_path: Optional[str] = None, enable_wal: bool = True):
        """
        初始化存储
        
        Args:
            base_path: 存储根目录，默认从配置系统读取
            enable_wal: 是否启用WAL
        """
        # 从配置系统读取默认路径
        if base_path is None:
            if SETTINGS_AVAILABLE:
                base_path = settings.system.data_dir
                logger.info(f"TaskStorage 使用配置系统路径: {base_path}")
            else:
                base_path = "data"
                logger.warning(f"配置系统不可用，使用默认路径: {base_path}")
        
        self.base_path = Path(base_path)
        self.tasks_dir = self.base_path / "tasks"
        self.wal_dir = self.base_path / "wal"
        
        # 创建目录
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        
        # WAL
        self.enable_wal = enable_wal
        self.wal = WriteAheadLog(str(self.base_path)) if enable_wal else None
        
        self._lock = Lock()
    
    def _get_task_path(self, task_id: str) -> Path:
        """获取任务文件路径"""
        return self.tasks_dir / f"{task_id}.json"
    
    def save_task(self, task: Dict[str, Any]) -> None:
        """
        保存任务
        
        Args:
            task: 任务字典，必须包含task_id
        """
        task_id = task.get("task_id")
        if not task_id:
            raise ValueError("Task must have 'task_id' field")
        
        task_path = self._get_task_path(task_id)
        
        with self._lock:
            # 1. 先写WAL
            if self.wal:
                self.wal.append({
                    "operation": "save_task",
                    "task_id": task_id,
                    "task": task
                })
            
            # 2. 再写入主文件
            with open(task_path, 'w', encoding='utf-8') as f:
                json.dump(task, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    
    def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务字典，不存在返回None
        """
        task_path = self._get_task_path(task_id)
        
        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        列出所有任务
        
        Returns:
            任务列表
        """
        tasks = []
        
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                    tasks.append(task)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        
        return tasks
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功删除
        """
        task_path = self._get_task_path(task_id)
        
        with self._lock:
            # 写WAL
            if self.wal:
                self.wal.append({
                    "operation": "delete_task",
                    "task_id": task_id
                })
            
            # 删除文件
            try:
                task_path.unlink()
                return True
            except FileNotFoundError:
                return False
    
    def recover_from_wal(self) -> List[str]:
        """
        从WAL恢复数据
        
        Returns:
            恢复的任务ID列表
        """
        if not self.wal:
            return []
        
        recovered = []
        logs = self.wal.read_all()
        
        for entry in logs:
            operation = entry.get("operation")
            task_id = entry.get("task_id")
            
            if operation == "save_task" and task_id:
                task = entry.get("task", {})
                # 直接恢复（不经过WAL避免循环）
                task_path = self._get_task_path(task_id)
                with open(task_path, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)
                recovered.append(task_id)
        
        return recovered
    
    def checkpoint(self) -> None:
        """
        创建checkpoint，清空WAL
        """
        if self.wal:
            self.wal.truncate()


def create_task_storage_from_settings(enable_wal: bool = True) -> TaskStorage:
    """
    从配置系统创建 TaskStorage 实例.
    
    自动从 settings.system.data_dir 读取存储路径。
    
    Args:
        enable_wal: 是否启用WAL
    
    Returns:
        配置好的 TaskStorage 实例
    """
    return TaskStorage(enable_wal=enable_wal)


def get_storage_paths() -> Dict[str, Path]:
    """
    从配置系统获取存储路径.
    
    Returns:
        包含 data_dir, cache_dir, temp_dir 的字典
    """
    if SETTINGS_AVAILABLE:
        return {
            "data_dir": Path(settings.system.data_dir),
            "cache_dir": Path(settings.system.cache_dir),
            "temp_dir": Path(settings.system.temp_dir),
            "report_output_dir": Path(settings.system.report_output_dir),
        }
    else:
        return {
            "data_dir": Path("data"),
            "cache_dir": Path("cache"),
            "temp_dir": Path("tmp"),
            "report_output_dir": Path("output/reports"),
        }
