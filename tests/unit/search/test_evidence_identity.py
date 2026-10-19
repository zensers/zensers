import pytest
from types import SimpleNamespace

from src.core.search.gateway import SearchGateway, SearchRequest
from src.core.search.query_deduplicator import SearchQueryDeduplicator
from src.core.agents.generic_agent import GenericAgent
from src.core.orchestrator.execution.engine import ExecutionEngine
from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
from src.core.memory.stores.data_point_store import DataPoint as StoredDataPoint
from src.core.analysis.shared_memory_schema import DataPoint as SharedDataPoint


class _Provider:
    async def search(self, request):
        return {
            "results": [{
                "title": "官方统计",
                "url": "https://example.com/statistics",
                "snippet": "市场规模为 100 亿元。",
                "quality_score": 90,
            }]
        }


@pytest.mark.asyncio
async def test_search_results_have_auditable_evidence_identity():
    gateway = SearchGateway(
        task_id="task_evidence_1",
        providers={"test": _Provider()},
        primary_provider="test",
        quality_threshold=50,
    )

    response = await gateway.search(
        SearchRequest(query="市场规模"),
        scope="data_collection",
    )

    assert response.success is True
    result = response.results[0]
    assert result.evidence_id
    assert result.provenance_id
    assert result.excerpt == "市场规模为 100 亿元。"
    assert result.task_id == "task_evidence_1"
    assert result.request_id == response.request_id


@pytest.mark.asyncio
async def test_query_deduplicator_preserves_evidence_identity():
    gateway = SearchGateway(
        task_id="task_evidence_2",
        providers={"test": _Provider()},
        primary_provider="test",
        quality_threshold=50,
    )
    deduplicator = SearchQueryDeduplicator(gateway=gateway)

    result = await deduplicator.search("市场规模", "section_market")

    item = result["results"][0]
    assert item["evidence_id"]
    assert item["provenance_id"]
    assert item["evidence_excerpt"]
    assert item["locator"] == item["url"]


@pytest.mark.asyncio
async def test_cached_search_keeps_evidence_identity_stable():
    gateway = SearchGateway(
        task_id="task_evidence_3",
        providers={"test": _Provider()},
        primary_provider="test",
        quality_threshold=50,
    )
    request = SearchRequest(query="市场规模")

    first = await gateway.search(request, scope="data_collection")
    second = await gateway.search(request, scope="data_collection")

    assert second.cache_hit is True
    assert second.results[0].evidence_id == first.results[0].evidence_id
    assert second.results[0].provenance_id == first.results[0].provenance_id


@pytest.mark.asyncio
async def test_generic_agent_gap_fill_preserves_evidence_identity():
    class LegacySearch:
        async def execute(self, **kwargs):
            return {
                "success": True,
                "results": [{
                    "title": "预测统计报告",
                    "url": "https://example.com/forecast",
                    "body": "2030 年市场规模预计达到 100 亿元。",
                    "quality_score": 90,
                    "evidence_id": "ev-gap-1",
                    "provenance_id": "prov-gap-1",
                    "evidence_excerpt": "2030 年市场规模预计达到 100 亿元。",
                    "locator": "https://example.com/forecast#p3",
                    "task_id": "task-gap-1",
                    "request_id": "req-gap-1",
                    "retrieved_at": "2026-09-06T00:00:00+00:00",
                }],
            }

    agent = GenericAgent(agent_id="generic-evidence", config={})
    result = await agent._supplementary_search_for_gaps(
        "储能市场",
        "市场规模",
        ["quantitative statistics"],
        {"search_skill": LegacySearch()},
    )

    assert result["data_points"][0]["evidence_id"] == "ev-gap-1"
    assert result["data_points"][0]["provenance_id"] == "prov-gap-1"
    assert result["data_points"][0]["evidence_excerpt"]
    assert result["data_points"][0]["locator"].endswith("#p3")
    assert result["sources"][0]["provenance_id"] == "prov-gap-1"


@pytest.mark.asyncio
async def test_generic_agent_search_projection_preserves_evidence_identity(monkeypatch):
    agent = GenericAgent(agent_id="generic-search-evidence", config={})

    async def fake_deep_research(**kwargs):
        return {
            "searches": [{
                "query": "市场规模",
                "results": [{
                    "title": "搜索证据",
                    "url": "https://example.com/search",
                    "snippet": "可引用摘录",
                    "evidence_id": "ev-search-1",
                    "provenance_id": "prov-search-1",
                    "evidence_excerpt": "可引用摘录",
                    "locator": "https://example.com/search#p4",
                    "task_id": "task-search-1",
                    "request_id": "req-search-1",
                }],
            }],
            "total_sources": 1,
            "quality_stats": {},
        }

    monkeypatch.setattr(agent, "_do_deep_research", fake_deep_research)
    result = await agent._process_search_skill(
        skill=None,
        topic="储能市场",
        aspect="市场规模",
        skill_registry={},
    )

    assert result["data_points"][0]["provenance_id"] == "prov-search-1"
    assert result["sources"][0]["evidence_id"] == "ev-search-1"


