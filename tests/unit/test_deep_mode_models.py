from src.core.deep_mode.config import DeepModeConfig
from src.core.deep_mode.models import BOMItemRecord, CompanyShareRecord, SupplierRecord


def test_config_from_env(monkeypatch):
    for key in (
        "ZENSERS_DEEP_MODE_ENABLED",
        "ZENSERS_DEEP_MODE_SHADOW",
        "ZENSERS_DEEP_MODE_MAX_SEARCHES",
        "ZENSERS_DEEP_MODE_MIN_QUERIES_PER_SECTION",
        "ZENSERS_DEEP_MODE_MAX_QUERIES_PER_SECTION",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ZENSERS_DEEP_MODE_ENABLED", "false")
    monkeypatch.setenv("ZENSERS_DEEP_MODE_MAX_SEARCHES", "42")
    monkeypatch.setenv("ZENSERS_DEEP_MODE_MAX_QUERIES_PER_SECTION", "7")

    config = DeepModeConfig.from_env()

    assert config.enabled is False
    assert config.max_searches == 42
    assert config.max_queries_per_section == 7


def test_company_share_to_data_point():
    record = CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="头部企业市场份额及变化",
        source_url="https://example.com/share",
        source_title="行业份额报告",
        source_quote="比亚迪份额32.5%",
        evidence_id="ev-1",
        period="2025",
        company_name="比亚迪",
        share_pct=32.5,
        metric_basis="shipments",
    )

    point = record.to_data_point()

    assert point["record_type"] == "company_share"
    assert point["structured_data"]["company_name"] == "比亚迪"
    assert point["structured_data"]["share_pct"] == 32.5
    assert point["data_need"] == "头部企业市场份额及变化"
    assert point["evidence_id"] == "ev-1"
    assert point["is_estimate"] is False


def test_bom_and_supplier_payloads():
    bom = BOMItemRecord(
        section_id="technology_trends",
        data_need="BOM成本拆解",
        source_url="https://example.com/bom",
        period="2025",
        system="动力电池",
        component="正极材料",
        cost_share_pct=18.0,
        supplier_names=["宁德时代"],
    )
    supplier = SupplierRecord(
        section_id="value_chain",
        data_need="关键供应商",
        source_url="https://example.com/supplier",
        supplier_name="宁德时代",
        component="动力电池",
        customers=["比亚迪"],
        relationship_type="supplier",
    )

    assert bom.payload()["component"] == "正极材料"
    assert bom.payload()["supplier_names"] == ["宁德时代"]
    assert supplier.payload()["customers"] == ["比亚迪"]
