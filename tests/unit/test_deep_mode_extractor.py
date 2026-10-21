import pytest

from src.core.deep_mode.extractor import StructuredEvidenceExtractor
from src.core.deep_mode.models import SupplierRecord

COMPANY_TABLE = """
| 公司 | 市场份额 | 统计口径 | 期间 |
|---|---|---|---|
| 比亚迪 | 32.5% | 销量 | 2025 |
| 特斯拉 | 12.0% | 销量 | 2025 |
"""

BOM_TABLE = """
| 系统 | 部件 | 成本占比 | 关键供应商 |
|---|---|---|---|
| 动力电池 | 正极材料 | 18% | 宁德时代 |
| 电驱 | 电机 | 8% | 汇川技术 |
"""


@pytest.mark.asyncio
async def test_extract_company_share_from_markdown_table():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "2025年新能源汽车份额",
            "url": "https://example.com/share",
            "content": COMPANY_TABLE,
            "evidence_id": "ev-1",
        }
    ]

    records = await extractor.extract(
        documents,
        "company_share",
        {"section_id": "competitive_landscape", "data_need": "头部企业市场份额"},
    )

    assert len(records) == 2
    assert records[0].company_name == "比亚迪"
    assert records[0].share_pct == 32.5
    assert records[0].source_url == "https://example.com/share"
    assert records[0].source_quote


@pytest.mark.asyncio
async def test_extract_bom_from_markdown_table():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "BOM拆解",
            "url": "https://example.com/bom",
            "content": BOM_TABLE,
            "evidence_id": "ev-2",
        }
    ]

    records = await extractor.extract(
        documents,
        "bom_item",
        {"section_id": "technology_trends", "data_need": "BOM成本拆解"},
    )

    assert len(records) == 2
    assert records[0].system == "动力电池"
    assert records[0].component == "正极材料"
    assert records[0].cost_share_pct == 18.0


@pytest.mark.asyncio
async def test_extract_supplier_from_markdown_table():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "供应商关系",
            "url": "https://example.com/supplier",
            "content": """
| 部件 | 供应商 | 客户 |
|---|---|---|
| 动力电池 | 宁德时代 | 比亚迪 |
""",
            "evidence_id": "ev-3",
        }
    ]

    records = await extractor.extract(
        documents,
        "supplier",
        {"section_id": "value_chain", "data_need": "关键供应商"},
    )

    assert len(records) == 1
    assert isinstance(records[0], SupplierRecord)
    assert records[0].supplier_name == "宁德时代"
    assert records[0].component == "动力电池"
    assert records[0].customers == ["比亚迪"]


@pytest.mark.asyncio
async def test_llm_fallback_handles_none_content_without_crashing():
    async def fake_llm(prompt):
        return {"success": True, "content": None}

    extractor = StructuredEvidenceExtractor(llm_call=fake_llm)
    documents = [
        {
            "title": "空文档",
            "url": "https://example.com/empty",
            "content": None,
            "evidence_id": "ev-none",
        }
    ]

    records = await extractor.extract(
        documents,
        "company_share",
        {"section_id": "competitive_landscape", "data_need": "市场份额"},
    )

    assert records == []


@pytest.mark.asyncio
async def test_llm_fallback_normalizes_bom_supplier_names_string():
    async def fake_llm(prompt):
        return {
            "success": True,
            "content": """```json
{"records": [{"system": "动力电池", "component": "正极材料", "cost_share_pct": 18, "supplier_names": "宁德时代", "source_quote": "正极材料成本占比18%", "evidence_id": "ev-llm-bom"}]}
```""",
        }

    extractor = StructuredEvidenceExtractor(llm_call=fake_llm)
    documents = [
        {
            "title": "BOM拆解",
            "url": "https://example.com/llm-bom",
            "content": "无表格",
            "evidence_id": "ev-llm-bom",
        }
    ]

    records = await extractor.extract(
        documents,
        "bom_item",
        {"section_id": "technology_trends", "data_need": "BOM成本拆解"},
    )

    assert len(records) == 1
    assert records[0].supplier_names == ["宁德时代"]


