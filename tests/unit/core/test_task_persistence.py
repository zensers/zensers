# -*- coding: utf-8 -*-
"""
任务持久化测试

Phase 4 Week 1 Day 2: 任务持久化
- 任务状态持久化
- 增量保存
- 恢复机制
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime
import pytest
import asyncio

from src.core.task_persistence import (
    TaskState,
    TaskStatus,
    PersistentTask,
    TaskPersistenceManager,
    TaskCheckpoint,
)


class TestTaskState:
    """测试任务状态枚举"""
    
    def test_task_state_values(self):
        """测试任务状态值"""
        assert TaskState.CREATED.value == "created"
        assert TaskState.INITIALIZING.value == "initializing"
        assert TaskState.RUNNING.value == "running"
        assert TaskState.PAUSED.value == "paused"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
    
    def test_task_state_is_terminal(self):
        """测试终止状态判断"""
        assert TaskState.COMPLETED.is_terminal() is True
        assert TaskState.FAILED.is_terminal() is True
        assert TaskState.RUNNING.is_terminal() is False


class TestTaskStatus:
    """测试任务状态信息"""
    
    def test_task_status_creation(self):
        """测试任务状态创建"""
        status = TaskStatus(
            task_id="task_001",
            state=TaskState.RUNNING,
            progress=0.5,
            message="Processing data",
        )
        
        assert status.task_id == "task_001"
        assert status.state == TaskState.RUNNING
        assert status.progress == 0.5
        assert status.message == "Processing data"
    
    def test_task_status_to_dict(self):
        """测试任务状态序列化"""
        status = TaskStatus(
            task_id="task_001",
            state=TaskState.RUNNING,
            progress=0.5,
        )
        
        data = status.to_dict()
        
        assert data["task_id"] == "task_001"
        assert data["state"] == "running"
        assert data["progress"] == 0.5
    
    def test_task_status_from_dict(self):
        """测试任务状态反序列化"""
        data = {
            "task_id": "task_001",
            "state": "running",
            "progress": 0.5,
            "message": "Test",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        status = TaskStatus.from_dict(data)
        
        assert status.task_id == "task_001"
        assert status.state == TaskState.RUNNING


class TestPersistentTask:
    """测试持久化任务"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={"query": "test"},
        )
        
        assert task.task_id == "task_001"
        assert task.task_type == "research"
        assert task.status.state == TaskState.CREATED
    
    def test_task_start(self):
        """测试任务启动"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={},
        )
        
        task.start()
        
        assert task.status.state == TaskState.RUNNING
    
    def test_task_complete(self):
        """测试任务完成"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={},
        )
        
        task.start()
        task.complete({"result": "success"})
        
        assert task.status.state == TaskState.COMPLETED
        assert task.result == {"result": "success"}
    
    def test_task_fail(self):
        """测试任务失败"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={},
        )
        
        task.start()
        task.fail("Something went wrong")
        
        assert task.status.state == TaskState.FAILED
        assert task.error == "Something went wrong"
    
    def test_task_pause_and_resume(self):
        """测试任务暂停和恢复"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={},
        )
        
        task.start()
        task.pause()
        
        assert task.status.state == TaskState.PAUSED
        
        task.resume()
        
        assert task.status.state == TaskState.RUNNING
    
    def test_task_to_dict(self):
        """测试任务序列化"""
        task = PersistentTask(
            task_id="task_001",
            task_type="research",
            input_data={"query": "test"},
        )
        
        data = task.to_dict()
        
        assert data["task_id"] == "task_001"
        assert data["task_type"] == "research"
        assert "status" in data
        assert "input_data" in data
    
    def test_task_from_dict(self):
        """测试任务反序列化"""
        data = {
            "task_id": "task_001",
            "task_type": "research",
            "input_data": {"query": "test"},
            "output_data": None,
            "status": {
                "task_id": "task_001",
                "state": "running",
                "progress": 0.3,
            },
            "checkpoints": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        task = PersistentTask.from_dict(data)
        
        assert task.task_id == "task_001"
        assert task.status.state == TaskState.RUNNING


class TestTaskCheckpoint:
    """测试任务检查点"""
    
    def test_checkpoint_creation(self):
        """测试检查点创建"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_001",
            step_name="data_collection",
            step_index=1,
            total_steps=5,
            data={"collected": 100},
        )
        
        assert checkpoint.checkpoint_id == "cp_001"
        assert checkpoint.step_name == "data_collection"
        assert checkpoint.progress == 0.2  # 1/5
    
    def test_checkpoint_to_dict(self):
        """测试检查点序列化"""
        checkpoint = TaskCheckpoint(
            checkpoint_id="cp_001",
            task_id="task_001",
            step_name="data_collection",
            step_index=1,
            total_steps=5,
            data={},
        )
        
        data = checkpoint.to_dict()
        
        assert data["checkpoint_id"] == "cp_001"
        assert data["progress"] == 0.2


class TestTaskPersistenceManager:
    """测试任务持久化管理器"""
    
    def test_manager_creation(self, tmp_path):
        """测试管理器创建"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        assert manager.storage_path.exists()
    
    def test_create_task(self, tmp_path):
        """测试创建任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        task = manager.create_task(
            task_type="research",
            input_data={"query": "test"},
        )
        
        assert task.task_id is not None
        assert task.status.state == TaskState.CREATED
    
    def test_save_and_load_task(self, tmp_path):
        """测试保存和加载任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建并保存任务
        task = manager.create_task(
            task_type="research",
            input_data={"query": "test"},
        )
        manager.save_task(task)
        
        # 加载任务
        loaded = manager.load_task(task.task_id)
        
        assert loaded is not None
        assert loaded.task_id == task.task_id
        assert loaded.task_type == "research"
    
    def test_update_task_state(self, tmp_path):
        """测试更新任务状态"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        
        # 更新状态
        manager.update_task_state(task.task_id, TaskState.RUNNING, progress=0.3)
        
        # 加载验证
        loaded = manager.load_task(task.task_id)
        
        assert loaded.status.state == TaskState.RUNNING
        assert loaded.status.progress == 0.3
    
    def test_create_checkpoint(self, tmp_path):
        """测试创建检查点"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        
        # 创建检查点
        checkpoint = manager.create_checkpoint(
            task_id=task.task_id,
            step_name="data_collection",
            step_index=1,
            total_steps=5,
            data={"items": 100},
        )
        
        assert checkpoint is not None
        assert checkpoint.step_name == "data_collection"
        
        # 加载任务验证检查点
        loaded = manager.load_task(task.task_id)
        assert len(loaded.checkpoints) == 1
    
    def test_restore_from_checkpoint(self, tmp_path):
        """测试从检查点恢复"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建任务和检查点
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        
        checkpoint = manager.create_checkpoint(
            task_id=task.task_id,
            step_name="data_collection",
            step_index=2,
            total_steps=5,
            data={"items": 200},
        )
        
        # 从检查点恢复
        restored = manager.restore_from_checkpoint(task.task_id, checkpoint.checkpoint_id)
        
        assert restored is not None
        assert restored["step_index"] == 2
        assert restored["data"]["items"] == 200
    
    def test_list_active_tasks(self, tmp_path):
        """测试列出活跃任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建多个任务
        task1 = manager.create_task(task_type="research", input_data={})
        task2 = manager.create_task(task_type="survey", input_data={})
        
        manager.save_task(task1)
        manager.save_task(task2)
        
        # 更新状态
        manager.update_task_state(task1.task_id, TaskState.RUNNING)
        manager.update_task_state(task2.task_id, TaskState.COMPLETED)
        
        # 列出活跃任务
        active = manager.list_active_tasks()
        
        assert len(active) == 1
        assert active[0].task_id == task1.task_id
    
    def test_cleanup_completed_tasks(self, tmp_path):
        """测试清理已完成任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建任务
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        manager.update_task_state(task.task_id, TaskState.COMPLETED)
        
        # 清理
        cleaned = manager.cleanup_completed_tasks(keep_days=0)
        
        assert cleaned == 1
    
    def test_recover_all_tasks(self, tmp_path):
        """测试恢复所有任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建多个任务
        task1 = manager.create_task(task_type="research", input_data={})
        task2 = manager.create_task(task_type="survey", input_data={})
        
        manager.save_task(task1)
        manager.save_task(task2)
        
        # 创建新管理器实例（模拟重启）
        manager2 = TaskPersistenceManager(str(tmp_path))
        
        # 恢复所有任务
        recovered = manager2.recover_all_tasks()
        
        assert len(recovered) == 2


class TestIncrementalSave:
    """测试增量保存"""
    
    def test_incremental_state_changes(self, tmp_path):
        """测试增量状态变化保存"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        
        # 增量更新状态
        manager.update_task_state(task.task_id, TaskState.INITIALIZING)
        manager.update_task_state(task.task_id, TaskState.RUNNING, progress=0.1)
        manager.update_task_state(task.task_id, TaskState.RUNNING, progress=0.5)
        
        # 验证最终状态
        loaded = manager.load_task(task.task_id)
        
        assert loaded.status.state == TaskState.RUNNING
        assert loaded.status.progress == 0.5
    
    def test_state_history_tracking(self, tmp_path):
        """测试状态历史追踪"""
        manager = TaskPersistenceManager(str(tmp_path), track_history=True)
        
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        
        # 多次状态变更
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        manager.update_task_state(task.task_id, TaskState.PAUSED)
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        # 获取状态历史
        history = manager.get_state_history(task.task_id)
        
        assert len(history) >= 3


class TestCrashRecovery:
    """测试崩溃恢复"""
    
    def test_recover_running_tasks(self, tmp_path):
        """测试恢复运行中的任务"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建运行中的任务
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        # 模拟崩溃：创建新管理器
        manager2 = TaskPersistenceManager(str(tmp_path))
        
        # 检测运行中的任务
        running_tasks = manager2.find_interrupted_tasks()
        
        assert len(running_tasks) == 1
        assert running_tasks[0].task_id == task.task_id
    
    def test_recover_with_checkpoint(self, tmp_path):
        """测试带检查点的恢复"""
        manager = TaskPersistenceManager(str(tmp_path))
        
        # 创建任务和检查点
        task = manager.create_task(task_type="research", input_data={})
        manager.save_task(task)
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        checkpoint = manager.create_checkpoint(
            task_id=task.task_id,
            step_name="step_2",
            step_index=2,
            total_steps=5,
            data={"progress": "midway"},
        )
        
        # 模拟崩溃恢复
        manager2 = TaskPersistenceManager(str(tmp_path))
        recovered_task = manager2.load_task(task.task_id)
        
        # 应该能从检查点恢复
        assert len(recovered_task.checkpoints) == 1
        assert recovered_task.checkpoints[0].step_name == "step_2"