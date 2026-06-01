# -*- coding: utf-8 -*-
"""
PhaseOrchestrator持久化功能单元测试

测试新增的JSON持久化方法：
- _sanitize_aspect
- _atomic_write_json
- _save_agent_result
- _save_phase_meta
- _get_previous_phase_data
- _save_input_refs
- _save_requirement
- _get_phase_refs
- _prepare_phase_input_with_persistence
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from src.core.analysis.phase_definition import AnalysisPhase
from src.core.analysis.phase_orchestrator import PhaseOrchestrator, PhaseOrchestratorConfig


class TestSanitizeAspect:
    """测试aspect名称清理"""
    
    def test_normal_aspect(self):
        """测试正常aspect名称"""
        orchestrator = PhaseOrchestrator()
        
        assert orchestrator._sanitize_aspect("market_size") == "market_size"
        assert orchestrator._sanitize_aspect("竞争格局") == "竞争格局"
        assert orchestrator._sanitize_aspect("tech-trend") == "tech-trend"
    
    def test_aspect_with_special_chars(self):
        """测试包含特殊字符的aspect"""
        orchestrator = PhaseOrchestrator()
        
        # 斜杠替换
        assert orchestrator._sanitize_aspect("market/size") == "market_size"
        assert orchestrator._sanitize_aspect("market\\size") == "market_size"
        
        # 空格替换
        assert orchestrator._sanitize_aspect("market size") == "market_size"
    
    def test_empty_aspect(self):
        """测试空字符串aspect"""
        orchestrator = PhaseOrchestrator()
        
        assert orchestrator._sanitize_aspect("") == "default"
        assert orchestrator._sanitize_aspect("   ") == "default"
    
    def test_long_aspect(self):
        """测试超长aspect"""
        orchestrator = PhaseOrchestrator()
        
        long_aspect = "a" * 200
        result = orchestrator._sanitize_aspect(long_aspect)
        assert len(result) == 100


class TestAtomicWriteJson:
    """测试原子写入JSON"""
    
    def test_write_success(self, tmp_path):
        """测试成功写入"""
        orchestrator = PhaseOrchestrator()
        
        file_path = tmp_path / "test.json"
        data = {"key": "value", "number": 123}
        
        orchestrator._atomic_write_json(file_path, data)
        
        assert file_path.exists()
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded == data
    
    def test_overwrite_existing(self, tmp_path):
        """测试覆盖已存在文件"""
        orchestrator = PhaseOrchestrator()
        
        file_path = tmp_path / "test.json"
        
        # 第一次写入
        orchestrator._atomic_write_json(file_path, {"version": 1})
        
        # 第二次写入
        orchestrator._atomic_write_json(file_path, {"version": 2})
        
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded["version"] == 2
    
    def test_no_temp_file_left(self, tmp_path):
        """测试不留下临时文件"""
        orchestrator = PhaseOrchestrator()
        
        file_path = tmp_path / "test.json"
        orchestrator._atomic_write_json(file_path, {"test": "data"})
        
        # 不应该有.tmp文件
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestSaveAgentResult:
    """测试保存Agent结果"""
    
    def test_save_success(self, tmp_path, monkeypatch):
        """测试成功保存Agent结果"""
        # 修改输出目录
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        file_path = orchestrator._save_agent_result(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_COLLECTION,
            agent_id="agent_001",
            aspect="市场规模",
            input_data={"topic": "新能源汽车"},
            output_data={"data_points": [{"value": "100亿"}]},
        )
        
        assert file_path.exists()
        assert "agent_市场规模.json" in str(file_path)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["agent_id"] == "agent_001"
        assert data["aspect"] == "市场规模"
        assert data["output"]["data_points"][0]["value"] == "100亿"
    
    def test_save_with_metadata(self, tmp_path, monkeypatch):
        """测试带元数据保存"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        file_path = orchestrator._save_agent_result(
            task_id="test_task_001",
            phase=AnalysisPhase.DEEP_ANALYSIS,
            agent_id="agent_002",
            aspect="竞争格局",
            input_data={},
            output_data={"insights": ["insight1"]},
            metadata={
                "duration_seconds": 30,
                "quality_score": 0.9,
            }
        )
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["metadata"]["duration_seconds"] == 30
        assert data["metadata"]["quality_score"] == 0.9


