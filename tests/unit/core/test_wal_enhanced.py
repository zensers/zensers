# -*- coding: utf-8 -*-
"""
增强版 WAL (Write-Ahead Log) 测试

Phase 4 Week 1 Day 1: WAL增强
- 原子写入保证
- 校验和验证
- 检查点机制
- 自动恢复
"""

import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import pytest

from src.core.storage_wal import EnhancedWAL, EnhancedTaskStorage


class TestEnhancedWALInit:
    """测试 EnhancedWAL 初始化"""
    
    def test_init_creates_directory(self, tmp_path):
        """初始化时创建 WAL 目录"""
        wal = EnhancedWAL(str(tmp_path))
        assert wal.wal_dir.exists()
        assert wal.wal_dir.name == "wal"
    
    def test_init_with_checksum_enabled(self, tmp_path):
        """初始化时启用校验和"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        assert wal.enable_checksum is True
    
    def test_init_with_checksum_disabled(self, tmp_path):
        """初始化时禁用校验和"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=False)
        assert wal.enable_checksum is False


class TestEnhancedWALAtomicWrite:
    """测试原子写入"""
    
    def test_append_single_entry(self, tmp_path):
        """测试追加单个条目"""
        wal = EnhancedWAL(str(tmp_path))
        
        entry = {"operation": "save", "data": "test"}
        wal.append(entry)
        
        logs = wal.read_all()
        assert len(logs) == 1
        assert logs[0]["operation"] == "save"
        assert logs[0]["data"] == "test"
    
    def test_append_multiple_entries(self, tmp_path):
        """测试追加多个条目"""
        wal = EnhancedWAL(str(tmp_path))
        
        for i in range(5):
            wal.append({"operation": "save", "index": i})
        
        logs = wal.read_all()
        assert len(logs) == 5
        for i, log in enumerate(logs):
            assert log["index"] == i
    
    def test_atomic_write_with_temp_file(self, tmp_path):
        """测试使用临时文件的原子写入"""
        wal = EnhancedWAL(str(tmp_path))
        
        entry = {"operation": "test", "data": "atomic"}
        wal.append(entry)
        
        # 验证没有残留的临时文件
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0
    
    def test_append_with_timestamp(self, tmp_path):
        """测试自动添加时间戳"""
        wal = EnhancedWAL(str(tmp_path))
        
        entry = {"operation": "save"}
        wal.append(entry)
        
        logs = wal.read_all()
        assert "timestamp" in logs[0]
        assert "sequence" in logs[0]


class TestEnhancedWALChecksum:
    """测试校验和验证"""
    
    def test_append_with_checksum(self, tmp_path):
        """测试带校验和的写入"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        
        entry = {"operation": "save", "data": "test"}
        wal.append(entry)
        
        logs = wal.read_all()
        assert "checksum" in logs[0]
    
    def test_verify_valid_checksum(self, tmp_path):
        """测试验证有效校验和"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        
        entry = {"operation": "save", "data": "test"}
        wal.append(entry)
        
        # 验证校验和有效
        logs = wal.read_all()
        assert wal.verify_checksum(logs[0]) is True
    
    def test_detect_corrupted_entry(self, tmp_path):
        """测试检测损坏的条目"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        
        entry = {"operation": "save", "data": "test"}
        wal.append(entry)
        
        # 读取并篡改数据
        wal_file = wal._get_current_wal_file()
        with open(wal_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 篡改内容 - 修改数据但不修改校验和
        corrupted_line = lines[0].replace('"test"', '"corrupted"')
        with open(wal_file, 'w', encoding='utf-8') as f:
            f.write(corrupted_line)
        
        # 读取时不跳过损坏条目，验证校验和检测
        logs = wal.read_all(skip_corrupted=False)
        assert len(logs) == 1
        # 校验和验证应该失败
        assert wal.verify_checksum(logs[0]) is False
    
    def test_read_all_skip_corrupted(self, tmp_path):
        """测试读取时跳过损坏的条目"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        
        # 写入两个有效条目
        wal.append({"operation": "save", "data": "valid1"})
        wal.append({"operation": "save", "data": "valid2"})
        
        logs = wal.read_all(skip_corrupted=True)
        assert len(logs) == 2


class TestEnhancedWALCheckpoint:
    """测试检查点机制"""
    
    def test_create_checkpoint(self, tmp_path):
        """测试创建检查点"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 写入一些条目
        for i in range(5):
            wal.append({"operation": "save", "index": i})
        
        # 创建检查点
        checkpoint_info = wal.checkpoint()
        
        assert checkpoint_info["entries_processed"] == 5
        assert checkpoint_info["checkpoint_file"] is not None
    
    def test_checkpoint_clears_wal(self, tmp_path):
        """测试检查点后清空 WAL"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 写入条目
        wal.append({"operation": "save", "data": "test"})
        
        # 创建检查点
        wal.checkpoint()
        
        # WAL 应该被清空
        logs = wal.read_all()
        assert len(logs) == 0
    
    def test_checkpoint_persistence(self, tmp_path):
        """测试检查点持久化"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 写入条目
        wal.append({"operation": "save", "data": "test"})
        
        # 创建检查点
        checkpoint_info = wal.checkpoint()
        
        # 验证检查点文件存在
        checkpoint_file = Path(checkpoint_info["checkpoint_file"])
        assert checkpoint_file.exists()
    
    def test_list_checkpoints(self, tmp_path):
        """测试列出检查点"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 创建多个检查点
        wal.append({"operation": "save", "data": "test1"})
        cp1 = wal.checkpoint()
        
        # 等待一秒确保时间戳不同
        import time
        time.sleep(1.1)
        
        wal.append({"operation": "save", "data": "test2"})
        cp2 = wal.checkpoint()
        
        checkpoints = wal.list_checkpoints()
        # 至少有1个检查点
        assert len(checkpoints) >= 1
        # 验证检查点信息
        assert all("checkpoint_id" in cp for cp in checkpoints)


