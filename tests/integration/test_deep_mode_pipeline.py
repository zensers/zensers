from datetime import datetime, timezone

import pytest

from src.core.deep_mode.config import DeepModeConfig
from src.core.deep_mode.service import DeepModeService
from src.core.search.gateway import SearchResponse, SearchResult

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

SUPPLIER_TABLE = """
| 部件 | 供应商 | 客户 |
|---|---|---|
| 动力电池 | 宁德时代 | 比亚迪 |
| 电驱 | 汇川技术 | 比亚迪 |
"""


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def search(self, request, scope="default"):
        self.calls.append((request.query, scope))
        if "BOM" in request.query or "成本" in request.query:
            table = BOM_TABLE
        elif "供应商" in request.query:
            table = SUPPLIER_TABLE
        else:
            table = COMPANY_TABLE
        return SearchResponse(
            schema_version="1",
            request_id="r1",
            task_id="t1",
            intent_id=None,
            success=True,
            results=[
                SearchResult(
                    title="行业数据",
                    url="https://example.com/source",
                    snippet=table,
                    evidence_id="ev-1",
                    quality_score=80,
                )
            ],
            provider="fake",
            provider_status={},
            quality_score=80,
            source_count=1,
            high_quality_count=1,
            retries=0,
            cache_hit=False,
            estimated_cost=None,
            fetched_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_pipeline_generates_three_tables(tmp_path):
    gateway = FakeGateway()
    service = DeepModeService(
        config=DeepModeConfig(max_searches=12),
        gateway_provider=lambda: gateway,
        store_dir=tmp_path,
    )
    sections = [
        {"id": "competitive_landscape", "name": "竞争格局", "points": ["市场份额"]},
        {"id": "technology_trends", "name": "技术趋势", "points": ["BOM"]},
        {"id": "value_chain", "name": "产业链", "points": ["供应商"]},
    ]

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=sections,
        output_type="industry_report",
        companies=["比亚迪", "特斯拉"],
        task_id="task-integration",
    )

    assert records["competitive_landscape"]
    assert records["technology_trends"]
    assert records["value_chain"]
    assert "| 公司 | 市场份额 |" in service.get_tables("competitive_landscape")
    assert "| 系统 | 部件 |" in service.get_tables("technology_trends")
    assert "| 环节 | 主要供应商 |" in service.get_tables("value_chain")
    assert (tmp_path / "task-integration" / "validation.json").exists()
