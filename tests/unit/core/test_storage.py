"""
TaskStorage + WAL 存储层测试
TDD: 先写测试，再实现
"""
import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime


class TestTaskStorage:
    """任务存储测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录fixture"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def storage(self, temp_dir):
        """存储实例fixture"""
        from src.core.storage import TaskStorage
        return TaskStorage(base_path=temp_dir)
    
    def test_init_creates_directories(self, temp_dir):
        """测试初始化创建目录结构"""
        from src.core.storage import TaskStorage
        storage = TaskStorage(base_path=temp_dir)
        
        assert os.path.exists(temp_dir)
        assert os.path.exists(os.path.join(temp_dir, "tasks"))
        assert os.path.exists(os.path.join(temp_dir, "wal"))
    
    def test_save_task(self, storage, temp_dir):
        """测试保存任务"""
        task = {
            "task_id": "test-001",
            "status": "running",
            "data": {"key": "value"}
        }
        
        storage.save_task(task)
        
        # 验证文件存在
        task_file = os.path.join(temp_dir, "tasks", "test-001.json")
        assert os.path.exists(task_file)
        
        # 验证内容正确
        with open(task_file, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        assert saved["task_id"] == "test-001"
        assert saved["status"] == "running"
    
    def test_load_task(self, storage):
        """测试加载任务"""
        # 先保存
        task = {"task_id": "test-002", "status": "completed"}
        storage.save_task(task)
        
        # 再加载
        loaded = storage.load_task("test-002")
        assert loaded is not None
        assert loaded["task_id"] == "test-002"
        assert loaded["status"] == "completed"
    
    def test_load_nonexistent_task(self, storage):
        """测试加载不存在的任务"""
        result = storage.load_task("nonexistent")
        assert result is None
    
    def test_list_tasks(self, storage):
        """测试列出所有任务"""
        storage.save_task({"task_id": "task-1", "status": "running"})
        storage.save_task({"task_id": "task-2", "status": "completed"})
        storage.save_task({"task_id": "task-3", "status": "pending"})
        
        tasks = storage.list_tasks()
        assert len(tasks) == 3
        task_ids = {t["task_id"] for t in tasks}
        assert task_ids == {"task-1", "task-2", "task-3"}
    
    def test_delete_task(self, storage, temp_dir):
        """测试删除任务"""
        storage.save_task({"task_id": "delete-me", "status": "running"})
        
        # 确认存在
        assert storage.load_task("delete-me") is not None
        
        # 删除
        storage.delete_task("delete-me")
        
        # 确认删除
        assert storage.load_task("delete-me") is None
        assert not os.path.exists(os.path.join(temp_dir, "tasks", "delete-me.json"))


class TestWAL:
    """WAL（预写日志）测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def wal(self, temp_dir):
        """WAL实例fixture"""
        from src.core.storage import WriteAheadLog
        return WriteAheadLog(wal_path=temp_dir)
    
    def test_append_log(self, wal, temp_dir):
        """测试追加日志"""
        entry = {
            "operation": "save_task",
            "task_id": "wal-001",
            "timestamp": datetime.now().isoformat()
        }
        
        wal.append(entry)
        
        # 验证日志文件存在（在 wal/ 子目录中）
        log_files = list(Path(temp_dir).glob("**/*.wal"))
        assert len(log_files) == 1
    
    def test_read_logs(self, wal):
        """测试读取日志"""
        # 追加多条
        wal.append({"operation": "op1", "task_id": "t1"})
        wal.append({"operation": "op2", "task_id": "t2"})
        wal.append({"operation": "op3", "task_id": "t3"})
        
        # 读取
        logs = wal.read_all()
        assert len(logs) == 3
        assert logs[0]["operation"] == "op1"
        assert logs[1]["operation"] == "op2"
        assert logs[2]["operation"] == "op3"
    
    def test_truncate_after_checkpoint(self, wal):
        """测试checkpoint后截断日志"""
        wal.append({"operation": "op1"})
        wal.append({"operation": "op2"})
        
        # checkpoint
        wal.truncate()
        
        # 日志应该被清空
        logs = wal.read_all()
        assert len(logs) == 0
    
    def test_wal_recovery(self, temp_dir):
        """测试WAL恢复机制"""
        from src.core.storage import WriteAheadLog
        
        # 创建WAL并写入
        wal = WriteAheadLog(wal_path=temp_dir)
        wal.append({"operation": "save", "task_id": "recover-1"})
        wal.append({"operation": "save", "task_id": "recover-2"})
        
        # 模拟重启：创建新实例
        wal2 = WriteAheadLog(wal_path=temp_dir)
        logs = wal2.read_all()
        
        assert len(logs) == 2
        assert logs[0]["task_id"] == "recover-1"
        assert logs[1]["task_id"] == "recover-2"


class TestStorageIntegration:
    """存储层集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_save_with_wal(self, temp_dir):
        """测试带WAL的任务保存"""
        from src.core.storage import TaskStorage
        
        storage = TaskStorage(base_path=temp_dir, enable_wal=True)
        
        task = {"task_id": "wal-task", "data": "important"}
        storage.save_task(task)
        
        # 验证任务保存
        loaded = storage.load_task("wal-task")
        assert loaded["data"] == "important"
        
        # 验证WAL记录
        wal_logs = storage.wal.read_all()
        assert len(wal_logs) >= 1
        assert any(log.get("task_id") == "wal-task" for log in wal_logs)
    
    def test_crash_recovery(self, temp_dir):
        """测试崩溃恢复"""
        from src.core.storage import TaskStorage
        
        # 模拟保存但未完成
        storage1 = TaskStorage(base_path=temp_dir, enable_wal=True)
        storage1.save_task({"task_id": "crash-task", "status": "pending"})
        
        # 模拟重启（新实例）
        storage2 = TaskStorage(base_path=temp_dir, enable_wal=True)
        storage2.recover_from_wal()
        
        # 验证数据恢复
        recovered = storage2.load_task("crash-task")
        assert recovered is not None
        assert recovered["status"] == "pending"
