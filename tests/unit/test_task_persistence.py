# -*- coding: utf-8 -*-
"""
任务持久化管理器测试
==================

Phase 4 Week 16: 任务持久化测试

测试覆盖:
- TaskState 枚举
- TaskStatus, TaskCheckpoint, PersistentTask 数据类
- TaskPersistenceManager 持久化操作
"""

import pytest
import tempfile
import shutil
import json
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

# 导入待测试的模块
from src.core.task_persistence import (
    TaskState,
    TaskStatus,
    TaskCheckpoint,
    PersistentTask,
    TaskPersistenceManager
)


class TestTaskState:
    """TaskState 枚举测试"""
    
    def test_task_state_values(self):
        """测试任务状态值"""
        assert TaskState.CREATED.value == "created"
        assert TaskState.INITIALIZING.value == "initializing"
        assert TaskState.RUNNING.value == "running"
        assert TaskState.PAUSED.value == "paused"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
    
    def test_is_terminal(self):
        """测试终止状态判断"""
        assert TaskState.COMPLETED.is_terminal() is True
        assert TaskState.FAILED.is_terminal() is True
        assert TaskState.RUNNING.is_terminal() is False
        assert TaskState.CREATED.is_terminal() is False
    
    def test_is_active(self):
        """测试活跃状态判断"""
        assert TaskState.CREATED.is_active() is True
        assert TaskState.INITIALIZING.is_active() is True
        assert TaskState.RUNNING.is_active() is True
        assert TaskState.PAUSED.is_active() is True
        assert TaskState.COMPLETED.is_active() is False
        assert TaskState.FAILED.is_active() is False


class TestTaskStatus:
    """TaskStatus 数据类测试"""
    
    def test_task_status_creation(self):
        """测试任务状态创建"""
        status = TaskStatus(
            task_id="task_001",
            state=TaskState.CREATED,
            progress=0.0,
            message="初始化"
        )
        
        assert status.task_id == "task_001"
        assert status.state == TaskState.CREATED
        assert status.progress == 0.0
        assert status.message == "初始化"
        assert status.created_at is not None
        assert status.updated_at is not None
    
    def test_task_status_to_dict(self):
        """测试任务状态序列化"""
        status = TaskStatus(
            task_id="task_002",
            state=TaskState.RUNNING,
            progress=0.5,
            message="处理中"
        )
        
        data = status.to_dict()
        
        assert data["task_id"] == "task_002"
        assert data["state"] == "running"
        assert data["progress"] == 0.5
        assert data["message"] == "处理中"
        assert "created_at" in data
        assert "updated_at" in data
    
    def test_task_status_from_dict(self):
        """测试任务状态反序列化"""
        data = {
            "task_id": "task_003",
            "state": "completed",
            "progress": 1.0,
            "message": "完成",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T01:00:00"
        }
        
        status = TaskStatus.from_dict(data)
        
        assert status.task_id == "task_003"
        assert status.state == TaskState.COMPLETED
        assert status.progress == 1.0
        assert status.message == "完成"
    
    def test_task_status_default_values(self):
        """测试默认值"""
        status = TaskStatus(
            task_id="task_004",
            state=TaskState.CREATED
        )
        
        assert status.progress == 0.0
        assert status.message == ""