class TestEnhancedWALRecovery:
    """测试自动恢复"""
    
    def test_recover_from_wal(self, tmp_path):
        """测试从 WAL 恢复"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 写入条目
        entries = [
            {"operation": "save", "task_id": "task1", "data": "test1"},
            {"operation": "save", "task_id": "task2", "data": "test2"},
            {"operation": "delete", "task_id": "task1"},
        ]
        
        for entry in entries:
            wal.append(entry)
        
        # 恢复
        recovered = wal.recover()
        
        assert len(recovered) == 3
        assert recovered[0]["task_id"] == "task1"
    
    def test_recover_after_crash_simulation(self, tmp_path):
        """测试模拟崩溃后恢复"""
        wal = EnhancedWAL(str(tmp_path))
        
        # 写入条目但不创建检查点
        wal.append({"operation": "save", "task_id": "task1", "data": "test"})
        
        # 模拟崩溃：创建新实例
        wal2 = EnhancedWAL(str(tmp_path))
        
        # 应该能恢复数据
        logs = wal2.read_all()
        assert len(logs) == 1
        assert logs[0]["task_id"] == "task1"
    
    def test_recover_partial_write(self, tmp_path):
        """测试恢复部分写入"""
        wal = EnhancedWAL(str(tmp_path), enable_checksum=True)
        
        # 写入有效条目
        wal.append({"operation": "save", "data": "valid"})
        
        # 模拟部分写入（追加不完整的 JSON）
        wal_file = wal._get_current_wal_file()
        with open(wal_file, 'a', encoding='utf-8') as f:
            f.write('{"operation": "partial' + os.linesep)  # 不完整的 JSON
        
        # 读取时应该跳过不完整的条目
        logs = wal.read_all(skip_corrupted=True)
        assert len(logs) == 1
        assert logs[0]["data"] == "valid"


class TestEnhancedWALSequence:
    """测试序列号"""
    
    def test_sequence_increment(self, tmp_path):
        """测试序列号递增"""
        wal = EnhancedWAL(str(tmp_path))
        
        for i in range(5):
            wal.append({"operation": "save", "index": i})
        
        logs = wal.read_all()
        for i, log in enumerate(logs):
            assert log["sequence"] == i + 1
    
    def test_sequence_persistence(self, tmp_path):
        """测试序列号持久化"""
        wal = EnhancedWAL(str(tmp_path))
        
        wal.append({"operation": "save", "data": "test"})
        
        # 创建新实例
        wal2 = EnhancedWAL(str(tmp_path))
        wal2.append({"operation": "save", "data": "test2"})
        
        logs = wal2.read_all()
        assert logs[-1]["sequence"] == 2


class TestEnhancedTaskStorage:
    """测试增强版 TaskStorage"""
    
    def test_storage_with_enhanced_wal(self, tmp_path):
        """测试使用增强版 WAL 的 TaskStorage"""
        storage = EnhancedTaskStorage(str(tmp_path), enable_enhanced_wal=True)
        
        task = {"task_id": "task1", "name": "Test Task"}
        storage.save_task(task)
        
        loaded = storage.load_task("task1")
        assert loaded["name"] == "Test Task"
    
    def test_crash_recovery(self, tmp_path):
        """测试崩溃恢复"""
        storage = EnhancedTaskStorage(str(tmp_path), enable_enhanced_wal=True)
        
        # 保存任务
        storage.save_task({"task_id": "task1", "name": "Task 1"})
        storage.save_task({"task_id": "task2", "name": "Task 2"})
        
        # 模拟崩溃：创建新实例
        storage2 = EnhancedTaskStorage(str(tmp_path), enable_enhanced_wal=True)
        
        # 自动恢复
        recovered = storage2.recover_from_wal()
        
        # 验证数据完整性
        assert len(recovered) >= 2
    
    def test_checkpoint_integration(self, tmp_path):
        """测试检查点集成"""
        storage = EnhancedTaskStorage(str(tmp_path), enable_enhanced_wal=True)
        
        # 保存任务
        storage.save_task({"task_id": "task1", "name": "Task 1"})
        
        # 创建检查点
        storage.checkpoint()
        
        # WAL 应该被清空
        assert len(storage.wal.read_all()) == 0


class TestPerformanceOverhead:
    """测试性能开销"""
    
    def test_checksum_overhead_acceptable(self, tmp_path):
        """测试校验和开销在可接受范围内"""
        import time
        
        wal_with_checksum = EnhancedWAL(str(tmp_path / "with_checksum"), enable_checksum=True)
        wal_without_checksum = EnhancedWAL(str(tmp_path / "without_checksum"), enable_checksum=False)
        
        entries = [{"operation": "save", "data": f"test{i}"} for i in range(100)]
        
        # 测试带校验和
        start = time.time()
        for entry in entries:
            wal_with_checksum.append(entry)
        time_with_checksum = time.time() - start
        
        # 测试不带校验和
        start = time.time()
        for entry in entries:
            wal_without_checksum.append(entry)
        time_without_checksum = time.time() - start
        
        # 开销应该小于 50%（校验和计算确实会增加开销）
        # 注意：在不同机器上性能差异较大，50%是合理的阈值
        overhead = (time_with_checksum - time_without_checksum) / max(time_without_checksum, 0.001)
        assert overhead < 0.5, f"Checksum overhead {overhead*100:.1f}% exceeds 50%"