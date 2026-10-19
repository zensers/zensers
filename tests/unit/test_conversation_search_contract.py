import pytest

from src.api.research_api import ConversationToolSet
from src.core.search import SearchResponse, SearchResult
from datetime import datetime, timezone


class Gateway:
    async def search(self, request, *, scope, intent_id=None):
        return SearchResponse(
            schema_version="1.0",
            request_id="request-1",
            task_id="conversation-test",
            intent_id=intent_id,
            success=True,
            results=[SearchResult(
                title="标题",
                url="https://source.example/item",
                snippet="摘要",
                source="fake",
                quality_score=88,
            )],
            provider="fake",
            provider_status={"error_class": None, "message": None},
            quality_score=88,
            source_count=1,
            high_quality_count=1,
            retries=0,
            cache_hit=False,
            estimated_cost=None,
            fetched_at=datetime.now(timezone.utc),
            stop_reason="quality_reached",
        )


@pytest.mark.anyio
async def test_conversation_search_exposes_top_level_search_contract():
    tools = ConversationToolSet()
    tools._search_gateway = Gateway()

    result = await tools.web_search("测试", max_results=1)

    assert result["results"][0]["url"] == "https://source.example/item"
    assert result["data"] == result["results"]
    assert result["provider"] == "fake"
    assert result["quality_score"] == 88
    assert result["stop_reason"] == "quality_reached"
