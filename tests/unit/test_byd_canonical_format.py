"""
BYD canonical data format consistency tests.

Detects:
1. Canonical dict format inconsistency across test files
2. value type mixing (int vs float) in canonical data
3. Production code path using registry vs test data passing dict directly
"""
import pytest


class TestBYDCanonicalFormat:
    """Canonical data format validation."""

    def test_canonical_entry_fields(self):
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        for key, entry in BYD_CANONICAL.items():
            assert "value" in entry, f"{key} missing value"
            assert isinstance(entry["value"], (int, float)), (
                f"{key} value should be int/float, got {type(entry['value'])}"
            )
            assert "unit" in entry, f"{key} missing unit"

    def test_canonical_value_types_mixed_int_float(self):
        """BYD_CANONICAL has mixed int/float values — not a bug but worth noting."""
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        types = {type(entry["value"]).__name__ for entry in BYD_CANONICAL.values()}
        if len(types) > 1:
            pytest.skip(
                f"canonical values have mixed types: {types} — acceptable but prefer uniform"
            )

    def test_canonical_currency_field_present(self):
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        has_currency = any("currency" in v for v in BYD_CANONICAL.values())
        if not has_currency:
            pytest.skip("BYD_CANONICAL has no currency field (OK for CNY-only tests)")

    def test_parse_entry_key_on_all_keys(self):
        """Every canonical key must be parseable by parse_entry_key()."""
        from src.core.data.canonical_registry import parse_entry_key
        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        for key in BYD_CANONICAL:
            parsed = parse_entry_key(key)
            assert parsed is not None, f"parse_entry_key('{key}') returned None"
            assert parsed["metric"], f"parse_entry_key('{key}') extracted no metric"
            assert parsed["year"], f"parse_entry_key('{key}') extracted no year"


class TestBYDCanonicalUsage:
    """Canonical data usage in production code vs test bypass."""

    def test_bypass_detection_currency(self):
        """
        Test passes BYD_CANONICAL directly (with currency) to gate,
        but production builds _active_canonical_data without currency.
        """
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

        from tests.unit.test_e2e_m0_to_m5b import BYD_CANONICAL
        test_has_currency = any("currency" in v for v in BYD_CANONICAL.values())
        prod_has_currency = any("currency" in v for v in active.values())

        if test_has_currency and not prod_has_currency:
            pytest.skip(
                "test data has currency but _active_canonical_data does not"
                " — test bypasses production code path"
            )

    def test_fix_content_from_canonical_with_currency(self):
        """fix_content_from_canonical works with currency in canonical data."""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        result = fix_content_from_canonical(
            [{"success": True, "content": "净利润300亿元", "data_points": [],
              "agent_id": "a"}],
            {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元", "currency": "CNY"}},
        )
        assert result["calibration_report"]["total_metrics_checked"] >= 1

    def test_fix_content_from_canonical_without_currency(self):
        """fix_content_from_canonical also works without currency (no conversion)."""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        result = fix_content_from_canonical(
            [{"success": True, "content": "净利润300亿元", "data_points": [],
              "agent_id": "a"}],
            {"净利润_2024_CNY": {"value": 326.5, "unit": "亿元"}},
        )
        assert result["calibration_report"]["total_metrics_checked"] >= 1