class TestSavePhaseMeta:
    """测试保存阶段元数据"""
    
    def test_save_meta(self, tmp_path, monkeypatch):
        """测试保存阶段元数据"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        orchestrator._save_phase_meta(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_COLLECTION,
            meta={
                "phase": "data_collection",
                "status": "completed",
                "total_agents": 5,
                "successful_agents": 5,
            }
        )
        
        meta_path = tmp_path / "test_task_001" / "phase_1_collection" / "_phase_meta.json"
        assert meta_path.exists()
        
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["status"] == "completed"
        assert data["total_agents"] == 5


class TestGetPreviousPhaseData:
    """测试获取上一阶段数据"""
    
    def test_get_specific_aspect(self, tmp_path, monkeypatch):
        """测试获取特定aspect数据"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        # 先保存Phase 1数据
        orchestrator._save_agent_result(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_COLLECTION,
            agent_id="agent_001",
            aspect="市场规模",
            input_data={},
            output_data={"data_points": [{"value": "100亿"}]},
        )
        
        # 获取Phase 1数据
        prev_data = orchestrator._get_previous_phase_data(
            task_id="test_task_001",
            current_phase=AnalysisPhase.DATA_VALIDATION,
            aspect="市场规模"
        )
        
        assert prev_data["data_points"][0]["value"] == "100亿"
    
    def test_get_all_aspects(self, tmp_path, monkeypatch):
        """测试获取所有aspect数据"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        # 保存多个aspect数据
        for aspect in ["市场规模", "竞争格局", "技术趋势"]:
            orchestrator._save_agent_result(
                task_id="test_task_001",
                phase=AnalysisPhase.DATA_COLLECTION,
                agent_id=f"agent_{aspect}",
                aspect=aspect,
                input_data={},
                output_data={"aspect_data": aspect},
            )
        
        # 获取所有数据
        all_data = orchestrator._get_previous_phase_data(
            task_id="test_task_001",
            current_phase=AnalysisPhase.DATA_VALIDATION,
            aspect=None
        )
        
        assert len(all_data) == 3
        assert "市场规模" in all_data
        assert "竞争格局" in all_data
        assert "技术趋势" in all_data
    
    def test_get_nonexistent_data(self, tmp_path, monkeypatch):
        """测试获取不存在的数据"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        # 获取不存在的数据
        prev_data = orchestrator._get_previous_phase_data(
            task_id="test_task_001",
            current_phase=AnalysisPhase.DEEP_ANALYSIS,
            aspect="不存在的aspect"
        )
        
        assert prev_data == {}


class TestSaveInputRefs:
    """测试保存输入引用"""
    
    def test_save_refs(self, tmp_path, monkeypatch):
        """测试保存输入引用"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        orchestrator._save_input_refs(
            task_id="test_task_001",
            phase=AnalysisPhase.DEEP_ANALYSIS,
            refs={
                "市场规模": ["/path/to/agent_市场规模.json"],
                "竞争格局": ["/path/to/agent_竞争格局.json"],
            }
        )
        
        refs_path = tmp_path / "test_task_001" / "phase_3_analysis" / "_input_refs.json"
        assert refs_path.exists()
        
        with open(refs_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert "市场规模" in data
        assert "竞争格局" in data


class TestSaveRequirement:
    """测试保存需求信息"""
    
    def test_save_requirement(self, tmp_path, monkeypatch):
        """测试保存需求信息"""
        def mock_get_dir(self, task_id):
            dir_path = tmp_path / task_id
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            mock_get_dir
        )
        
        orchestrator = PhaseOrchestrator()
        
        requirement = {
            "task_id": "test_task_001",
            "topic": "新能源汽车市场研究",
            "aspects": ["市场规模", "竞争格局"],
        }
        
        orchestrator._save_requirement("test_task_001", requirement)
        
        req_path = tmp_path / "test_task_001" / "requirement.json"
        assert req_path.exists()
        
        with open(req_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["topic"] == "新能源汽车市场研究"


class TestGetPhaseRefs:
    """测试获取阶段引用"""
    
    def test_get_refs(self, tmp_path, monkeypatch):
        """测试获取阶段引用"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        # 保存多个Agent结果
        for aspect in ["市场规模", "竞争格局"]:
            orchestrator._save_agent_result(
                task_id="test_task_001",
                phase=AnalysisPhase.DATA_COLLECTION,
                agent_id=f"agent_{aspect}",
                aspect=aspect,
                input_data={},
                output_data={"data": aspect},
            )
        
        # 获取引用
        refs = orchestrator._get_phase_refs("test_task_001", AnalysisPhase.DATA_COLLECTION)
        
        assert len(refs) == 2
        assert "市场规模" in refs
        assert "竞争格局" in refs


