"""Failing-first contract for ChartSpec sidecar persistence (candidate 1)."""
import sys
sys.path.insert(0, "E:/market_report_systerm")
from src.services.chart_generator import ChartSpec, ChartType


def test_spec_roundtrip_json_safe(tmp_path):
    spec = ChartSpec(
        chart_type=ChartType.BAR,
        title="T",
        data={"categories": ["A", "B"], "values": [1, 2]},
        question="Which is higher?",
        unit="u",
        data_grain="company-year",
    )
    record = spec.to_record()
    import json
    json.dumps(record, ensure_ascii=False, allow_nan=False)
    back = ChartSpec.from_record(record)
    assert back.title == "T"
    assert back.data == {"categories": ["A", "B"], "values": [1, 2]}


def test_spec_rejects_nan_inf():
    spec = ChartSpec(
        chart_type=ChartType.BAR,
        title="T",
        data={"categories": ["A"], "values": [float("nan")]},
        question="q",
    )
    try:
        spec.to_record()
    except ValueError:
        return
    raise AssertionError("NaN data must be rejected")


def test_sidecar_store_roundtrip(tmp_path):
    from src.services.chart_generator import ChartSidecar
    store = ChartSidecar(str(tmp_path / "charts.json"))
    spec = ChartSpec(
        chart_type=ChartType.BAR,
        title="T",
        data={"categories": ["A"], "values": [1]},
        question="q",
    )
    ref = store.append(section="s1", spec=spec, path="charts/a.png")
    assert ref["chart_id"]
    loaded = ChartSidecar(str(tmp_path / "charts.json"))
    assert loaded.get(ref["chart_id"]).title == "T"
