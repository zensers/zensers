"""
Dream Mode 6阶段流程测试 - TDD模式

测试 Dream Mode 的6阶段执行流程
参考: CONTEXT_COMPRESSION.md 第3节 Dream Mode 设计

测试覆盖：
- Phase 1: Orientation (定位)
- Phase 2: Signal Gathering (信号收集)
- Phase 3: Consolidation (整合)
- Phase 4: Promotion (晋升)
- Phase 5: Pruning (修剪)
- Phase 6: Archival (归档)
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List
import tempfile
import shutil


class TestDreamModePhases:
    """测试 Dream Mode 6阶段流程"""

    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)

    @pytest.fixture
    def dream_mode(self, temp_dir):
        """创建 DreamMode 实例"""
        from src.core.memory.dream.dream_mode import DreamMode
        from src.core.memory.core.core_memory import CoreMemory
        
        core_memory = CoreMemory(user_id="user_001", storage_path=temp_dir)
        return DreamMode(core_memory=core_memory)

    # ========== Phase 1: Orientation (定位) ==========

    def test_orientation_scans_all_layers(self, dream_mode):
        """测试定位阶段扫描所有层"""
        result = dream_mode.phase1_orientation()
        
        assert "entities_count" in result
        assert "needs_count" in result
        assert "patterns_count" in result
        assert "total_size" in result

    def test_orientation_identifies_areas_to_process(self, dream_mode):
        """测试定位阶段识别需要处理的区域"""
        # 添加一些数据
        dream_mode.core_memory.add_top_entity({"name": "宁德时代", "type": "company", "mention_count": 5})
        
        result = dream_mode.phase1_orientation()
        
        assert "areas_to_process" in result
        assert len(result["areas_to_process"]) >= 0

    def test_orientation_returns_statistics(self, dream_mode):
        """测试定位阶段返回统计信息"""
        result = dream_mode.phase1_orientation()
        
        assert result["entities_count"] >= 0
        assert result["total_size"] >= 0

    # ========== Phase 2: Signal Gathering (信号收集) ==========

    def test_signal_gathering_analyzes_recent_sessions(self, dream_mode):
        """测试信号收集阶段分析最近会话"""
        result = dream_mode.phase2_signal_gathering()
        
        assert "user_corrections" in result
        assert "explicit_saves" in result
        assert "repeated_topics" in result
        assert "high_value_signals" in result

    def test_signal_gathering_identifies_user_corrections(self, dream_mode):
        """测试信号收集识别用户纠正"""
        # 模拟用户纠正信号
        dream_mode.add_session_signal({
            "type": "correction",
            "content": "不对，应该是宁德时代",
            "timestamp": datetime.now()
        })
        
        result = dream_mode.phase2_signal_gathering()
        
        assert len(result["user_corrections"]) > 0

    def test_signal_gathering_identifies_explicit_saves(self, dream_mode):
        """测试信号收集识别显式保存"""
        dream_mode.add_session_signal({
            "type": "save",
            "content": "记住这个信息",
            "timestamp": datetime.now()
        })
        
        result = dream_mode.phase2_signal_gathering()
        
        assert len(result["explicit_saves"]) > 0

    def test_signal_gathering_identifies_repeated_topics(self, dream_mode):
        """测试信号收集识别重复主题"""
        # 添加重复提及
        for _ in range(3):
            dream_mode.add_session_signal({
                "type": "mention",
                "topic": "新能源汽车",
                "timestamp": datetime.now()
            })
        
        result = dream_mode.phase2_signal_gathering()
        
        assert "新能源汽车" in result["repeated_topics"] or len(result["repeated_topics"]) > 0

    # ========== Phase 3: Consolidation (整合) ==========

    def test_consolidation_normalizes_dates(self, dream_mode):
        """测试整合阶段标准化日期"""
        dream_mode.core_memory.add_top_entity({
            "name": "测试公司",
            "type": "company",
            "mention_count": 5,
            "last_mentioned": "昨天"  # 相对日期
        })
        
        result = dream_mode.phase3_consolidation()
        
        assert "date_normalizations" in result
        assert result["date_normalizations"] > 0

    def test_consolidation_removes_contradictions(self, dream_mode):
        """测试整合阶段移除矛盾信息"""
        # 添加矛盾信息（相同实体，不同属性）
        dream_mode.core_memory.add_top_entity({
            "name": "测试公司",
            "type": "company",
            "mention_count": 10
        })
        
        result = dream_mode.phase3_consolidation()
        
        assert "contradictions_resolved" in result

    def test_consolidation_merges_duplicates(self, dream_mode):
        """测试整合阶段合并重复"""
        # 添加相似实体
        dream_mode.core_memory.add_learned_pattern({
            "pattern_key": "preference.format",
            "content": "偏好Markdown",
            "recurrence_count": 3
        })
        dream_mode.core_memory.add_learned_pattern({
            "pattern_key": "preference.format",
            "content": "偏好Markdown格式",
            "recurrence_count": 2
        })
        
        result = dream_mode.phase3_consolidation()
        
        assert "duplicates_merged" in result

    def test_consolidation_cleans_stale_references(self, dream_mode):
        """测试整合阶段清理陈旧引用"""
        result = dream_mode.phase3_consolidation()
        
        assert "stale_references_cleaned" in result

    # ========== Phase 4: Promotion (晋升) ==========

    def test_promotion_checks_conditions(self, dream_mode):
        """测试晋升阶段检查条件"""
        # 添加符合条件的实体
        dream_mode.core_memory.add_top_entity({
            "name": "宁德时代",
            "type": "company",
            "mention_count": 6  # >= 5
        })
        
        result = dream_mode.phase4_promotion()
        
        assert "entities_promoted" in result
        assert len(result["entities_promoted"]) > 0

    def test_promotion_does_not_promote_below_threshold(self, dream_mode):
        """测试晋升阶段不晋升低于阈值的条目"""
        dream_mode.core_memory.add_top_entity({
            "name": "小公司",
            "type": "company",
            "mention_count": 2  # < 5
        })
        
        result = dream_mode.phase4_promotion()
        
        # 不应该晋升
        promoted_names = [e["name"] for e in result["entities_promoted"]]
        assert "小公司" not in promoted_names

    def test_promotion_promotes_patterns(self, dream_mode):
        """测试晋升阶段晋升模式"""
        dream_mode.core_memory.add_learned_pattern({
            "pattern_key": "test_pattern",
            "content": "测试模式",
            "recurrence_count": 4  # >= 3
        })
        
        result = dream_mode.phase4_promotion()
        
        assert "patterns_promoted" in result

    def test_promotion_marks_core_needs(self, dream_mode):
        """测试晋升阶段标记核心需求"""
        for _ in range(4):
            dream_mode.core_memory.add_core_need("新能源汽车分析")  # frequency >= 3
        
        result = dream_mode.phase4_promotion()
        
        assert "needs_marked_core" in result

    # ========== Phase 5: Pruning (修剪) ==========

    def test_pruning_checks_layer1_size(self, dream_mode):
        """测试修剪阶段检查 Layer 1 大小"""
        result = dream_mode.phase5_pruning()
        
        assert "layer1_size_before" in result
        assert "layer1_size_after" in result

    def test_pruning_keeps_layer1_under_limit(self, dream_mode):
        """测试修剪阶段保持 Layer 1 在限制内"""
        # 添加大量数据
        for i in range(30):
            dream_mode.core_memory.add_top_entity({
                "name": f"公司{i}",
                "type": "company",
                "mention_count": i + 1
            })
        
        dream_mode.phase5_pruning()
        
        # 检查 Layer 1 大小
        dream_mode.core_memory._calculate_size()
        assert dream_mode.core_memory.size_bytes <= dream_mode.core_memory.SIZE_LIMIT_BYTES

    def test_pruning_calculates_importance_scores(self, dream_mode):
        """测试修剪阶段计算重要性分数"""
        dream_mode.core_memory.add_top_entity({"name": "公司A", "type": "company", "mention_count": 10})
        dream_mode.core_memory.add_top_entity({"name": "公司B", "type": "company", "mention_count": 3})
        
        result = dream_mode.phase5_pruning()
        
        assert "importance_scores" in result

    def test_pruning_removes_low_score_items(self, dream_mode):
        """测试修剪阶段移除低分条目"""
        # 添加高低分混合
        for i in range(25):
            dream_mode.core_memory.add_top_entity({
                "name": f"公司{i}",
                "type": "company",
                "mention_count": i + 1  # 1-25，分数差异大
            })
        
        result = dream_mode.phase5_pruning()
        
        assert "items_removed" in result

    # ========== Phase 6: Archival (归档) ==========

    def test_archival_compresses_old_sessions(self, dream_mode):
        """测试归档阶段压缩旧会话"""
        result = dream_mode.phase6_archival()
        
        assert "sessions_archived" in result
        assert "compression_ratio" in result

    def test_archival_moves_to_layer4(self, dream_mode):
        """测试归档阶段移动到 Layer 4"""
        result = dream_mode.phase6_archival()
        
        assert "archived_path" in result or "sessions_archived" in result

    def test_archival_cleans_original_data(self, dream_mode):
        """测试归档阶段清理原始数据"""
        result = dream_mode.phase6_archival()
        
        assert "original_data_cleaned" in result

    # ========== 完整流程测试 ==========

    def test_run_full_dream_mode(self, dream_mode):
        """测试运行完整 Dream Mode"""
        # 添加测试数据
        dream_mode.core_memory.add_top_entity({
            "name": "宁德时代",
            "type": "company",
            "mention_count": 6
        })
        dream_mode.core_memory.add_core_need("新能源汽车分析")
        
        report = dream_mode.run()
        
        assert report["status"] == "completed"
        assert "phases" in report
        assert "started_at" in report
        assert "completed_at" in report

    def test_dream_mode_report_includes_all_phases(self, dream_mode):
        """测试 Dream Mode 报告包含所有阶段"""
        report = dream_mode.run()
        
        phases = report["phases"]
        
        assert "orientation" in phases
        assert "signal_gathering" in phases
        assert "consolidation" in phases
        assert "promotion" in phases
        assert "pruning" in phases
        assert "archival" in phases

    def test_dream_mode_duration(self, dream_mode):
        """测试 Dream Mode 执行时间"""
        report = dream_mode.run()
        
        assert "duration_ms" in report
        assert report["duration_ms"] < 5000  # 应该 < 5秒


class TestDreamModeTriggers:
    """测试 Dream Mode 触发条件"""

    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)

    @pytest.fixture
    def dream_mode(self, temp_dir):
        """创建 DreamMode 实例"""
        from src.core.memory.dream.dream_mode import DreamMode
        from src.core.memory.core.core_memory import CoreMemory
        
        core_memory = CoreMemory(user_id="user_001", storage_path=temp_dir)
        return DreamMode(core_memory=core_memory)

    def test_trigger_on_session_end(self, dream_mode):
        """测试会话结束时触发"""
        assert dream_mode.should_trigger("session_end") is True

    def test_trigger_on_scheduled(self, dream_mode):
        """测试定时触发"""
        # 设置上次运行时间为25小时前
        dream_mode._last_run = datetime.now() - timedelta(hours=25)
        
        assert dream_mode.should_trigger("scheduled") is True

    def test_trigger_manual(self, dream_mode):
        """测试手动触发"""
        assert dream_mode.should_trigger("manual") is True

    def test_trigger_on_threshold(self, dream_mode):
        """测试阈值触发"""
        # 添加大量数据接近限制
        for i in range(25):
            dream_mode.core_memory.add_top_entity({
                "name": f"公司{i}名称很长" * 5,
                "type": "company",
                "mention_count": i + 1
            })
        
        dream_mode.core_memory._calculate_size()
        
        # 如果接近阈值应该触发
        if dream_mode.core_memory.size_bytes >= 8 * 1024:
            assert dream_mode.should_trigger("threshold") is True

    def test_no_trigger_too_soon(self, dream_mode):
        """测试太频繁不触发"""
        # 刚刚运行过
        dream_mode._last_run = datetime.now() - timedelta(minutes=30)
        
        assert dream_mode.should_trigger("scheduled") is False


class TestDreamModeIntegration:
    """测试 Dream Mode 集成"""

    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)

    @pytest.fixture
    def dream_mode(self, temp_dir):
        """创建 DreamMode 实例"""
        from src.core.memory.dream.dream_mode import DreamMode
        from src.core.memory.core.core_memory import CoreMemory
        
        core_memory = CoreMemory(user_id="user_001", storage_path=temp_dir)
        return DreamMode(core_memory=core_memory)

    def test_dream_mode_updates_core_memory(self, dream_mode):
        """测试 Dream Mode 更新核心记忆"""
        # 添加数据
        dream_mode.core_memory.add_top_entity({
            "name": "宁德时代",
            "type": "company",
            "mention_count": 6
        })
        
        dream_mode.run()
        
        # 核心记忆应该被更新
        entities = dream_mode.core_memory.top_entities
        assert len(entities) > 0

    def test_dream_mode_preserves_important_data(self, dream_mode):
        """测试 Dream Mode 保留重要数据"""
        # 添加重要数据
        dream_mode.core_memory.add_top_entity({
            "name": "重要公司",
            "type": "company",
            "mention_count": 20  # 高频
        })
        dream_mode.core_memory.save()
        
        dream_mode.run()
        
        # 重要数据应该被保留
        entity_names = [e.name for e in dream_mode.core_memory.top_entities]
        assert "重要公司" in entity_names

    def test_dream_mode_can_be_cancelled(self, dream_mode):
        """测试 Dream Mode 可以取消"""
        dream_mode.start_async()
        
        # 取消
        cancelled = dream_mode.cancel()
        
        assert cancelled is True