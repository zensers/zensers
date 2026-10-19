"""Contract tests for the task-scoped SearchGateway.

These tests intentionally describe the architecture before its implementation.
Provider doubles expose an async ``search(request)`` method and may return a
mapping with ``results`` or a list of provider result mappings.
"""

import asyncio
from copy import deepcopy

import pytest

from src.core.search.gateway import (
    GatewaySearchSkillAdapter,
    LegacySkillProvider,
    SearchGateway,
    SearchRequest,
    SearchResult,
)
from src.core.search.anysearch_provider import SearchProviderError


class FakeProvider:
    def __init__(self, name="fake", response=None, error=None, delay=0):
        self.name = name
        self.response = response if response is not None else {"results": []}
        self.error = error
        self.delay = delay
        self.calls = []

    async def search(self, request):
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return deepcopy(self.response)


def result_payload(title="权威来源", url="https://example.com/a", score=90):
    return {
        "title": title,
        "url": url,
        "snippet": "摘要",
        "published_at": "2026-09-01",
        "quality_score": score,
    }


def request(**overrides):
    values = {
        "query": "  新能源汽车  市场规模 ",
        "objective": "market_size",
        "region": "cn-cn",
        "time_range": "m",
        "depth": "auto",
        "max_results": 8,
        "livecrawl": "fallback",
        "allowed_domains": ["B.com", "a.com"],
        "query_revision": 0,
        "provider_capability_version": "v1",
        "source_mode": "provider_pool",
    }
    values.update(overrides)
    return SearchRequest(**values)


def test_request_normalization_and_cache_key_include_all_semantic_fields():
    first = request()
    second = request(allowed_domains=["a.com", "b.com"])

    assert first.normalized_query == "新能源汽车 市场规模"
    assert first.cache_key() == second.cache_key()
    assert request(max_results=5).cache_key() != first.cache_key()
    assert request(livecrawl="always").cache_key() != first.cache_key()
    assert request(query_revision=1).cache_key() != first.cache_key()
    assert request(provider_capability_version="v2").cache_key() != first.cache_key()
    assert request(source_mode="local").cache_key() != first.cache_key()


@pytest.mark.anyio
async def test_same_task_single_flight_executes_provider_once_and_returns_copies():
    provider = FakeProvider(
        response={"results": [result_payload()]},
        delay=0.02,
    )
    gateway = SearchGateway(
        task_id="task-1",
        providers={"fake": provider},
        primary_provider="fake",
        cache_ttl_seconds=60,
        min_quality_score=70,
    )

    responses = await asyncio.gather(
        gateway.search(request()),
        gateway.search(request()),
        gateway.search(request()),
    )

    assert len(provider.calls) == 1
    assert all(response.success for response in responses)
    assert responses[1].cache_hit is True
    assert responses[0].results is not responses[1].results
    responses[0].results[0].title = "被调用方修改"
    assert responses[1].results[0].title == "权威来源"


@pytest.mark.anyio
async def test_cache_ttl_zero_does_not_reuse_completed_result():
    provider = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-ttl",
        providers={"fake": provider},
        primary_provider="fake",
        cache_ttl_seconds=0,
    )

    first = await gateway.search(request())
    second = await gateway.search(request())

    assert first.success and second.success
    assert len(provider.calls) == 2
    assert second.cache_hit is False


@pytest.mark.anyio
async def test_transient_error_retries_within_total_budget():
    provider = FakeProvider(response={"results": [result_payload()]})
    original = provider.search
    attempts = 0

    async def flaky(req):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary timeout")
        return await original(req)

    provider.search = flaky
    gateway = SearchGateway(
        task_id="task-retry",
        providers={"fake": provider},
        primary_provider="fake",
        max_provider_retries=1,
    )

    response = await gateway.search(request())

    assert response.success is True
    assert response.retries == 1
    assert response.provider_status["error_class"] is None


