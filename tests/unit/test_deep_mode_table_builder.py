import json

from src.core.deep_mode.models import BOMItemRecord, CompanyShareRecord, SupplierRecord
from src.core.deep_mode.store import DeepModeStore
from src.core.deep_mode.table_builder import DeepTableBuilder


def _point(company: str, pct: float, estimate: bool = False) -> dict:
    record = CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="市场份额",
        source_url="https://example.com/share",
        source_quote=f"{company} {pct}%",
        period="2025",
        company_name=company,
        share_pct=pct,
        metric_basis="shipments",
        is_estimate=estimate,
        estimate_method="公司销量/行业销量" if estimate else "",
    )
    return record.to_data_point()


def _bom_point() -> dict:
    record = BOMItemRecord(
        section_id="bom_breakdown",
        data_need="BOM成本",
        source_url="https://example.com/bom",
        source_quote="电芯占60%",
        period="2025",
        system="动力电池",
        component="电芯",
        cost_share_pct=60.0,
        supplier_names=["宁德时代"],
    )
    return record.to_data_point()


def _supplier_point() -> dict:
    record = SupplierRecord(
        section_id="supply_chain",
        data_need="供应商",
        source_url="https://example.com/supply",
        source_quote="宁德时代供应电芯",
        period="2025",
        supplier_name="宁德时代",
        component="电芯",
        customers=["比亚迪", "特斯拉"],
    )
    return record.to_data_point()


def test_build_company_share_table_marks_estimates():
    table = DeepTableBuilder().build_for_section(
        "competitive_landscape",
        [_point("比亚迪", 32.5), _point("特斯拉", 12.0, estimate=True)],
    )

    assert "| 公司 | 市场份额 | 统计口径 | 期间 | 数据性质 | 来源 |" in table
    assert "比亚迪" in table
    assert "特斯拉" in table
    assert "12.0%*" in table
    assert "估算" in table


def test_ensure_table_appends_missing_table():
    builder = DeepTableBuilder()
    content = "竞争格局分析。"

    updated = builder.ensure_table(
        "competitive_landscape",
        content,
        [_point("比亚迪", 32.5)],
    )

    assert updated.startswith(content)
    assert "| 公司 | 市场份额 |" in updated


def test_store_writes_artifacts(tmp_path):
    store = DeepModeStore(base_dir=tmp_path)
    store.save(
        task_id="task-1",
        plan={"sections": {"company_share": "competitive_landscape"}},
        queries=[],
        records=[],
        validation={"dropped": []},
        tables={"competitive_landscape": "| 公司 |"},
        summary={"queries_used": 0},
    )

    assert (tmp_path / "task-1" / "plan.json").exists()
    assert json.loads((tmp_path / "task-1" / "summary.json").read_text(encoding="utf-8")) == {
        "queries_used": 0
    }


def test_mixed_points_deterministic_type():
    table = DeepTableBuilder().build_for_section(
        "competitive_landscape",
        [_point("比亚迪", 32.5), _supplier_point()],
    )

    assert "| 公司 | 市场份额 |" in table


def test_build_bom_table():
    table = DeepTableBuilder().build_for_section("section_2", [_bom_point()])

    assert "| 系统 | 部件 | 成本占比 | 关键供应商 | 技术路线/备注 | 来源 |" in table
    assert "电芯" in table
    assert "60.0%" in table
    assert "宁德时代" in table


def test_build_supplier_table():
    table = DeepTableBuilder().build_for_section("section_3", [_supplier_point()])

    assert "| 环节 | 主要供应商 | 配套关系 | 期间 | 来源 |" in table
    assert "宁德时代" in table
    assert "比亚迪、特斯拉" in table


def test_cells_escaped():
    table = DeepTableBuilder().build_for_section(
        "competitive_landscape",
        [_point("宁德时代 | CATL", 32.5)],
    )

    assert "宁德时代 \\| CATL" in table
    assert "宁德时代 | CATL" not in table


def test_ensure_table_idempotent():
    builder = DeepTableBuilder()
    points = [_point("比亚迪", 32.5)]

    first = builder.ensure_table("competitive_landscape", "竞争格局分析。", points)
    second = builder.ensure_table("competitive_landscape", "竞争格局分析。", points)

    assert first == second


def test_empty_points_no_table():
    builder = DeepTableBuilder()

    assert builder.build_for_section("section_3", []) == ""
    assert builder.ensure_table("section_3", "正文。", []) == "正文。"


def test_store_serializes_records_and_markdown(tmp_path):
    record = CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="市场份额",
        source_url="https://example.com/share",
        source_quote="比亚迪 32.5%",
        company_name="比亚迪",
        share_pct=32.5,
    )
    store = DeepModeStore(base_dir=tmp_path)
    tables = "| 公司 |\n|---|\n"
    store.save(
        task_id="task-2",
        plan={},
        queries=[],
        records=[record],
        validation={},
        tables=tables,
        summary={},
    )

    parsed = json.loads((tmp_path / "task-2" / "records.json").read_text(encoding="utf-8"))
    assert isinstance(parsed, list)
    assert parsed[0]["record_type"] == "company_share"
    assert "structured_data" in parsed[0]
    assert (tmp_path / "task-2" / "tables.md").read_text(encoding="utf-8") == tables