def test_generic_agent_standard_result_preserves_raw_search_evidence():
    agent = GenericAgent(agent_id="generic-standard-evidence", config={})
    result = agent._ensure_standard_result({
        "success": True,
        "results": [{
            "title": "标准化证据",
            "url": "https://example.com/standard",
            "snippet": "标准化摘录",
            "evidence_id": "ev-standard-1",
            "provenance_id": "prov-standard-1",
            "evidence_excerpt": "标准化摘录",
        }],
    }, "search")

    assert result["sources"][0]["evidence_id"] == "ev-standard-1"
    assert result["sources"][0]["provenance_id"] == "prov-standard-1"


@pytest.mark.asyncio
async def test_execution_engine_supplement_preserves_evidence_identity():
    class Deduplicator:
        async def search(self, query, section_id, skill, scope):
            return {
                "results": [{
                    "title": "补充证据",
                    "url": "https://example.com/supplement",
                    "snippet": "补充摘录",
                    "evidence_id": "ev-supplement-1",
                    "provenance_id": "prov-supplement-1",
                    "evidence_excerpt": "补充摘录",
                    "locator": "https://example.com/supplement#p5",
                    "task_id": "task-supplement-1",
                    "request_id": "req-supplement-1",
                }]
            }

    engine = ExecutionEngine.__new__(ExecutionEngine)
    engine.search_gateway = object()
    engine._search_deduplicator = Deduplicator()
    engine._previous_all_results = []
    engine._section_data_specs = [
        SimpleNamespace(section_id="section_market", search_data_needs=["市场规模"])
    ]

    result = await engine._supplement_missing_data(
        batch_results=[{"success": True, "data_points": []}],
        requirement={"topic": "储能市场"},
        max_rounds=1,
        coverage_threshold=1.0,
    )

    item = result["市场规模"]["data_points"][0]
    assert item["evidence_id"] == "ev-supplement-1"
    assert item["provenance_id"] == "prov-supplement-1"
    assert result["市场规模"]["sources"][0]["locator"].endswith("#p5")


def test_research_result_store_does_not_keep_stale_unverified_url_record(tmp_path):
    store = ResearchResultStore(str(tmp_path))
    task_id = "task-evidence-store"
    url = "https://example.com/same-source"

    store.save_result(
        task_id,
        {
            "data_points": [{"title": "旧结果", "url": url}],
            "sources": [{"title": "旧结果", "url": url}],
        },
        status=ResearchStatus.COLLECTING,
    )
    store.save_result(
        task_id,
        {
            "data_points": [{
                "title": "完整结果",
                "url": url,
                "evidence_id": "ev-store-1",
                "provenance_id": "prov-store-1",
                "evidence_excerpt": "完整摘录",
            }],
            "sources": [{
                "title": "完整结果",
                "url": url,
                "evidence_id": "ev-store-1",
                "provenance_id": "prov-store-1",
                "evidence_excerpt": "完整摘录",
            }],
        },
        status=ResearchStatus.COLLECTING,
    )

    saved = store.load_result(task_id)
    assert saved["data_points"][0]["provenance_id"] == "prov-store-1"
    assert saved["sources"][0]["evidence_id"] == "ev-store-1"


def test_memory_data_point_serialization_preserves_source_reference():
    point = StoredDataPoint(
        data_id="data-evidence-1",
        entity_id="entity-1",
        metric_name="市场规模",
        metric_value="100",
        source_ref="prov-store-1",
    )

    assert point.to_dict()["source_ref"] == "prov-store-1"


def test_shared_memory_data_point_round_trip_preserves_evidence_identity():
    point = SharedDataPoint(
        metric="市场规模",
        value="100",
        source="官方报告",
        source_url="https://example.com/shared",
        evidence_id="ev-shared-1",
        provenance_id="prov-shared-1",
        evidence_excerpt="共享摘录",
    )

    restored = SharedDataPoint.from_dict(point.to_dict())
    assert restored.source_url == "https://example.com/shared"
    assert restored.evidence_id == "ev-shared-1"
    assert restored.provenance_id == "prov-shared-1"
    assert restored.evidence_excerpt == "共享摘录"
