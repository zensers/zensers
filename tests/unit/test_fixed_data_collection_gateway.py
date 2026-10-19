import pytest
from datetime import datetime, timezone

from src.agents.fixed_agents.data_collection_agent import DataCollectionAgent
from src.core.search import SearchGateway, SearchRequest
from src.core.search.gateway import SearchResponse, SearchResult


class Provider:
    async def search(self, request: SearchRequest):
        return {
            "results": [{
                "title": "真实来源",
                "url": "https://source.example/report",
                "snippet": "市场规模数据",
                "source": "official",
                "quality_score": 90,
            }]
        }


@pytest.mark.anyio
async def test_fixed_data_collection_uses_injected_gateway():
    gateway = SearchGateway(
        task_id="task-fixed-collector",
        providers={"fake": Provider()},
        primary_provider="fake",
        task_max_searches=1,
        default_scope_max_searches=1,
        quality_threshold=70,
    )
    agent = DataCollectionAgent(
        "collector",
        "collector",
        search_gateway=gateway,
    )

    result = await agent.execute({"query": "市场规模", "max_results": 5})

    assert result["success"] is True
    assert result["data"][0]["url"] == "https://source.example/report"
    assert gateway.get_stats()["task_used_searches"] == 1


@pytest.mark.anyio
async def test_fixed_data_collection_preserves_evidence_identity():
    class IdentityGateway:
        async def search(self, request, scope=None):
            return SearchResponse(
                schema_version="v1",
                success=True,
                results=[
                    SearchResult(
                        title="可审计来源",
                        url="https://source.example/auditable",
                        snippet="正文证据摘录",
                        source="official",
                        evidence_id="ev-fixed-1",
                        provenance_id="prov-fixed-1",
                        excerpt="正文证据摘录",
                        locator="https://source.example/auditable#p2",
                        task_id="task-fixed-collector",
                        request_id="req-fixed-1",
                        retrieved_at="2026-09-06T00:00:00+00:00",
                    )
                ],
                provider="fake",
                request_id="req-fixed-1",
                task_id="task-fixed-collector",
                intent_id=None,
                provider_status={"message": "ok"},
                quality_score=90,
                source_count=1,
                high_quality_count=1,
                retries=0,
                cache_hit=False,
                estimated_cost=0.0,
                fetched_at=datetime.now(timezone.utc),
            )

    agent = DataCollectionAgent(
        "collector",
        "collector",
        search_gateway=IdentityGateway(),
    )

    result = await agent._collect_from_gateway("市场规模", 5, {})

    item = result["data"][0]
    assert item["evidence_id"] == "ev-fixed-1"
    assert item["provenance_id"] == "prov-fixed-1"
    assert item["evidence_excerpt"] == "正文证据摘录"
    assert item["locator"] == "https://source.example/auditable#p2"
    assert item["task_id"] == "task-fixed-collector"
    assert item["request_id"] == "req-fixed-1"
    assert item["retrieved_at"] == "2026-09-06T00:00:00+00:00"


@pytest.mark.anyio
async def test_fixed_data_collection_rejects_web_search_without_gateway():
    agent = DataCollectionAgent("collector", "collector")
    result = await agent.execute({"query": "市场规模", "max_results": 5})
    assert result["success"] is False
    assert result["data"] == []
    assert "mock data is disabled" in result["errors"][0]["error"]