@pytest.mark.asyncio
async def test_llm_fallback_normalizes_supplier_customers_string():
    async def fake_llm(prompt):
        return {
            "success": True,
            "content": """```json
{"records": [{"supplier_name": "宁德时代", "component": "动力电池", "customers": "比亚迪", "source_quote": "宁德时代供应动力电池", "evidence_id": "ev-llm-supplier"}]}
```""",
        }

    extractor = StructuredEvidenceExtractor(llm_call=fake_llm)
    documents = [
        {
            "title": "供应商关系",
            "url": "https://example.com/llm-supplier",
            "content": "无表格",
            "evidence_id": "ev-llm-supplier",
        }
    ]

    records = await extractor.extract(
        documents,
        "supplier",
        {"section_id": "value_chain", "data_need": "关键供应商"},
    )

    assert len(records) == 1
    assert records[0].customers == ["比亚迪"]


@pytest.mark.asyncio
async def test_dedupe_keeps_same_component_under_different_systems():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "BOM拆解",
            "url": "https://example.com/bom-systems",
            "content": """
| 系统 | 部件 | 成本占比 |
|---|---|---|
| 动力电池 | 正极材料 | 18% |
| 电池包 | 正极材料 | 12% |
""",
            "evidence_id": "ev-4",
        }
    ]

    records = await extractor.extract(
        documents,
        "bom_item",
        {"section_id": "technology_trends", "data_need": "BOM成本拆解"},
    )

    assert len(records) == 2
    assert [record.system for record in records] == ["动力电池", "电池包"]


@pytest.mark.asyncio
async def test_extract_markdown_table_without_trailing_pipes():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "2025年新能源汽车份额",
            "url": "https://example.com/no-trailing",
            "content": """
   | 公司 | 市场份额 | 统计口径 | 期间
   | --- | --- | --- | ---
   | 比亚迪 | 32.5% | 销量 | 2025
   | 特斯拉 | 12.0% | 销量 | 2025
""",
            "evidence_id": "ev-5",
        }
    ]

    records = await extractor.extract(
        documents,
        "company_share",
        {"section_id": "competitive_landscape", "data_need": "头部企业市场份额"},
    )

    assert len(records) == 2
    assert records[0].company_name == "比亚迪"
    assert records[0].source_quote == "| 比亚迪 | 32.5% | 销量 | 2025"


@pytest.mark.asyncio
async def test_extract_html_table_with_omitted_end_tags():
    extractor = StructuredEvidenceExtractor()
    documents = [
        {
            "title": "新能源汽车份额",
            "url": "https://example.com/html",
            "content": "<table><tr><td>公司<td>市场份额<tr><td>比亚迪<td>32.5%</table>",
            "evidence_id": "ev-6",
        }
    ]

    records = await extractor.extract(
        documents,
        "company_share",
        {"section_id": "competitive_landscape", "data_need": "头部企业市场份额"},
    )

    assert len(records) == 1
    assert records[0].company_name == "比亚迪"
    assert records[0].share_pct == 32.5
    assert records[0].source_quote == "| 比亚迪 | 32.5% |"


@pytest.mark.asyncio
async def test_llm_prompt_contains_schema_for_each_type():
    captured = {}

    async def fake_llm(prompt: str):
        captured["prompt"] = prompt
        return {"success": True, "content": ""}

    extractor = StructuredEvidenceExtractor(llm_call=fake_llm)
    doc = {
        "title": "行业数据",
        "url": "https://example.com",
        "content": "纯文本资料，没有表格。",
        "evidence_id": "ev-9",
    }

    await extractor.extract([doc], "bom_item", {"section_id": "s", "data_need": "d"})
    assert '"component"' in captured["prompt"]
    assert '"cost_share_pct"' in captured["prompt"]
    assert '"supplier_names"' in captured["prompt"]

    await extractor.extract([doc], "company_share", {"section_id": "s", "data_need": "d"})
    assert '"company_name"' in captured["prompt"]
    assert '"share_pct"' in captured["prompt"]
    assert '"metric_basis"' in captured["prompt"]

    await extractor.extract([doc], "supplier", {"section_id": "s", "data_need": "d"})
    assert '"supplier_name"' in captured["prompt"]
    assert '"customers"' in captured["prompt"]