class TestTaskCheckpoint:
    """TaskCheckpoint 数据类测试"""
    
    def test_checkpoint_creation(self):
        """测试检查点创建"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_001",
            step_name="step_1",
            step_index=1,
            total_steps=5,
            data={"key": "value"}
        )
        
        assert checkpoint.checkpoint_id == "cp_001"
        assert checkpoint.task_id == "task_001"
        assert checkpoint.step_name == "step_1"
        assert checkpoint.step_index == 1
        assert checkpoint.total_steps == 5
        assert checkpoint.data == {"key": "value"}
    
    def test_checkpoint_progress(self):
        """测试检查点进度计算"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_001",
            step_name="step_2",
            step_index=2,
            total_steps=5,
            data={}
        )
        
        # 进度 = 2 / 5 = 0.4
        assert checkpoint.progress == 0.4
    
    def test_checkpoint_progress_zero_total(self):
        """测试总步骤为 0 时的进度"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_001",
            step_name="step_1",
            step_index=1,
            total_steps=0,
            data={}
        )
        
        assert checkpoint.progress == 0.0
    
    def test_checkpoint_to_dict(self):
        """测试检查点序列化"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_002",
            task_id="task_002",
            step_name="step_3",
            step_index=3,
            total_steps=10,
            data={"result": "data"}
        )
        
        data = checkpoint.to_dict()
        
        assert data["checkpoint_id"] == "cp_002"
        assert data["task_id"] == "task_002"
        assert data["step_name"] == "step_3"
        assert data["step_index"] == 3
        assert data["total_steps"] == 10
        assert data["data"] == {"result": "data"}
        assert "progress" in data
    
    def test_checkpoint_from_dict(self):
        """测试检查点反序列化"""
        data = {
            "checkpoint_id": "cp_003",
            "task_id": "task_003",
            "step_name": "step_1",
            "step_index": 1,
            "total_steps": 3,
            "data": {"input": "test"},
            "created_at": "2024-01-01T00:00:00"
        }
        
        checkpoint = TaskCheckpoint.from_dict(data)
        
        assert checkpoint.checkpoint_id == "cp_003"
        assert checkpoint.step_name == "step_1"
        assert checkpoint.data == {"input": "test"}