@pytest.mark.anyio
async def test_provider_failure_switches_to_fallback_without_blocking_task():
    primary = FakeProvider(name="primary", error=TimeoutError("down"))
    fallback = FakeProvider(
        name="fallback",
        response={"results": [result_payload()]},
    )
    gateway = SearchGateway(
        task_id="task-fallback",
        providers={"primary": primary, "fallback": fallback},
        primary_provider="primary",
        fallback_providers=["fallback"],
        max_provider_retries=0,
        max_provider_switches=1,
    )

    response = await gateway.search(request())

    assert response.success is True
    assert response.provider == "fallback"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.anyio
async def test_provider_specific_rate_limit_is_preserved_and_falls_back():
    primary = FakeProvider(
        name="anysearch",
        error=SearchProviderError("quota", category="rate_limited", status_code=429),
    )
    fallback = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-rate-limit",
        providers={"anysearch": primary, "local": fallback},
        primary_provider="anysearch",
        fallback_providers=["local"],
        max_provider_retries=1,
        max_provider_switches=1,
    )

    response = await gateway.search(request())

    assert response.success is True
    assert response.provider == "local"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.anyio
async def test_empty_provider_results_are_reported_as_no_results_and_fall_back():
    primary = FakeProvider(name="anysearch", response={"results": []})
    fallback = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-empty", providers={"anysearch": primary, "local": fallback},
        primary_provider="anysearch", fallback_providers=["local"],
        max_provider_retries=0, max_provider_switches=1,
    )
    response = await gateway.search(request())
    assert response.success is True
    assert response.provider == "local"


@pytest.mark.anyio
async def test_all_empty_providers_return_unified_error_fields():
    gateway = SearchGateway(
        task_id="task-all-empty", providers={"local": FakeProvider(response={"results": []})},
        primary_provider="local", max_provider_retries=0,
    )
    response = await gateway.search(request())
    assert response.success is False
    assert response.error_class == "no_results"
    assert response.message


@pytest.mark.anyio
async def test_auth_error_is_not_retried_on_same_provider():
    provider = FakeProvider(error=PermissionError("invalid api key"))
    gateway = SearchGateway(
        task_id="task-auth",
        providers={"fake": provider},
        primary_provider="fake",
        max_provider_retries=3,
    )

    response = await gateway.search(request())

    assert response.success is False
    assert response.provider_status["error_class"] == "auth_error"
    assert response.retries == 0
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_results_are_standardized_and_low_quality_results_are_filtered():
    provider = FakeProvider(
        response={
            "results": [
                {"title": "低质量", "href": "https://spam.example", "body": "广告", "quality_score": 20},
                result_payload(score=85),
            ]
        }
    )
    gateway = SearchGateway(
        task_id="task-quality",
        providers={"fake": provider},
        primary_provider="fake",
        min_quality_score=70,
    )

    response = await gateway.search(request())

    assert response.success is True
    assert len(response.results) == 1
    assert isinstance(response.results[0], SearchResult)
    assert response.results[0].url == "https://example.com/a"
    assert response.quality_score >= 70
    assert response.high_quality_count == 1


@pytest.mark.anyio
async def test_quality_insufficient_is_reported_without_infinite_retry():
    provider = FakeProvider(
        response={"results": [result_payload(score=30)]}
    )
    gateway = SearchGateway(
        task_id="task-insufficient",
        providers={"fake": provider},
        primary_provider="fake",
        min_quality_score=70,
        max_provider_retries=0,
    )

    response = await gateway.search(request())

    assert response.success is False
    assert response.provider_status["error_class"] == "quality_insufficient"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_legacy_adapter_preserves_dict_skill_contract():
    class LegacySkill:
        def __init__(self):
            self.calls = []

        async def execute(self, **kwargs):
            self.calls.append(kwargs)
            return {"success": True, "results": [result_payload()]}

    legacy_skill = LegacySkill()
    gateway = SearchGateway(
        task_id="task-legacy",
        providers={"legacy": LegacySkillProvider(legacy_skill)},
        primary_provider="legacy",
        min_quality_score=70,
    )

    result = await GatewaySearchSkillAdapter(gateway).execute(
        query="  新能源汽车 市场规模 ", max_results=5, region="cn-cn"
    )

    assert result["success"] is True
    assert result["query"] == "新能源汽车 市场规模"
    assert result["total"] == 1
    assert result["results"][0]["url"] == "https://example.com/a"
    assert legacy_skill.calls[0]["max_results"] == 5


