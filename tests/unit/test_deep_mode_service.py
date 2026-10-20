from datetime import datetime, timezone

import pytest

from src.core.deep_mode.config import DeepModeConfig
from src.core.deep_mode.models import CompanyShareRecord
from src.core.deep_mode.service import DeepModeService
from src.core.search.gateway import SearchResponse, SearchResult

COMPANY_TABLE = """
| 公司 | 市场份额 | 统计口径 | 期间 |
|---|---|---|---|
| 比亚迪 | 32.5% | 销量 | 2025 |
| 特斯拉 | 12.0% | 销量 | 2025 |
"""

PLAIN_TEXT = "新能源汽车市场持续增长，竞争加剧，头部企业优势明显。"

SECTIONS = [
    {
        "id": "competitive_landscape",
        "name": "竞争格局",
        "points": ["头部企业市场份额"],
    },
    {"id": "technology_trends", "name": "技术趋势", "points": ["BOM"]},
    {"id": "value_chain", "name": "产业链", "points": ["供应商"]},
]


def _response(success=True, stop_reason=None):
    return SearchResponse(
        schema_version="1",
        request_id="r1",
        task_id="t1",
        intent_id=None,
        success=success,
        results=[
            SearchResult(
                title="行业份额",
                url="https://example.com/share",
                snippet=COMPANY_TABLE,
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
        stop_reason=stop_reason,
    )


def _table_response(success=True, stop_reason=None, snippet=COMPANY_TABLE):
    response = _response(success=success, stop_reason=stop_reason)
    response.results[0].snippet = snippet
    return response


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def search(self, request, scope="default"):
        self.calls.append((request.query, scope))
        return _table_response()


class FlakyGateway(FakeGateway):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    async def search(self, request, scope="default"):
        if not self.failed_once:
            self.failed_once = True
            raise RuntimeError("gateway boom")
        return await super().search(request, scope=scope)


class DeadGateway:
    def __init__(self):
        self.calls = []

    async def search(self, request, *, scope="default"):
        self.calls.append((request.query, scope))
        return _table_response(success=False, stop_reason="max_searches_reached")


class StrictScraper:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("scraper must not be called")


class TablesScraper:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "message": "Extracted 1 tables",
            "tables": [[["公司", "市场份额"], ["比亚迪", "32.5%"]]],
            "count": 1,
            "url": kwargs.get("url", ""),
        }


def _service(tmp_path, gateway, scraper=None, config=None):
    return DeepModeService(
        config=config or DeepModeConfig(),
        gateway_provider=lambda: gateway,
        scraper_provider=(lambda: scraper) if scraper is not None else None,
        store_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_service_enriches_and_builds_table(tmp_path):
    gateway = FakeGateway()
    service = DeepModeService(
        config=DeepModeConfig(max_searches=6),
        gateway_provider=lambda: gateway,
        store_dir=tmp_path,
    )

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        companies=["比亚迪", "特斯拉"],
        task_id="task-1",
    )

    assert "competitive_landscape" in records
    assert records["competitive_landscape"][0]["record_type"] == "company_share"
    assert "比亚迪" in service.get_tables("competitive_landscape")
    assert len(gateway.calls) <= 6
    assert all(scope == "deep_mode" for _, scope in gateway.calls)
    assert (tmp_path / "task-1" / "summary.json").exists()


@pytest.mark.asyncio
async def test_service_ignores_non_industry(tmp_path):
    service = DeepModeService(
        config=DeepModeConfig(),
        gateway_provider=lambda: FakeGateway(),
        store_dir=tmp_path,
    )

    records = await service.enrich(
        topic="宁德时代",
        section_specs=[{"id": "summary", "name": "Summary", "points": []}],
        output_type="company_report",
        task_id="task-2",
    )

    assert records == {}


def test_ensure_tables_appends_table(tmp_path):
    service = _service(tmp_path, FakeGateway())
    point = CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="头部企业市场份额",
        source_url="https://example.com/share",
        source_quote="| 比亚迪 | 32.5% | 销量 | 2025 |",
        evidence_id="ev-1",
        period="2025",
        company_name="比亚迪",
        share_pct=32.5,
        metric_basis="销量",
    ).to_data_point()
    results = [{"agent_id": "a1", "content": "正文。", "data_points": [point]}]

    service.ensure_tables(results, {"a1": "competitive_landscape"})

    assert "正文。" in results[0]["content"]
    assert "| 公司 | 市场份额 |" in results[0]["content"]


