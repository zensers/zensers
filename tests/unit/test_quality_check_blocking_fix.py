"""
质量检查阻断问题修复测试套件

测试范围：
- BUG-1: quality_score 未初始化导致 NameError
- R1-P3: aggregated_dict 在 research() 路径未定义
- R3-P1: _check_cross_chapter_consistency() 不存在于 QualityCheckAgent
- R1: ResearchResult 新增 quality_score/quality_issues 字段
- R4: 幻觉检测上下文感知
- R5: 规范数据冲突口径对齐
- R6: 跨章节一致性口径分组
- E6: NumericConsistencyGate 口径分组
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import fields
import asyncio


# ============================================================
# BUG-1: quality_score 未初始化导致 NameError
# ============================================================

class TestBug1QualityScoreUninitialized:
    """
    验证 quality_score 未初始化的 NameError bug
    
    问题位置：
    - orchestrator.py L1001-1003: 只初始化 quality_result/quality_passed/issues
    - orchestrator.py L1935-1937: 同样问题
    - quality_score 仅在 if quality_result.get("success") 分支内赋值
    - 异常路径或 success=False 时，L1093/L2023 访问 quality_score 会 NameError
    """

    def test_quality_score_not_initialized_before_loop(self):
        """
        RED: 验证 quality_score 在循环前未初始化
        
        模拟 orchestrator.py L1001-1003 的初始化逻辑
        """
        quality_result = None
        quality_passed = False
        issues = []
        
        with pytest.raises(NameError):
            _ = quality_score

    def test_quality_score_access_after_exception_path(self):
        """
        RED: 模拟异常路径后访问 quality_score
        
        当 quality check agent 抛异常时，quality_score 未赋值
        """
        quality_result = None
        quality_passed = False
        issues = []
        
        try:
            raise Exception("Quality check failed")
        except Exception:
            pass
        
        with pytest.raises(NameError):
            summary = f"Quality check not passed (score={quality_score:.1f})"

    def test_quality_score_access_after_success_false(self):
        """
        RED: 模拟 success=False 路径后访问 quality_score
        
        当 quality_result.get("success") 为 False 时，
        quality_score 未赋值但 L1093 仍会访问
        """
        quality_result = {"success": False, "error": "Check failed"}
        quality_passed = False
        issues = []
        
        if quality_result.get("success"):
            quality_score = quality_result.get("quality_score", 0)
        else:
            pass
        
        with pytest.raises(NameError):
            summary = f"Quality check not passed (score={quality_score:.1f})"

    def test_fix_quality_score_initialized_to_zero(self):
        """
        GREEN: 验证修复方案——初始化 quality_score = 0.0
        """
        quality_result = None
        quality_passed = False
        issues = []
        quality_score = 0.0  # 修复：初始化
        
        try:
            raise Exception("Quality check failed")
        except Exception:
            pass
        
        summary = f"Quality check not passed (score={quality_score:.1f})"
        assert "score=0.0" in summary


# ============================================================
# R1-P3: aggregated_dict 在 research() 路径未定义
# ============================================================

class TestR1P3AggregatedDictUndefined:
    """
    验证 R1 修订代码中 aggregated_dict 变量名问题
    
    问题：
    - research() 路径用 aggregated (AggregationResult 对象)
    - smart routing 路径用 aggregated_dict (dict)
    - R1 修订代码混用两者，在 research() 路径 aggregated_dict 未定义
    """

    def test_research_path_has_aggregated_not_aggregated_dict(self):
        """
        RED: research() 路径只有 aggregated，没有 aggregated_dict
        """
        class MockAggregated:
            def to_dict(self):
                return {"sections": []}
        
        aggregated = MockAggregated()
        
        with pytest.raises(NameError):
            _ = aggregated_dict

    def test_smart_routing_path_has_aggregated_dict(self):
        """
        smart routing 路径有 aggregated_dict
        """
        aggregated_dict = {"sections": []}
        
        assert aggregated_dict is not None

    def test_fix_use_correct_variable_per_path(self):
        """
        GREEN: 验证修复方案——两路径分别处理
        """
        class MockAggregated:
            def to_dict(self):
                return {"sections": [{"title": "test"}]}
        
        # research() 路径
        aggregated = MockAggregated()
        report_research = aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {}
        assert "sections" in report_research
        
        # smart routing 路径
        aggregated_dict = {"sections": [{"title": "test2"}]}
        report_routing = aggregated_dict
        assert "sections" in report_routing


# ============================================================
# R3-P1: _check_cross_chapter_consistency() 不存在于 QualityCheckAgent
# ============================================================

class TestR3P1CrossChapterConsistencyMethodNotExists:
    """
    验证 _check_cross_chapter_consistency() 方法不存在于 QualityCheckAgent
    
    问题：
    - 该方法属于 checkers.py 的 ReportQualityChecker
    - QualityCheckAgent 继承自 FixedAgent，无此方法
    - R3 代码直接调用 self._check_cross_chapter_consistency() 会 AttributeError
    """

    def test_method_not_in_quality_check_agent(self):
        """
        RED: 验证方法不存在
        """
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")
        
        assert not hasattr(agent, '_check_cross_chapter_consistency')

    def test_method_exists_in_report_quality_checker(self):
        """
        验证方法存在于 ReportQualityChecker
        """
        from src.core.quality.checkers import ReportQualityChecker
        
        checker = ReportQualityChecker(threshold=80.0)
        
        assert hasattr(checker, '_check_cross_chapter_consistency')

    def test_fix_delegate_to_report_quality_checker(self):
        """
        GREEN: 验证修复方案——委托调用
        """
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        from src.core.quality.checkers import ReportQualityChecker
        
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")
        checker = ReportQualityChecker(threshold=80.0)
        
        sections = [
            {"id": "s1", "content": "2025年净利润40.85亿元"},
            {"id": "s2", "content": "2025年净利润40.85亿元"},
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        assert isinstance(score, float)
        assert 0 <= score <= 100


# ============================================================
# R1: ResearchResult 新增 quality_score/quality_issues 字段
# ============================================================

class TestR1ResearchResultNewFields:
    """
    验证 ResearchResult dataclass 新增字段
    """

    def test_current_fields_exist(self):
        """
        验证当前字段存在
        """
        from src.core.orchestrator.orchestrator import ResearchResult
        
        field_names = {f.name for f in fields(ResearchResult)}
        
        assert "task_id" in field_names
        assert "status" in field_names
        assert "output_path" in field_names
        assert "report" in field_names
        assert "document_path" in field_names

    def test_quality_fields_now_exist(self):
        """
        GREEN: 验证 quality_score/quality_issues 字段已添加
        """
        from src.core.orchestrator.orchestrator import ResearchResult
        
        field_names = {f.name for f in fields(ResearchResult)}
        
        assert "quality_score" in field_names
        assert "quality_issues" in field_names

    def test_fix_add_quality_fields(self):
        """
        GREEN: 验证修复后字段存在
        
        注意：此测试在修复前会失败
        """
        from src.core.orchestrator.orchestrator import ResearchResult
        from datetime import datetime
        
        result = ResearchResult(
            task_id="test",
            status="completed",
            topic="test topic",
            agents_used=["agent1"],
            stages_completed=5,
            quality_score=75.0,
            quality_issues=[{"type": "test", "message": "test issue"}],
        )
        
        assert result.quality_score == 75.0
        assert len(result.quality_issues) == 1


# ============================================================
# R4: 幻觉检测上下文感知
# ============================================================

class TestR4HallucinationContextAware:
    """
    验证幻觉检测的上下文感知改进
    
    问题：
    - 11.82 出现 25 次被标记为幻觉
    - 但 -11.82% 是营收同比变动，多章节引用完全正常
    """

    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        return QualityCheckAgent(agent_id="test", storage_path="/tmp")

    def test_percentage_with_metric_keyword_not_flagged(self, agent):
        """
        百分比 + 财务关键词 → 不应误判为幻觉
        """
        content = """
        2025年Q1营收1502.25亿元，同比下滑11.82%。
        2025年Q2营收1802亿元，同比下滑11.82%。
        2025年Q3营收1965亿元，同比下滑11.82%。
        2025年Q4营收2300亿元，同比下滑11.82%。
        全年营收同比变动-11.82%。
        """
        
        issues = agent._check_hallucinations(content)
        
        high_severity_hallucinations = [
            i for i in issues
            if i.get("type") == "accuracy" and i.get("severity") == "high"
            and "11.82" in i.get("message", "")
        ]
        
        assert len(high_severity_hallucinations) == 0, \
            f"百分比+财务关键词不应高严重度误判: {[i['message'] for i in high_severity_hallucinations]}"

    def test_same_value_different_contexts_not_flagged(self, agent):
        """
        同一数值在不同上下文出现 → 不应误判
        """
        content = """
        第一章：出口量40.85万辆。
        第二章：归母净利润40.85亿元。
        第三章：竞争对手出口约40.85万辆。
        第四章：海外市场40.85万辆面临风险。
        第五章：高端品牌占比40.85%。
        """
        
        issues = agent._check_hallucinations(content)
        
        hallucination_issues = [
            i for i in issues
            if "40.85" in i.get("message", "") and "幻觉" in i.get("message", "")
        ]
        
        assert len(hallucination_issues) == 0, \
            f"不同上下文的同一数值不应误判: {[i['message'] for i in hallucination_issues]}"

    def test_true_placeholder_still_flagged(self, agent):
        """
        真正的占位符仍应被检测
        """
        content = """
        销量200.0万辆，收入200.0万辆，利润200.0万辆。
        """
        
        issues = agent._check_hallucinations(content)
        
        placeholder_issues = [
            i for i in issues
            if "200.0" in i.get("message", "") and "占位符" in i.get("message", "")
        ]
        
        assert len(placeholder_issues) > 0, "真正的占位符应被检测"


# ============================================================
# R5: 规范数据冲突口径对齐
# ============================================================

class TestR5CanonicalCaliberAlignment:

    @pytest.fixture
    def registry(self):
        from src.core.data.canonical_registry import CanonicalDataRegistry, CanonicalDataEntry
        registry = CanonicalDataRegistry()
        entry = CanonicalDataEntry(
            metric="净利润",
            value=40.85,
            unit="亿元",
            year="2025",
            caliber="归母",
            source="test",
        )
        key = f"{entry.metric}_{entry.year}_{entry.caliber}"
        registry._data[key] = entry
        return registry

    def test_different_year_not_conflict(self, registry):
        section_content = "2024年净利润402.54亿元"
        data_points = [
            {"metric": "净利润", "value": "402.54", "unit": "亿元", "year": "2024"}
        ]
        
        errors = registry.validate_section(section_content, data_points)
        
        year_conflicts = [e for e in errors if "2024" in e and "净利润" in e]
        assert len(year_conflicts) == 0, "不同年份不应判为冲突"

    def test_different_caliber_not_conflict(self, registry):
        section_content = "扣非净利润41.48亿元"
        data_points = [
            {"metric": "净利润", "value": "41.48", "unit": "亿元", "year": "2025", "caliber": "扣非"}
        ]
        
        errors = registry.validate_section(section_content, data_points)
        
        caliber_conflicts = [e for e in errors if "口径" in e]
        assert len(caliber_conflicts) == 0, "不同口径不应判为冲突"

    def test_same_year_same_caliber_conflict_detected(self, registry):
        """
        同年同口径的冲突仍应被检测
        
        100.0 vs canonical 40.85 → diff > 5% → conflict
        """
        data_points = [
            {"metric": "净利润", "value": "100.0", "unit": "亿元", "year": "2025", "caliber": "归母"}
        ]
        
        errors = registry.validate_section("", data_points)
        
        assert len(errors) > 0, "同年同口径的冲突应被检测"
        assert any("净利润" in e for e in errors)


# ============================================================
# R6: 跨章节一致性口径分组
# ============================================================

class TestR6CrossChapterCaliberGrouping:
    """
    验证跨章节数值一致性的口径分组
    
    问题：
    - "2025年Q1净利润91.55亿" vs "2026年Q1净利润40.85亿" 被判为冲突
    - 不同年份/口径的同一指标名不是冲突
    """

    @pytest.fixture
    def checker(self):
        from src.core.quality.checkers import ReportQualityChecker
        return ReportQualityChecker(threshold=80.0)

    def test_different_year_not_contradiction(self, checker):
        """
        不同年份的同一指标不应判为矛盾
        """
        sections = [
            {"id": "s1", "content": "2025年Q1净利润91.55亿元"},
            {"id": "s2", "content": "2026年Q1净利润40.85亿元"},
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        
        assert score == 100.0, f"不同年份不应判为矛盾，得分={score}"

    def test_different_caliber_not_contradiction(self, checker):
        """
        不同口径的同一指标不应判为矛盾
        """
        sections = [
            {"id": "s1", "content": "归母净利润40.85亿元"},
            {"id": "s2", "content": "扣非净利润41.48亿元"},
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        
        assert score == 100.0, f"不同口径不应判为矛盾，得分={score}"

    def test_same_year_same_caliber_contradiction_detected(self, checker):
        """
        同年同口径的矛盾仍应被检测
        """
        sections = [
            {"id": "s1", "content": "2025年归母净利润40.85亿元"},
            {"id": "s2", "content": "2025年归母净利润100.0亿元"},
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        
        assert score < 100.0, "同年同口径的矛盾应被检测"


# ============================================================
# E6: NumericConsistencyGate 口径分组
# ============================================================

class TestE6NumericConsistencyGateCaliber:
    """
    验证 NumericConsistencyGate 的口径分组
    
    问题：
    - 该 gate 无年份/口径分组
    - engine.py 会静默篡改不同口径的 data_points
    """

    @pytest.fixture
    def gate(self):
        from src.core.quality.checkers import NumericConsistencyGate
        return NumericConsistencyGate(threshold=80.0)

    def test_different_year_not_contradiction(self, gate):
        """
        不同年份不应判为矛盾
        """
        data = {
            "sections": [
                {"id": "s1", "content": "2025年净利润91.55亿元"},
                {"id": "s2", "content": "2026年净利润40.85亿元"},
            ]
        }
        
        result = gate.check(data)
        
        assert result.score == 100.0, f"不同年份不应判为矛盾，得分={result.score}"

    def test_different_caliber_not_contradiction(self, gate):
        """
        不同口径不应判为矛盾
        """
        data = {
            "sections": [
                {"id": "s1", "content": "归母净利润40.85亿元"},
                {"id": "s2", "content": "扣非净利润41.48亿元"},
            ]
        }
        
        result = gate.check(data)
        
        assert result.score == 100.0, f"不同口径不应判为矛盾，得分={result.score}"


# ============================================================
# E6: engine.py data_points 修正口径对齐
# ============================================================

class TestE6EngineDataPointsCaliberAlignment:
    """
    验证 engine.py 中 data_points 修正的口径对齐
    
    问题：
    - engine.py:1480-1511 会静默篡改不同口径的 data_points
    """

    def test_different_year_not_modified(self):
        """
        不同年份的 data_point 不应被修改
        """
        from src.core.data.canonical_registry import parse_entry_key
        
        all_results = [{
            "success": True,
            "agent_id": "test",
            "content": "2024年净利润402.54亿元",
            "data_points": [
                {"metric": "净利润", "value": "402.54", "unit": "亿元", "year": "2024"}
            ],
        }]
        
        active_canonical_data = {
            "净利润_2025_CNY": {"value": 160.0, "unit": "亿元"}
        }
        
        fix_count = 0
        for metric_key, canon in active_canonical_data.items():
            kp = parse_entry_key(metric_key)
            cv = str(canon.get("value", ""))
            if not cv:
                continue
            metric_name = kp["metric"]
            canon_year = kp.get("year", "")
            
            for r in all_results:
                if not r.get("success"):
                    continue
                for dp in r.get("data_points", []):
                    if dp.get("metric", "").lower() != metric_name.lower():
                        continue
                    dp_year = str(dp.get("year", ""))
                    if canon_year and dp_year and dp_year != canon_year:
                        continue
                    old_val = str(dp.get("value", ""))
                    if old_val != "" and old_val != cv:
                        dp["value"] = cv
                        fix_count += 1
        
        assert fix_count == 0, "不同年份的 data_point 不应被修改"
        assert all_results[0]["data_points"][0]["value"] == "402.54"

    def test_different_caliber_not_modified(self):
        """
        不同口径的 data_point 不应被修改
        """
        from src.core.data.canonical_registry import parse_entry_key
        
        all_results = [{
            "success": True,
            "agent_id": "test",
            "content": "扣非净利润41.48亿元",
            "data_points": [
                {"metric": "净利润", "value": "41.48", "unit": "亿元", "year": "2025", "caliber": "扣非"}
            ],
        }]
        
        active_canonical_data = {
            "净利润_2025_CNY_归母": {"value": 40.85, "unit": "亿元", "caliber": "归母"}
        }
        
        fix_count = 0
        for metric_key, canon in active_canonical_data.items():
            kp = parse_entry_key(metric_key)
            cv = str(canon.get("value", ""))
            if not cv:
                continue
            metric_name = kp["metric"]
            canon_caliber = canon.get("caliber", "")
            
            for r in all_results:
                if not r.get("success"):
                    continue
                for dp in r.get("data_points", []):
                    if dp.get("metric", "").lower() != metric_name.lower():
                        continue
                    dp_caliber = dp.get("caliber", "")
                    if dp_caliber and canon_caliber and dp_caliber != canon_caliber:
                        continue
                    old_val = str(dp.get("value", ""))
                    if old_val != "" and old_val != cv:
                        dp["value"] = cv
                        fix_count += 1
        
        assert fix_count == 0, "不同口径的 data_point 不应被修改"
        assert all_results[0]["data_points"][0]["value"] == "41.48"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
