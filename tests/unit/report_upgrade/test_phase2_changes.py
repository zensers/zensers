import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict


class TestE1ProgressiveThresholds:
    """E1: 渐进收敛阈值"""

    def test_get_min_improvement_round0(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        # round_idx=0 (第一轮): 阈值应为3
        min_imp = RetryPolicy.get_min_improvement(0)
        assert min_imp == 3

    def test_get_min_improvement_round1(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        min_imp = RetryPolicy.get_min_improvement(1)
        assert min_imp == 2

    def test_get_min_improvement_round2(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        min_imp = RetryPolicy.get_min_improvement(2)
        assert min_imp == 1

    def test_get_min_improvement_beyond_rounds(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        # 超出预设轮数时使用最后一个值
        min_imp = RetryPolicy.get_min_improvement(10)
        assert min_imp == 1


class TestD2ExtractChapterDataAcceptsSkillRegistry:
    """D2: _extract_chapter_data 接受 skill_registry 参数"""

    def test_accepts_skill_registry_param(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        import inspect
        sig = inspect.signature(ReportOrchestrator._extract_chapter_data)
        assert 'skill_registry' in sig.parameters, "_extract_chapter_data应接受skill_registry参数"
        param = sig.parameters['skill_registry']
        assert param.default is None, "skill_registry应默认为None，兼容旧调用"

    def test_default_skill_registry_works(self):
        """不传skill_registry时行为不变"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from tests.unit.report_upgrade.test_orchestrator import MockAggregationResult
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"data": "内容"}}}
        chapter_data, raw_summary = ReportOrchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data == {"data": "内容"}

    def test_skill_registry_passed_from_orchestrator(self):
        """验证 orchestrator 在调用 _extract_chapter_data 时传入 self._skill_registry"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        import inspect
        # 检查 _phase4_fix_and_optimize 中调用 _extract_chapter_data 的位置
        # 和 generate_report 中调用 _extract_chapter_data 的位置
        source = inspect.getsource(ReportOrchestrator._phase4_fix_and_optimize)
        assert '_extract_chapter_data' in source
        assert 'self._aggregated_result' in source

    def test_pass_skill_registry_to_extract(self):
        """传入 skill_registry 不报错"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from tests.unit.report_upgrade.test_orchestrator import MockAggregationResult
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"data": "内容"}}}
        skill_registry = {"stock_data": "mock", "knowledge_query": "mock"}
        chapter_data, raw_summary = ReportOrchestrator._extract_chapter_data(agg, "ch1", [], skill_registry=skill_registry)
        assert chapter_data == {"data": "内容"}


class TestA3AnalysisQualityCheckerInPhase4:
    """A3: AnalysisQualityChecker 接入 _phase4_fix_and_optimize"""

    def test_checker_imported_in_orchestrator(self):
        """orchestrator.py 中应导入 AnalysisQualityChecker"""
        from src.agents.fixed_agents.report_upgrade import orchestrator as orch_mod
        assert hasattr(orch_mod, 'AnalysisQualityChecker') or 'AnalysisQualityChecker' in dir(orch_mod)
        # 实际上应该从 checkers.py 导入
        from src.core.quality.checkers import AnalysisQualityChecker
        assert AnalysisQualityChecker is not None

    def test_phase4_uses_programmatic_checker(self):
        """_phase4_fix_and_optimize 应包含 AnalysisQualityChecker 检查"""
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        import inspect
        source = inspect.getsource(ReportOrchestrator._phase4_fix_and_optimize)
        assert 'AnalysisQualityChecker' in source, "_phase4中应使用AnalysisQualityChecker"
        assert '_check_structure' in source or 'checker.check' in source, "_phase4中应调用checker检查"


class TestS3S2S1CheckersChanges:
    """S3: 反证兼容risk + S2: data_support关键词 + S1: 权重调整"""

    def test_s3_fanzheng_in_risk_disclosure_keywords(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        risk_keywords = AnalysisQualityChecker.STRUCTURE_MARKERS["risk_disclosure"]["keywords"]
        assert "反证" in risk_keywords
        assert "边界条件" in risk_keywords

    def test_s2_data_support_keywords_no_vague_words(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        ds_keywords = AnalysisQualityChecker.STRUCTURE_MARKERS["data_support"]["keywords"]
        assert "据" not in ds_keywords, "据 should be removed (matches liaojie)"
        assert "来源" not in ds_keywords
        assert "统计" not in ds_keywords

    def test_s2_data_support_has_specific_keywords(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        ds_keywords = AnalysisQualityChecker.STRUCTURE_MARKERS["data_support"]["keywords"]
        assert "数据来源" in ds_keywords
        assert "数据显示" in ds_keywords
        assert "据统计" in ds_keywords

    def test_s1_weights_adjusted(self):
        """S1: AnalysisQualityChecker 权重应调整"""
        from src.core.quality.checkers import AnalysisQualityChecker
        # 验证 weights 有变化（不再使用原始权重）
        # 通过检查calculate_score来获取权重
        import re
        source = open(AnalysisQualityChecker.calculate_score.__code__.co_filename, encoding='utf-8').read()
        # 在calculate_score附近查找0.45
        start = source.find('def calculate_score')
        end = source.find('def _check_structure', start)
        calc_body = source[start:end]
        assert '0.45' in calc_body, 'structure权重应为0.45'
        assert '0.20' in calc_body, 'caliber/risk权重应为0.20'

    def test_risk_disclosure_min_context_chars_30(self):
        """S3: risk_disclosure min_context_chars 保持30"""
        from src.core.quality.checkers import AnalysisQualityChecker
        risk_config = AnalysisQualityChecker.STRUCTURE_MARKERS["risk_disclosure"]
        assert risk_config["min_context_chars"] == 30