class TestPersistentTask:
    """PersistentTask 数据类测试"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={"query": "test"}
        )
        
        assert task.task_id == "task_001"
        assert task.task_type == "research"
        assert task.input_data == {"query": "test"}
        assert task.output_data is None
        assert task.result is None
        assert task.error is None
        assert len(task.checkpoints) == 0
    
    def test_task_post_init(self):
        """测试 __post_init__ 初始化 status"""
        task = PersistentTask(
            task_id="task_002",
            task_type="analysis",
            input_data={}
        )
        
        # status 应该在 __post_init__ 中被初始化
        assert task.status is not None
        assert task.status.state == TaskState.CREATED
    
    def test_task_start(self):
        """测试任务启动"""
        task = PersistentTask(
            task_id="task_003",
            task_type="research",
            input_data={}
        )
        
        task.start()
        
        assert task.status.state == TaskState.RUNNING
    
    def test_task_complete(self):
        """测试任务完成"""
        task = PersistentTask(
            task_id="task_004",
            task_type="research",
            input_data={}
        )
        
        task.complete({"result": "success"})
        
        assert task.status.state == TaskState.COMPLETED
        assert task.status.progress == 1.0
        assert task.result == {"result": "success"}
    
    def test_task_fail(self):
        """测试任务失败"""
        task = PersistentTask(
            task_id="task_005",
            task_type="research",
            input_data={}
        )
        
        task.fail("Something went wrong")
        
        assert task.status.state == TaskState.FAILED
        assert task.error == "Something went wrong"
    
    def test_task_pause_resume(self):
        """测试任务暂停和恢复"""
        task = PersistentTask(
            task_id="task_006",
            task_type="research",
            input_data={}
        )
        
        task.start()
        task.pause()
        assert task.status.state == TaskState.PAUSED
        
        task.resume()
        assert task.status.state == TaskState.RUNNING
    
    def test_task_update_progress(self):
        """测试更新进度"""
        task = PersistentTask(
            task_id="task_007",
            task_type="research",
            input_data={}
        )
        
        task.update_progress(0.5, "处理中")
        
        assert task.status.progress == 0.5
        assert task.status.message == "处理中"
    
    def test_task_update_progress_clamped(self):
        """测试进度值被限制在 0-1 范围"""
        task = PersistentTask(
            task_id="task_008",
            task_type="research",
            input_data={}
        )
        
        task.update_progress(1.5, "超过 1")
        assert task.status.progress == 1.0
        
        task.update_progress(-0.5, "小于 0")
        assert task.status.progress == 0.0
    
    def test_task_add_checkpoint(self):
        """测试添加检查点"""
        task = PersistentTask(
            task_id="task_009",
            task_type="research",
            input_data={}
        )
        
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_009",
            step_name="step_1",
            step_index=1,
            total_steps=3,
            data={}
        )
        
        task.add_checkpoint(checkpoint)
        
        assert len(task.checkpoints) == 1
        assert task.checkpoints[0].checkpoint_id == "cp_001"
    
    def test_task_get_latest_checkpoint(self):
        """测试获取最新检查点"""
        task = PersistentTask(
            task_id="task_010",
            task_type="research",
            input_data={}
        )
        
        # 无检查点
        assert task.get_latest_checkpoint() is None
        
        # 添加多个检查点
        for i in range(3):
            checkpoint = TaskCheckpoint(
                checkpoint_id=f"cp_{i}",
                task_id="task_010",
                step_name=f"step_{i}",
                step_index=i + 1,
                total_steps=3,
                data={}
            )
            task.add_checkpoint(checkpoint)
        
        latest = task.get_latest_checkpoint()
        assert latest.checkpoint_id == "cp_2"
    
    def test_task_to_dict(self):
        """测试任务序列化"""
        task = PersistentTask(
            task_id="task_011",
            task_type="research",
            input_data={"query": "test"},
            output_data={"output": "result"}
        )
        task.start()
        task.update_progress(0.5, "处理中")
        
        data = task.to_dict()
        
        assert data["task_id"] == "task_011"
        assert data["task_type"] == "research"
        assert data["input_data"] == {"query": "test"}
        assert data["output_data"] == {"output": "result"}
        assert data["status"]["state"] == "running"
        assert data["status"]["progress"] == 0.5
    
    def test_task_from_dict(self):
        """测试任务反序列化"""
        data = {
            "task_id": "task_012",
            "task_type": "analysis",
            "input_data": {"input": "data"},
            "output_data": {"output": "result"},
            "result": {"final": "result"},
            "error": None,
            "status": {
                "task_id": "task_012",
                "state": "running",
                "progress": 0.7,
                "message": "处理中",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:30:00"
            },
            "checkpoints": [
                {
                    "checkpoint_id": "cp_001",
                    "task_id": "task_012",
                    "step_name": "step_1",
                    "step_index": 1,
                    "total_steps": 3,
                    "data": {},
                    "progress": 0.33,
                    "created_at": "2024-01-01T00:10:00"
                }
            ],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:30:00"
        }
        
        task = PersistentTask.from_dict(data)
        
        assert task.task_id == "task_012"
        assert task.task_type == "analysis"
        assert task.status.state == TaskState.RUNNING
        assert task.status.progress == 0.7
        assert len(task.checkpoints) == 1


class TestTaskPersistenceManager:
    """TaskPersistenceManager 测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录 fixture"""
        dir_path = tempfile.mkdtemp()
        yield dir_path
        shutil.rmtree(dir_path, ignore_errors=True)
    
    def test_manager_initialization(self, temp_dir):
        """测试管理器初始化"""
        manager = TaskPersistenceManager(temp_dir)
        
        assert manager.storage_path == Path(temp_dir)
        assert manager.tasks_dir.exists()
    
    def test_manager_initialization_with_history(self, temp_dir):
        """测试带历史追踪的初始化"""
        manager = TaskPersistenceManager(temp_dir, track_history=True)
        
        assert manager.track_history is True
        assert manager.history_dir.exists()
    
    def test_create_task(self, temp_dir):
        """测试创建任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        
        assert task.task_id is not None
        assert task.task_type == "research"
        assert task.input_data == {"query": "test"}
        assert task.status.state == TaskState.CREATED
    
    def test_create_task_with_custom_id(self, temp_dir):
        """测试使用自定义 ID 创建任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task(
            "research",
            {"query": "test"},
            task_id="custom_task_001"
        )
        
        assert task.task_id == "custom_task_001"
    
    def test_save_and_load_task(self, temp_dir):
        """测试保存和加载任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        loaded = manager.load_task(task.task_id)
        
        assert loaded is not None
        assert loaded.task_id == task.task_id
        assert loaded.task_type == "research"
        assert loaded.input_data == {"query": "test"}
    
    def test_load_nonexistent_task(self, temp_dir):
        """测试加载不存在的任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        loaded = manager.load_task("nonexistent_task")
        assert loaded is None
    
    def test_update_task_state(self, temp_dir):
        """测试更新任务状态"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        result = manager.update_task_state(
            task.task_id,
            TaskState.RUNNING,
            progress=0.5,
            message="处理中"
        )
        
        assert result is True
        
        loaded = manager.load_task(task.task_id)
        assert loaded.status.state == TaskState.RUNNING
        assert loaded.status.progress == 0.5
        assert loaded.status.message == "处理中"
    
    def test_update_nonexistent_task_state(self, temp_dir):
        """测试更新不存在任务的状态"""
        manager = TaskPersistenceManager(temp_dir)
        
        result = manager.update_task_state("nonexistent", TaskState.RUNNING)
        assert result is False
    
    def test_create_checkpoint(self, temp_dir):
        """测试创建检查点"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        checkpoint = manager.create_checkpoint(
            task.task_id,
            "step_1",
            1,
            5,
            {"intermediate": "data"}
        )
        
        assert checkpoint is not None
        assert checkpoint.step_name == "step_1"
        assert checkpoint.step_index == 1
        assert checkpoint.total_steps == 5
        
        # 验证检查点被添加到任务
        loaded = manager.load_task(task.task_id)
        assert len(loaded.checkpoints) == 1
    
    def test_create_checkpoint_nonexistent_task(self, temp_dir):
        """测试为不存在的任务创建检查点"""
        manager = TaskPersistenceManager(temp_dir)
        
        checkpoint = manager.create_checkpoint(
            "nonexistent",
            "step_1",
            1,
            5,
            {}
        )
        
        assert checkpoint is None
    
    def test_restore_from_checkpoint(self, temp_dir):
        """测试从检查点恢复"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        checkpoint = manager.create_checkpoint(
            task.task_id,
            "step_1",
            1,
            5,
            {"saved": "state"}
        )
        
        # 从检查点恢复
        restored = manager.restore_from_checkpoint(task.task_id, checkpoint.checkpoint_id)
        
        assert restored is not None
        assert restored["step_name"] == "step_1"
        assert restored["data"] == {"saved": "state"}
    
    def test_restore_from_nonexistent_checkpoint(self, temp_dir):
        """测试从不存在的检查点恢复"""
        manager = TaskPersistenceManager(temp_dir)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        restored = manager.restore_from_checkpoint(task.task_id, "nonexistent_cp")
        assert restored is None
    
    def test_list_active_tasks(self, temp_dir):
        """测试列出活跃任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        # 创建多个任务
        task1 = manager.create_task("research", {"query": "1"})
        task2 = manager.create_task("research", {"query": "2"})
        task3 = manager.create_task("research", {"query": "3"})
        
        manager.save_task(task1)
        manager.save_task(task2)
        manager.save_task(task3)
        
        # 更新状态
        manager.update_task_state(task1.task_id, TaskState.COMPLETED)
        manager.update_task_state(task2.task_id, TaskState.RUNNING)
        # task3 保持 CREATED
        
        active_tasks = manager.list_active_tasks()
        
        assert len(active_tasks) == 2
        task_ids = [t.task_id for t in active_tasks]
        assert task2.task_id in task_ids
        assert task3.task_id in task_ids
    
    def test_list_tasks_by_state(self, temp_dir):
        """测试按状态列出任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task1 = manager.create_task("research", {"query": "1"})
        task2 = manager.create_task("research", {"query": "2"})
        
        manager.save_task(task1)
        manager.save_task(task2)
        
        manager.update_task_state(task1.task_id, TaskState.COMPLETED)
        manager.update_task_state(task2.task_id, TaskState.FAILED)
        
        completed = manager.list_tasks_by_state(TaskState.COMPLETED)
        assert len(completed) == 1
        assert completed[0].task_id == task1.task_id
        
        failed = manager.list_tasks_by_state(TaskState.FAILED)
        assert len(failed) == 1
        assert failed[0].task_id == task2.task_id
    
    def test_cleanup_completed_tasks(self, temp_dir):
        """测试清理已完成任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task1 = manager.create_task("research", {"query": "1"})
        task2 = manager.create_task("research", {"query": "2"})
        
        manager.save_task(task1)
        manager.save_task(task2)
        
        manager.update_task_state(task1.task_id, TaskState.COMPLETED)
        # task2 保持 CREATED
        
        cleaned = manager.cleanup_completed_tasks(keep_days=0)  # 立即清理
        assert cleaned == 1
        
        # 验证 task1 被删除
        loaded = manager.load_task(task1.task_id)
        assert loaded is None
        
        # task2 应该还在
        loaded2 = manager.load_task(task2.task_id)
        assert loaded2 is not None
    
    def test_recover_all_tasks(self, temp_dir):
        """测试恢复所有任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        for i in range(5):
            task = manager.create_task("research", {"query": str(i)})
            manager.save_task(task)
        
        recovered = manager.recover_all_tasks()
        assert len(recovered) == 5
    
    def test_find_interrupted_tasks(self, temp_dir):
        """测试查找中断的任务"""
        manager = TaskPersistenceManager(temp_dir)
        
        task1 = manager.create_task("research", {"query": "1"})
        task2 = manager.create_task("research", {"query": "2"})
        task3 = manager.create_task("research", {"query": "3"})
        
        manager.save_task(task1)
        manager.save_task(task2)
        manager.save_task(task3)
        
        manager.update_task_state(task1.task_id, TaskState.RUNNING)
        manager.update_task_state(task2.task_id, TaskState.INITIALIZING)
        manager.update_task_state(task3.task_id, TaskState.COMPLETED)
        
        interrupted = manager.find_interrupted_tasks()
        
        assert len(interrupted) == 2
        task_ids = [t.task_id for t in interrupted]
        assert task1.task_id in task_ids
        assert task2.task_id in task_ids
    
    def test_get_statistics(self, temp_dir):
        """测试获取统计信息"""
        manager = TaskPersistenceManager(temp_dir)
        
        # 创建不同类型和状态的任务
        task1 = manager.create_task("research", {"query": "1"})
        task2 = manager.create_task("research", {"query": "2"})
        task3 = manager.create_task("analysis", {"data": "3"})
        
        manager.save_task(task1)
        manager.save_task(task2)
        manager.save_task(task3)
        
        manager.update_task_state(task1.task_id, TaskState.COMPLETED)
        manager.update_task_state(task2.task_id, TaskState.RUNNING)
        
        stats = manager.get_statistics()
        
        assert stats["total"] == 3
        assert stats["by_state"]["completed"] == 1
        assert stats["by_state"]["running"] == 1
        assert stats["by_type"]["research"] == 2
        assert stats["by_type"]["analysis"] == 1


