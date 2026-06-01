# -*- coding: utf-8 -*-
"""
历史压缩器测试

测试 HistoryCompressor 的核心功能：
- 历史差分存储
- 压缩策略（保留最近5步完整 + 中间10步摘要 + 更早归档）
- 大小限制
- 归档管理
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
import json
import gzip
import tempfile
from pathlib import Path


class TestHistoryCompressorInit:
    """测试 HistoryCompressor 初始化"""
    
    def test_init_with_required_params(self):
        """测试必需参数初始化"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_20260408_001"
        )
        
        assert compressor.user_id == "user_001"
        assert compressor.session_id == "sess_20260408_001"
        
    def test_init_with_custom_params(self):
        """测试自定义参数初始化"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001",
            max_full_steps=10,  # 自定义保留完整记录数
            max_summary_steps=20,  # 自定义摘要记录数
            size_limit_kb=100  # 自定义大小限制
        )
        
        assert compressor.max_full_steps == 10
        assert compressor.max_summary_steps == 20
        assert compressor.size_limit_kb == 100
        
    def test_init_with_archive_path(self):
        """测试归档路径初始化"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            assert compressor.archive_path == Path(tmp_dir)


class TestHistoryCompressorCompression:
    """测试压缩功能"""
    
    def test_compress_empty_history(self):
        """测试空历史压缩"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001"
        )
        
        result = compressor.compress([])
        
        assert result["history"] == []
        assert result["archived"] == False
        assert result["compression_ratio"] == 0.0
        
    def test_compress_small_history_no_compression(self):
        """测试小历史不压缩"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001"
        )
        
        # 创建10步历史（少于压缩阈值15）
        history = self._create_mock_history(10)
        
        result = compressor.compress(history)
        
        # 不应该压缩，返回原历史
        assert len(result["history"]) == 10
        assert result["archived"] == False
        
    def test_compress_medium_history_with_summary(self):
        """测试中等历史压缩（生成摘要）"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001"
        )
        
        # 创建20步历史（触发压缩）
        history = self._create_mock_history(20)
        
        result = compressor.compress(history)
        
        # 应该压缩：最近5步完整 + 中间摘要
        assert len(result["history"]) <= 6  # 5步完整 + 1个摘要
        assert result["archived"] == False  # 没有归档
        
    def test_compress_large_history_with_archive(self):
        """测试大历史压缩（触发归档）"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            # 创建50步历史（触发归档）
            history = self._create_mock_history(50)
            
            result = compressor.compress(history)
            
            # 应该压缩：最近5步完整 + 中间摘要 + 早期归档
            assert len(result["history"]) <= 6  # 5步完整 + 1个摘要
            assert result["archived"] == True  # 触发归档
            assert "archive_path" in result
            
    def test_compress_preserves_recent_full_steps(self):
        """测试压缩保留最近完整记录"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001",
            max_full_steps=5
        )
        
        history = self._create_mock_history(25)
        
        result = compressor.compress(history)
        
        # 检查最近5步保留完整
        recent = result["history"][-5:]
        for step in recent:
            assert step.get("type") == "full" or "state" in step
            
    def _create_mock_history(self, count: int) -> List[Dict[str, Any]]:
        """创建模拟历史记录"""
        history = []
        for i in range(count):
            history.append({
                "step": i + 1,
                "state": f"state_{i + 1}",
                "timestamp": datetime.now().isoformat(),
                "summary": f"步骤 {i + 1}: 执行操作...",
                "data": {
                    "action": "process",
                    "input": f"input_{i}",
                    "output": f"output_{i}"
                }
            })
        return history


class TestHistoryCompressorSizeLimit:
    """测试大小限制"""
    
    def test_check_size_within_limit(self):
        """测试大小在限制内"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001",
            size_limit_kb=50
        )
        
        # 创建小历史
        history = self._create_small_history()
        
        size_kb = compressor.calculate_size(history)
        
        assert size_kb < 50
        assert compressor.is_within_limit(history) == True
        
    def test_check_size_exceeds_limit(self):
        """测试大小超限"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001",
            size_limit_kb=50
        )
        
        # 创建大历史
        history = self._create_large_history(100)
        
        size_kb = compressor.calculate_size(history)
        
        assert size_kb > 50
        assert compressor.is_within_limit(history) == False
        
    def test_auto_compress_when_exceeds_limit(self):
        """测试超限自动压缩"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001",
            size_limit_kb=50
        )
        
        # 创建超限历史
        history = self._create_large_history(100)
        
        # 自动压缩
        result = compressor.compress_if_needed(history)
        
        # 压缩后应该在限制内
        assert compressor.is_within_limit(result) == True
        
    def _create_small_history(self) -> List[Dict[str, Any]]:
        """创建小历史"""
        return [{"step": i, "data": "small"} for i in range(10)]
        
    def _create_large_history(self, count: int) -> List[Dict[str, Any]]:
        """创建大历史"""
        history = []
        for i in range(count):
            history.append({
                "step": i,
                "data": "x" * 1000,  # 大数据
                "details": "y" * 500
            })
        return history