@pytest.mark.anyio
async def test_task_and_scope_budgets_are_enforced_atomically():
    provider = FakeProvider(response={"results": [result_payload()]}, delay=0.02)
    gateway = SearchGateway(
        task_id="task-budget",
        providers={"fake": provider},
        primary_provider="fake",
        task_max_searches=2,
        default_scope_max_searches=2,
        scope_max_searches={"repair": 1},
    )

    responses = await asyncio.gather(
        gateway.search(request(query="q1"), scope="research"),
        gateway.search(request(query="q2"), scope="repair"),
        gateway.search(request(query="q3"), scope="research"),
    )

    assert sum(response.success for response in responses) == 2
    assert gateway.get_stats()["task_used_searches"] == 2
    assert gateway.get_stats()["scope_used_searches"]["repair"] == 1
    exhausted = [r for r in responses if not r.success][0]
    assert exhausted.error_class == "budget_exhausted"
    assert exhausted.stop_reason == "max_searches_reached"
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_cache_hit_does_not_consume_task_or_scope_budget():
    provider = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-cache-budget",
        providers={"fake": provider},
        primary_provider="fake",
        task_max_searches=1,
        default_scope_max_searches=1,
    )

    first = await gateway.search(request(), scope="research")
    second = await gateway.search(request(), scope="research")

    assert first.success and second.success
    assert second.cache_hit is True
    stats = gateway.get_stats()
    assert stats["task_used_searches"] == 1
    assert stats["scope_used_searches"] == {"research": 1}
    assert stats["cache_hits"] == 1
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_adapter_forwards_scope_and_exposes_stop_fields():
    provider = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-adapter-scope",
        providers={"fake": provider},
        primary_provider="fake",
        task_max_searches=1,
        quality_threshold=70,
    )

    result = await GatewaySearchSkillAdapter(gateway, scope="report_repair").execute(
        query="q"
    )

    assert result["stop_reason"] == "quality_reached"
    assert result["fallback_attempted"] is False
    assert gateway.get_stats()["scope_used_searches"] == {"report_repair": 1}


@pytest.mark.anyio
async def test_gateway_enforces_requested_result_limit_and_rejects_unsafe_urls():
    provider = FakeProvider(response={"results": [
        result_payload(title="one", url="https://example.com/1"),
        result_payload(title="two", url="https://example.com/2"),
        result_payload(title="script", url="javascript:alert(1)"),
    ]})
    gateway = SearchGateway(
        task_id="task-result-limit",
        providers={"fake": provider},
        primary_provider="fake",
        min_quality_score=70,
    )
    response = await gateway.search(request(max_results=3))
    assert response.success is True
    assert len(response.results) == 2
    assert response.results[0].url == "https://example.com/1"


@pytest.mark.anyio
async def test_unknown_scope_returns_contract_error_without_consuming_budget():
    provider = FakeProvider(response={"results": [result_payload()]})
    gateway = SearchGateway(
        task_id="task-unknown-scope",
        providers={"fake": provider},
        primary_provider="fake",
        task_max_searches=1,
    )
    response = await gateway.search(request(), scope="typo_scope")
    assert response.success is False
    assert response.error_class == "provider_contract_error"
    assert response.stop_reason == "invalid_scope"
    assert gateway.get_stats()["task_used_searches"] == 0
    assert provider.calls == []
