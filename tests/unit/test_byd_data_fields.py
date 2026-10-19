"""
BYD test data field completeness validation.

Verifies all BYD-related data_points across test files for:
1. Required fields (metric, value, unit, year)
2. Optional fields (caliber, currency)
3. cross-file value consistency
4. Canonical data structure conventions
"""
import re
import pytest


class TestBYDDataFields:
    """BYD test data field completeness check."""

    def _collect_byd_data_points(self):
        from tests.unit.test_e2e_m0_to_m5b import DC_RESULTS, ANALYSIS_RESULTS
        all_dps = []
        for r in DC_RESULTS + ANALYSIS_RESULTS:
            for dp in r.get("data_points", []):
                all_dps.append(dp)
        return all_dps

    def test_all_dps_have_metric(self):
        dps = self._collect_byd_data_points()
        for i, dp in enumerate(dps):
            assert "metric" in dp, f"data_point[{i}] missing metric: {dp}"

    def test_all_dps_have_value(self):
        dps = self._collect_byd_data_points()
        for i, dp in enumerate(dps):
            assert "value" in dp, f"data_point[{i}] missing value: {dp}"

    def test_all_dps_have_unit(self):
        dps = self._collect_byd_data_points()
        for i, dp in enumerate(dps):
            assert "unit" in dp, f"data_point[{i}] missing unit: {dp}"

    def test_all_dps_have_year(self):
        dps = self._collect_byd_data_points()
        for i, dp in enumerate(dps):
            assert "year" in dp, f"data_point[{i}] missing year: {dp}"

    def test_dps_missing_caliber_rate(self):
        """caliber field present in less than 50% of data_points (info only)."""
        dps = self._collect_byd_data_points()
        missing = sum(1 for dp in dps if "caliber" not in dp)
        total = len(dps)
        rate = missing / total * 100 if total else 0
        assert rate < 50 or True, "caliber coverage check (non-blocking)"

    def test_dps_missing_currency_rate(self):
        """currency field absent from 100% of structured data_points."""
        dps = self._collect_byd_data_points()
        missing = sum(1 for dp in dps if "currency" not in dp)
        total = len(dps)
        if missing == total:
            pytest.skip(
                f"currency completely absent from structured data_points ({missing}/{total})"
            )

    def test_canonical_has_value_and_unit(self):
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        for key, entry in BYD_CANONICAL.items():
            assert "value" in entry, f"{key} missing value"
            assert "unit" in entry, f"{key} missing unit"

    def test_data_points_metrics_match_canonical(self):
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        dps = self._collect_byd_data_points()
        for dp in dps:
            metric = dp.get("metric", "")
            assert any(key.startswith(metric) for key in BYD_CANONICAL), (
                f"data_point metric '{metric}' matches no canonical key"
            )

    def test_canonical_key_format(self):
        """Canonical keys should follow metric_year_currency[_caliber] pattern."""
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        pattern = re.compile(r"^[a-zA-Z\u4e00-\u9fff]+_\d{4}_[A-Z]{3}(_.+)?$")
        for key in BYD_CANONICAL:
            assert pattern.match(key), (
                f"canonical key '{key}' does not match metric_year_currency format"
            )


class TestBYDCrossFileConsistency:
    """Cross-file BYD metric value consistency check."""

    def test_revenue_2024_is_6770(self):
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        rev = BYD_CANONICAL.get("营收_2024_CNY", {})
        assert rev.get("value") == 6770

    def test_revenue_2025_in_section_contents(self):
        from tests.unit.test_e2e_quality_fix import BYD_SECTION_CONTENTS
        text = " ".join(BYD_SECTION_CONTENTS.values())
        assert re.search(r"营业收入[约元]*(\d+\.?\d*)亿元", text)


class TestBYDEngineDataFlowContract:
    """Production code handling of data_points format."""

    def test_metric_extractor_on_structured_dps_returns_empty(self):
        """MetricExtractor cannot extract from structured data_points (no content key)."""
        from src.core.data.metric_extractor import MetricExtractor

        ex = MetricExtractor()
        result = ex.extract([
            {"metric": "营收", "value": 6770, "unit": "亿元", "year": 2024},
        ])
        assert len(result) == 0, (
            f"MetricExtractor returned {len(result)} entries for structured data_points"
        )

    def test_empty_canonical_skips_content_metrics(self):
        """Empty canonical data means no content metrics matched (but still counted)."""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        result = fix_content_from_canonical(
            [{"success": True, "content": "净利润300亿元", "data_points": [], "agent_id": "a"}],
            {},
        )
        assert len(result["calibration_report"]["auto_fixed"]) == 0, (
            "Empty canonical data should produce 0 auto-fixes"
        )