class TestPreparePhaseInputWithPersistence:
    """测试准备阶段输入"""
    
    def test_prepare_with_persisted_data(self, tmp_path, monkeypatch):
        """测试从持久化数据准备输入"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        orchestrator = PhaseOrchestrator()
        
        # 保存Phase 1数据
        orchestrator._save_agent_result(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_COLLECTION,
            agent_id="agent_001",
            aspect="市场规模",
            input_data={},
            output_data={"data_points": [{"value": "100亿"}]},
        )
        
        # 准备Phase 2输入
        input_data = orchestrator._prepare_phase_input_with_persistence(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_VALIDATION,
            aspect="市场规模",
            requirement={}
        )
        
        assert "previous_phase_data" in input_data
        assert input_data["previous_phase_data"]["data_points"][0]["value"] == "100亿"
    
    def test_prepare_without_persisted_data(self, tmp_path, monkeypatch):
        """测试无持久化数据时回退到SharedMemory"""
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            lambda self, task_id: tmp_path / task_id
        )
        
        # 创建带SharedMemory的orchestrator
        from src.core.communication import SharedMemory
        shared_memory = SharedMemory()
        orchestrator = PhaseOrchestrator(shared_memory=shared_memory)
        
        # 在SharedMemory中设置数据
        shared_memory.set("phase_output.data_collection", {"test": "data"})
        
        # 准备输入
        input_data = orchestrator._prepare_phase_input_with_persistence(
            task_id="test_task_001",
            phase=AnalysisPhase.DATA_VALIDATION,
            aspect="市场规模",
            requirement={}
        )
        
        # 应该回退到SharedMemory
        assert "raw_data" in input_data


class TestIntegration:
    """集成测试"""
    
    def test_full_persistence_flow(self, tmp_path, monkeypatch):
        """测试完整持久化流程"""
        def mock_get_dir(self, task_id):
            dir_path = tmp_path / task_id
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        
        monkeypatch.setattr(
            PhaseOrchestrator,
            "_get_research_output_dir",
            mock_get_dir
        )
        
        orchestrator = PhaseOrchestrator()
        task_id = "integration_test_001"
        
        # 1. 保存需求
        orchestrator._save_requirement(task_id, {"topic": "测试研究"})
        
        # 2. 保存Phase 1 Agent结果
        for aspect in ["市场规模", "竞争格局"]:
            orchestrator._save_agent_result(
                task_id=task_id,
                phase=AnalysisPhase.DATA_COLLECTION,
                agent_id=f"agent_{aspect}",
                aspect=aspect,
                input_data={"topic": "测试研究"},
                output_data={"data": f"{aspect}数据"},
            )
        
        # 3. 保存Phase 1元数据
        orchestrator._save_phase_meta(
            task_id=task_id,
            phase=AnalysisPhase.DATA_COLLECTION,
            meta={"status": "completed", "total_agents": 2}
        )
        
        # 4. 获取Phase 1引用
        refs = orchestrator._get_phase_refs(task_id, AnalysisPhase.DATA_COLLECTION)
        
        # 5. 保存Phase 3输入引用
        orchestrator._save_input_refs(task_id, AnalysisPhase.DEEP_ANALYSIS, refs)
        
        # 6. 获取上一阶段数据（DEEP_ANALYSIS的上一阶段是DATA_VALIDATION）
        # 但我们保存的是DATA_COLLECTION，所以应该从DATA_VALIDATION获取
        # 先获取DATA_COLLECTION的数据
        prev_data = orchestrator._get_previous_phase_data(
            task_id=task_id,
            current_phase=AnalysisPhase.DATA_VALIDATION,
            aspect=None
        )
        
        # 验证
        assert len(prev_data) == 2
        
        # 检查目录结构
        research_dir = tmp_path / task_id
        assert (research_dir / "requirement.json").exists()
        assert (research_dir / "phase_1_collection").exists()
        assert (research_dir / "phase_1_collection" / "_phase_meta.json").exists()
        assert (research_dir / "phase_3_analysis" / "_input_refs.json").exists()
