import pytest

from src.core.search.anysearch_provider import AnySearchProvider, SearchProviderError
from src.core.search.gateway import SearchRequest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def request():
    return SearchRequest(query="  新能源汽车  市场规模 ", max_results=5)


@pytest.mark.anyio
async def test_anysearch_posts_normalized_request_and_auth_header():
    client = FakeClient(FakeResponse({
        "code": 0,
        "data": {"results": [{
            "title": "权威来源", "url": "https://example.com/a",
            "content": "摘要", "published_at": "2026-09-01",
            "quality_score": 88,
        }]},
    }))
    provider = AnySearchProvider(api_key="secret", client=client)

    result = await provider.search(request())

    assert result["success"] is True
    assert result["results"][0]["snippet"] == "摘要"
    url, kwargs = client.calls[0]
    assert url == "https://api.anysearch.com/v1/search"
    assert kwargs["json"] == {"query": "新能源汽车 市场规模", "max_results": 5, "zone": "cn"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert "secret" not in repr(result)


@pytest.mark.anyio
async def test_anysearch_without_key_uses_anonymous_headers():
    client = FakeClient(FakeResponse({"code": 0, "data": {"results": []}}))
    provider = AnySearchProvider(api_key="", client=client)

    result = await provider.search(request())

    assert result["success"] is True
    headers = client.calls[0][1]["headers"]
    assert "Authorization" not in headers
    assert headers["X-Anysearch-Client"].startswith("market-report/")


@pytest.mark.anyio
async def test_anysearch_quota_error_is_classified_without_leaking_payload():
    client = FakeClient(FakeResponse({
        "code": 429,
        "message": "quota exhausted",
        "data": {"api_key": "should-not-be-returned"},
    }, status_code=429))
    provider = AnySearchProvider(client=client)

    with pytest.raises(SearchProviderError) as error:
        await provider.search(request())

    assert error.value.category == "rate_limited"
    assert "should-not-be-returned" not in str(error.value)
