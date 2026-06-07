"""
M5-a 测试：增强版 NumericConsistencyGate

TDD: RED 阶段 — 测试 MetricExtractor 修复 content + CalibrationReport
"""
import pytest


class TestM5aContentFixing:
    """M5-a: MetricExtractor 修复 content 中不一致数值"""

    def test_content_value_replaced(self):
        """content 中净利润值被 canonical 替换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "2024年净利润300亿元，同比增长10%",
             "data_points": [], "agent_id": "agent_0"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        assert "326.5亿元" in result["all_results"][0]["content"]
        assert "同比增长10%" in result["all_results"][0]["content"]

    def test_data_points_also_fixed(self):
        """data_points 中匹配到的指标也被替换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润300亿元",
             "data_points": [{"metric": "净利润", "value": 300, "year": "2024", "unit": "亿元"}],
             "agent_id": "agent_0"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        dp = result["all_results"][0]["data_points"][0]
        assert str(dp["value"]) == "326.5"

    def test_no_canonical_no_change(self):
        """无条件时原样通过"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润300亿元", "data_points": [], "agent_id": "a"},
        ]
        result = fix_content_from_canonical(all_results, {})
        assert result["all_results"][0]["content"] == "净利润300亿元"

    def test_multiple_metrics_all_fixed(self):
        """多个指标全部修复"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润300亿元，营收5000亿元",
             "data_points": [], "agent_id": "agent_0"},
        ]
        canonical_data = {
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元"},
            "营收_2024_CNY": {"value": 5300, "unit": "亿元"},
        }
        result = fix_content_from_canonical(all_results, canonical_data)
        c = result["all_results"][0]["content"]
        assert "326.5亿元" in c
        assert "5300亿元" in c

    def test_failed_results_skipped(self):
        """失败的结果不修复"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": False, "content": "失败", "data_points": [], "agent_id": "a"},
            {"success": True, "content": "净利润300亿元", "data_points": [], "agent_id": "b"},
        ]
        canonical_data = {"净利润_2024": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        assert result["all_results"][0]["content"] == "失败"
        assert "326.5亿元" in result["all_results"][1]["content"]

    def test_same_metric_multiple_appearances(self):
        """同一指标多次出现全部替换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True,
             "content": "Q1净利润300亿元。全年净利润300亿元。",
             "data_points": [], "agent_id": "a"},
        ]
        canonical_data = {"净利润_2024": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        assert result["all_results"][0]["content"].count("326.5亿元") == 2

    def test_table_lines_skipped(self):
        """表格行不替换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        content = "| 指标 | 值 |\n|------|----|\n| 净利润 | 300亿元 |\n\n其它部分净利润300亿元。"
        all_results = [
            {"success": True, "content": content, "data_points": [], "agent_id": "a"},
        ]
        canonical_data = {"净利润_2024": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        lines = result["all_results"][0]["content"].split('\n')
        table_lines = [l for l in lines if l.startswith('|')]
        for tl in table_lines:
            assert "326.5亿元" not in tl


class TestM5aCalibrationReport:
    """M5-a: CalibrationReport 结构"""

    def test_report_structure(self):
        """包含必要字段"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润300亿元", "data_points": [], "agent_id": "agent_0"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        report = result["calibration_report"]
        assert "total_metrics_checked" in report
        assert "auto_fixed" in report
        assert "currency_converted" in report
        assert "canonical_summary" in report

    def test_auto_fixed_records_changes(self):
        """auto_fixed 记录每次替换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润300亿元", "data_points": [], "agent_id": "agent_0"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        entry = result["calibration_report"]["auto_fixed"][0]
        assert entry["metric"] == "净利润"
        assert entry["old_value"] == 300.0
        assert entry["new_value"] == 326.5

    def test_no_fixes_still_generates_report(self):
        """无修复时也生成空报告"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润326亿元", "data_points": [], "agent_id": "a"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data)
        report = result["calibration_report"]
        assert report["total_metrics_checked"] >= 0
        assert len(report["auto_fixed"]) == 0


class TestM5aCurrencyConversion:
    """M5-a: 货币转换"""

    def test_hkd_to_cny_converted(self):
        """HKD 转换为 CNY"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "净利润520亿港元", "data_points": [], "agent_id": "a"},
        ]
        canonical_data = {"净利润_2024_HKD": {"value": 520, "unit": "亿港元"}}
        result = fix_content_from_canonical(all_results, canonical_data, target_currency="CNY")
        report = result["calibration_report"]
        assert len(report["currency_converted"]) > 0
        conv = report["currency_converted"][0]
        assert conv["from_currency"] == "HKD"

    def test_same_currency_no_conversion(self):
        """同货币不转换"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        all_results = [
            {"success": True, "content": "", "data_points": [], "agent_id": "a"},
        ]
        canonical_data = {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}}
        result = fix_content_from_canonical(all_results, canonical_data, target_currency="CNY")
        assert len(result["calibration_report"]["currency_converted"]) == 0