class TestHistoryCompressorArchive:
    """测试归档功能"""
    
    def test_archive_old_history(self):
        """测试归档旧历史"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            old_history = self._create_mock_history(30)
            
            archive_path = compressor.archive_history(old_history)
            
            assert archive_path is not None
            assert Path(archive_path).exists()
            
    def test_archive_with_compression(self):
        """测试归档使用压缩"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            old_history = self._create_mock_history(30)
            
            archive_path = compressor.archive_history(old_history)
            
            # 检查是否是压缩文件
            assert archive_path.endswith(".gz")
            
            # 检查可以解压
            with gzip.open(archive_path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
                assert len(data) == 30
                
    def test_restore_from_archive(self):
        """测试从归档恢复"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            old_history = self._create_mock_history(30)
            
            # 归档
            archive_path = compressor.archive_history(old_history)
            
            # 恢复
            restored = compressor.restore_from_archive(archive_path)
            
            assert len(restored) == 30
            assert restored[0]["step"] == 1
            
    def _create_mock_history(self, count: int) -> List[Dict[str, Any]]:
        """创建模拟历史"""
        return [{"step": i + 1, "data": f"step_{i + 1}"} for i in range(count)]


class TestHistoryCompressorIntegration:
    """集成测试"""
    
    def test_full_compression_cycle(self):
        """测试完整压缩周期"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            compressor = HistoryCompressor(
                user_id="user_001",
                session_id="sess_001",
                archive_path=tmp_dir
            )
            
            # 创建大量历史
            history = self._create_mock_history(100)
            
            # 第一次压缩
            result1 = compressor.compress(history)
            
            # 继续添加历史
            compressed_history = result1["history"]
            for i in range(101, 150):
                compressed_history.append({
                    "step": i,
                    "state": f"state_{i}",
                    "summary": f"步骤 {i}"
                })
            
            # 第二次压缩
            result2 = compressor.compress(compressed_history)
            
            # 验证压缩效果
            assert compressor.is_within_limit(result2["history"])
            
    def test_compression_ratio_calculation(self):
        """测试压缩率计算"""
        from src.core.memory.compressor.history_compressor import HistoryCompressor
        
        compressor = HistoryCompressor(
            user_id="user_001",
            session_id="sess_001"
        )
        
        original = self._create_mock_history(50)
        compressed = compressor.compress(original)
        
        ratio = compressor.compression_ratio(original, compressed["history"])
        
        # 压缩率应该 > 50%
        assert ratio >= 0.5
        
    def _create_mock_history(self, count: int) -> List[Dict[str, Any]]:
        """创建模拟历史"""
        history = []
        for i in range(count):
            history.append({
                "step": i + 1,
                "state": f"state_{i + 1}",
                "timestamp": datetime.now().isoformat(),
                "summary": f"步骤 {i + 1}: 执行操作",
                "data": {"key": f"value_{i}"}
            })
        return history