class TestTaskPersistenceManagerEdgeCases:
    """TaskPersistenceManager 边缘情况测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录 fixture"""
        dir_path = tempfile.mkdtemp()
        yield dir_path
        shutil.rmtree(dir_path, ignore_errors=True)
    
    def test_corrupted_task_file(self, temp_dir):
        """测试损坏的任务文件"""
        manager = TaskPersistenceManager(temp_dir)
        
        # 写入损坏的 JSON 文件
        task_file = manager.tasks_dir / "corrupted.json"
        with open(task_file, 'w', encoding='utf-8') as f:
            f.write("not valid json {{{")
        
        # 加载应该返回 None
        loaded = manager.load_task("corrupted")
        assert loaded is None
    
    def test_state_history_tracking(self, temp_dir):
        """测试状态历史追踪"""
        manager = TaskPersistenceManager(temp_dir, track_history=True)
        
        task = manager.create_task("research", {"query": "test"})
        manager.save_task(task)
        
        # 多次更新状态
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        manager.update_task_state(task.task_id, TaskState.PAUSED)
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        # 获取历史
        history = manager.get_state_history(task.task_id)
        
        assert len(history) == 3
        assert history[0]["state"] == "running"
        assert history[1]["state"] == "paused"
        assert history[2]["state"] == "running"
    
    def test_empty_directory_recovery(self, temp_dir):
        """测试空目录恢复"""
        manager = TaskPersistenceManager(temp_dir)
        
        tasks = manager.recover_all_tasks()
        assert tasks == []
    
    def test_concurrent_save(self, temp_dir):
        """测试并发保存（简单模拟）"""
        import threading
        
        manager = TaskPersistenceManager(temp_dir)
        results = []
        
        def save_tasks():
            for i in range(5):
                task = manager.create_task("test", {"index": i})
                manager.save_task(task)
                results.append(task.task_id)
        
        threads = [threading.Thread(target=save_tasks) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 验证所有任务都被保存
        all_tasks = manager.recover_all_tasks()
        assert len(all_tasks) == 10


class TestIntegration:
    """集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录 fixture"""
        dir_path = tempfile.mkdtemp()
        yield dir_path
        shutil.rmtree(dir_path, ignore_errors=True)
    
    def test_full_task_lifecycle(self, temp_dir):
        """测试完整任务生命周期"""
        manager = TaskPersistenceManager(temp_dir, track_history=True)
        
        # 创建任务
        task = manager.create_task(
            "research",
            {"query": "测试查询", "options": {"depth": 3}}
        )
        manager.save_task(task)
        
        # 启动任务
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        # 创建检查点
        manager.create_checkpoint(task.task_id, "step_1", 1, 3, {"partial": "result1"})
        manager.create_checkpoint(task.task_id, "step_2", 2, 3, {"partial": "result2"})
        
        # 更新进度
        manager.update_task_state(task.task_id, TaskState.RUNNING, progress=0.67)
        
        # 完成
        manager.update_task_state(
            task.task_id,
            TaskState.COMPLETED,
            progress=1.0,
            message="研究完成"
        )
        
        # 验证最终状态
        loaded = manager.load_task(task.task_id)
        assert loaded.status.state == TaskState.COMPLETED
        assert loaded.status.progress == 1.0
        assert len(loaded.checkpoints) == 2
        
        # 验证历史
        history = manager.get_state_history(task.task_id)
        assert len(history) >= 3
        
        # 验证统计
        stats = manager.get_statistics()
        assert stats["total"] == 1
        assert stats["by_state"]["completed"] == 1
    
    def test_crash_recovery_simulation(self, temp_dir):
        """测试崩溃恢复模拟"""
        # 第一阶段：创建任务
        manager1 = TaskPersistenceManager(temp_dir)
        task = manager1.create_task("research", {"query": "important"})
        manager1.save_task(task)
        manager1.update_task_state(task.task_id, TaskState.RUNNING)
        
        # 模拟崩溃：创建新的管理器实例
        manager2 = TaskPersistenceManager(temp_dir)
        
        # 恢复中断的任务
        interrupted = manager2.find_interrupted_tasks()
        assert len(interrupted) == 1
        
        recovered_task = interrupted[0]
        assert recovered_task.input_data == {"query": "important"}
        
        # 继续执行
        manager2.update_task_state(recovered_task.task_id, TaskState.COMPLETED)
        
        # 验证最终状态
        loaded = manager2.load_task(recovered_task.task_id)
        assert loaded.status.state == TaskState.COMPLETED