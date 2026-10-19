# -*- coding: utf-8 -*-
"""复审修订 P0-A/P0-B 合同测试（ses_baf7a884 复审裁决落地）。

P0-A：定性表述变体（双侧无数值的复述差异）不进 L5 conflicts，只记
variants；数值冲突保持 blocking（L5 本体职责）。
P0-B：L2 元数据检查仅对定量数据点生效（回归 defense_audit 注释声明的
设计意图）；_ground_data_point_sources 从证据目录确定性回填元数据。
"""
import unittest

from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.defense_audit import ReportDefenseAudit


class TestQualitativeVariantsNotConflicts(unittest.TestCase):
    """P0-A：定性复述差异不构成 L5 blocking。"""

    def test_qualitative_paraphrase_records_variant_not_conflict(self):
        registry = DataRegistry()
        registry.register(
            metric="竞争重心", value="从'模型能不能做'转向'系统能不能持续做'",
            unit="定性", chapter_id="s1", source="jazzyear月报")
        registry.register(
            metric="竞争重心", value="从模型能力转向系统能力",
            unit="定性", chapter_id="s4", source="jazzyear月报")
        self.assertEqual(registry.get_conflicts(), [], "定性复述差异不得进 conflicts")
        entry = registry._metrics[registry._normalize_metric("竞争重心")]
        self.assertEqual(len(entry.variants), 1)
        self.assertEqual(entry.variants[0]["value"], "从模型能力转向系统能力")

    def test_numeric_conflict_still_blocks(self):
        registry = DataRegistry()
        registry.register(metric="市场规模", value="1.2万亿", unit="元",
                          chapter_id="s0", source="新华网")
        registry.register(metric="市场规模", value="2.5万亿", unit="元",
                          chapter_id="s3", source="其他来源")
        conflicts = registry.get_conflicts()
        self.assertEqual(len(conflicts), 1, "数值冲突必须保持 blocking")
        self.assertEqual(conflicts[0].metric, "市场规模")

    def test_mixed_numeric_vs_qualitative_is_conflict(self):
        """一侧定量一侧定性：保守按冲突处理（证据状态不明）。"""
        registry = DataRegistry()
        registry.register(metric="算力规模", value="持续扩大", unit="定性",
                          chapter_id="s1", source="南开")
        registry.register(metric="算力规模", value="500 EFLOPS", unit="",
                          chapter_id="s2", source="浦银")
        self.assertEqual(len(registry.get_conflicts()), 1)

    def test_serialize_conflicts_clean_for_qualitative_only(self):
        registry = DataRegistry()
        registry.register(metric="技术路线", value="AGI探索与应用落地并行",
                          unit="—", chapter_id="s1", source="阿里云")
        registry.register(metric="技术路线", value="分化为两条路线",
                          unit="—", chapter_id="s4", source="同上")
        self.assertIn("无已知数据冲突", registry.serialize_conflicts())

    def test_snapshot_roundtrip_preserves_variants(self):
        registry = DataRegistry()
        registry.register(metric="竞争重心", value="转向系统能力", unit="定性",
                          chapter_id="s1", source="A")
        registry.register(metric="竞争重心", value="转向系统持续能力", unit="定性",
                          chapter_id="s2", source="B")
        restored = DataRegistry.from_snapshot(registry.to_snapshot())
        entry = restored._metrics[restored._normalize_metric("竞争重心")]
        self.assertEqual(len(entry.variants), 1)
        self.assertEqual(restored.get_conflicts(), [])


def _dp(**over):
    base = {
        "metric": "全球AI市场规模", "value": "3420亿美元", "unit": "",
        "source": "IIM", "source_url": "https://x.test/a",
        "evidence_status": "verified", "evidence_id": "ev_1",
        "provenance_id": "prov_1", "chapter_id": "s0",
        "geographic_scope": "全球", "period": "2025年", "population": "",
        "epistemic_level": "factual",
    }
    base.update(over)
    return base


class TestL2QuantitativeOnly(unittest.TestCase):
    """P0-B：L2 元数据检查仅对定量数据点生效。"""

    def _audit_one(self, dp):
        report = {"sections": [{"id": "s0", "title": "T", "content": "正文",
                                "data_points": [dp]}]}
        return ReportDefenseAudit().audit(report)

    def test_quantitative_dp_missing_scope_still_flagged(self):
        dp = _dp(geographic_scope="", period="", population="")
        audit = self._audit_one(dp)
        codes = {i["code"] for i in audit["issues"]}
        self.assertIn("missing_geographic_scope", codes)
        self.assertIn("missing_period", codes)

    def test_qualitative_dp_without_metadata_not_flagged(self):
        dp = _dp(metric="大模型技术路线", value="AGI探索与应用落地并行",
                 unit="—", geographic_scope="", period="", population="")
        audit = self._audit_one(dp)
        codes = {i["code"] for i in audit["issues"]}
        self.assertNotIn("missing_geographic_scope", codes, "定性条目不得触发 L2")
        self.assertNotIn("missing_period", codes)
        self.assertNotIn("missing_population", codes)


class TestMetadataBackfill(unittest.TestCase):
    """P0-B 配套：_ground_data_point_sources 从证据目录回填元数据。"""

    def test_backfills_period_and_scope_from_catalog(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "规模", "value": "3420亿美元", "source": "IIM",
                "source_url": "https://x.test/a"}]
        catalog = [{
            "title": "IIM研究报告", "url": "https://x.test/a",
            "evidence_id": "ev_9", "provenance_id": "prov_9",
            "evidence_excerpt": "2025年全球强人工智能核心产业市场规模3420亿美元",
            "period": "2025年", "geographic_scope": "全球",
        }]
        grounded = ReportOrchestrator._ground_data_point_sources(dps, catalog, "s0")
        self.assertEqual(grounded[0].get("period"), "2025年")
        self.assertEqual(grounded[0].get("geographic_scope"), "全球")

    def test_no_fabrication_when_catalog_lacks_metadata(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "规模", "value": "3420亿美元", "source": "IIM",
                "source_url": "https://x.test/a"}]
        catalog = [{"title": "IIM研究报告", "url": "https://x.test/a",
                    "evidence_id": "ev_9", "provenance_id": "prov_9",
                    "evidence_excerpt": "excerpt"}]
        grounded = ReportOrchestrator._ground_data_point_sources(dps, catalog, "s0")
        self.assertEqual(grounded[0].get("period", ""), "")
        self.assertEqual(grounded[0].get("geographic_scope", ""), "")


if __name__ == "__main__":
    unittest.main()