def test_ensure_tables_skips_unknown_agent(tmp_path):
    service = _service(tmp_path, FakeGateway())
    results = [{"agent_id": "unknown", "content": "正文。", "data_points": []}]

    service.ensure_tables(results, {"a1": "competitive_landscape"})

    assert results[0]["content"] == "正文。"


@pytest.mark.asyncio
async def test_disabled_config_short_circuits(tmp_path):
    gateway = FakeGateway()
    service = _service(
        tmp_path,
        gateway,
        config=DeepModeConfig(enabled=False),
    )

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        task_id="task-off",
    )

    assert records == {}
    assert gateway.calls == []
    assert not (tmp_path / "task-off").exists()


@pytest.mark.asyncio
async def test_gateway_raise_continues_remaining_queries(tmp_path):
    gateway = FlakyGateway()
    service = _service(tmp_path, gateway)

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        companies=["比亚迪"],
        task_id="task-flaky",
    )

    assert "competitive_landscape" in records
    assert any("error" in entry for entry in service._last_validation)


@pytest.mark.asyncio
async def test_gateway_hard_failure_breaks_loop(tmp_path):
    gateway = DeadGateway()
    service = _service(tmp_path, gateway)

    await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        companies=["比亚迪"],
        task_id="task-dead",
    )

    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_snippet_table_skips_scrape(tmp_path):
    gateway = FakeGateway()
    scraper = StrictScraper()
    service = _service(tmp_path, gateway, scraper=scraper)

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        companies=["比亚迪"],
        task_id="task-snippet",
    )

    assert "competitive_landscape" in records
    assert scraper.calls == []


@pytest.mark.asyncio
async def test_scraper_tables_action_builds_content(tmp_path):
    gateway = _table_response(snippet=PLAIN_TEXT)

    class PlainGateway(FakeGateway):
        async def search(self, request, scope="default"):
            self.calls.append((request.query, scope))
            return gateway

    scraper = TablesScraper()
    service = DeepModeService(
        config=DeepModeConfig(
            min_queries_per_section=1,
            max_queries_per_section=1,
            max_searches=1,
        ),
        gateway_provider=lambda: PlainGateway(),
        scraper_provider=lambda: scraper,
        store_dir=tmp_path,
    )

    records = await service.enrich(
        topic="新能源汽车",
        section_specs=SECTIONS,
        output_type="industry_report",
        companies=["比亚迪"],
        task_id="task-tables",
    )

    assert len(scraper.calls) == 1
    assert scraper.calls[0].get("action") == "extract_tables"
    assert scraper.calls[0].get("max_chars") == 3000
    assert "competitive_landscape" in records
    assert any(
        point["structured_data"].get("company_name") == "比亚迪"
        for point in records["competitive_landscape"]
    )


def test_dedupe_keeps_distinct_metric_basis():
    def _point(basis):
        return CompanyShareRecord(
            section_id="competitive_landscape",
            data_need="头部企业市场份额",
            source_url="https://example.com/share",
            source_quote="quote",
            evidence_id="ev-1",
            period="2025",
            company_name="比亚迪",
            share_pct=32.5,
            metric_basis=basis,
        ).to_data_point()

    kept, removed = DeepModeService._dedupe_points([_point("shipments"), _point("revenue")])

    assert len(kept) == 2
    assert removed == 0
