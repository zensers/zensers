"""
BYD pipeline data flow tests: verify production code correctly handles
structured data_points and canonical data format.

Issues detected:
  C3: engine.py:1325 _ex.extract(_r["data_points"]) reads dp.get("content", "")
      but structured data_points have no "content" key -> always returns empty.
  C2: engine.py:1337 _active_canonical_data built without "currency" field.
"""
import pytest


class TestBYDPipelineMetricExtractionPath:
    """engine.py S-FIX-2 extraction path with structured data_points."""

    def test_engine_extract_with_structured_dps_returns_empty(self):
        """engine.py:1325 ex.extract(data_points) on structured dps returns empty."""
        from src.core.data.metric_extractor import MetricExtractor

        ex = MetricExtractor()
        data_points = [
            {"metric": "营收", "value": 6770, "unit": "亿元", "year": 2024},
            {"metric": "净利润", "value": 326.5, "unit": "亿元", "year": 2024},
        ]
        result = ex.extract(data_points)
        assert len(result) == 0, (
            f"MetricExtractor on structured data_points returned {len(result)} items"
        )

    def test_engine_extract_with_content_key_works(self):
        """MetricExtractor works only when data_points have 'content' key."""
        from src.core.data.metric_extractor import MetricExtractor

        ex = MetricExtractor()
        data_points = [
            {
                "content": "2024年营收6770亿元，净利润326.5亿元",
                "url": "https://example.com",
            },
        ]
        result = ex.extract(data_points)
        assert len(result) > 0, "data_points with content key should be extractable"

    def test_active_canonical_data_lacks_currency(self):
        """engine.py:1336-1340 strips currency from _active_canonical_data."""
        from src.core.data.canonical_registry import CanonicalDataRegistry, CanonicalDataEntry

        registry = CanonicalDataRegistry()
        entry = CanonicalDataEntry(
            metric="营收", value=6770, unit="亿元", year="2024",
            currency="CNY", source="年报",
        )
        registry._data["营收_2024_CNY"] = entry

        active = {
            k: {"value": v.value, "unit": v.unit, "caliber": v.caliber,
                "source": v.source, "year": v.year}
            for k, v in registry.get_all().items()
        }

        entry_dict = active.get("营收_2024_CNY", {})
        assert "currency" not in entry_dict, (
            "_active_canonical_data should NOT contain currency"
        )

    def test_normalize_canonical_uses_currency(self):
        """_normalize_canonical uses entry.get('currency') for conversion."""
        import inspect
        from src.core.orchestrator.execution.calibration_gate import _normalize_canonical
        src = inspect.getsource(_normalize_canonical)
        assert "currency" in src, "_normalize_canonical should reference currency"


class TestBYDStructuredDataIntegration:
    """End-to-end: calibration gate with structured data_points."""

    def test_fix_content_from_canonical_with_structured_dps(self):
        """calibration gate fixes both content and data_points."""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        all_results = [
            {
                "success": True,
                "content": "2024年营收7200亿元，净利润360亿元",
                "data_points": [
                    {"metric": "营收", "value": 7200, "unit": "亿元", "year": 2024},
                    {"metric": "净利润", "value": 360, "unit": "亿元", "year": 2024},
                ],
                "agent_id": "analysis_1",
            },
        ]
        canonical_data = {
            "营收_2024_CNY": {"value": 6770, "unit": "亿元", "currency": "CNY"},
            "净利润_2024_CNY": {"value": 326.5, "unit": "亿元", "currency": "CNY"},
        }

        result = fix_content_from_canonical(all_results, canonical_data)
        report = result["calibration_report"]
        assert len(report["auto_fixed"]) >= 2, (
            f"Expected >=2 auto-fixes, got {len(report['auto_fixed'])}"
        )

        dps = result["all_results"][0]["data_points"]
        rev_dp = next(dp for dp in dps if dp["metric"] == "营收")
        assert rev_dp["value"] == 6770, f"Revenue should be fixed to 6770, got {rev_dp['value']}"

    def test_content_also_fixed_by_calibration_gate(self):
        """calibration gate fixes content text as well."""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        all_results = [
            {
                "success": True,
                "content": "2024年营收7200亿元，净利润360亿元",
                "data_points": [
                    {"metric": "营收", "value": 7200, "unit": "亿元", "year": 2024},
                ],
                "agent_id": "analysis_1",
            },
        ]
        canonical_data = {
            "营收_2024_CNY": {"value": 6770, "unit": "亿元", "currency": "CNY"},
        }

        result = fix_content_from_canonical(all_results, canonical_data)
        content = result["all_results"][0]["content"]
        assert "6770亿元" in content
        assert "7200亿元" not in content
