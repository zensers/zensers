import pytest

from src.core.search import AnySearchProvider, get_search_config


def test_search_config_reads_and_validates_environment_without_exposing_key():
    config = get_search_config(environ={
        "ANYSEARCH_API_KEY": "  secret-key  ",
        "ANYSEARCH_API_BASE_URL": "https://search.example.test/",
    })
    assert config.api_key == "secret-key"
    assert config.base_url == "https://search.example.test"
    assert config.configured is True
    assert "secret-key" not in repr(config)


def test_search_config_rejects_non_http_url():
    with pytest.raises(ValueError, match="absolute HTTP\(S\) URL"):
        get_search_config(environ={"ANYSEARCH_API_BASE_URL": "file:///tmp/search"})


@pytest.mark.anyio
async def test_health_check_returns_safe_status():
    class Response:
        status_code = 200

    class Client:
        async def get(self, url, **kwargs):
            assert url.endswith("/health")
            assert kwargs["headers"]["Authorization"] == "Bearer secret"
            return Response()

    result = await AnySearchProvider(api_key="secret", client=Client()).health_check()
    assert result["healthy"] is True
    assert "secret" not in repr(result)
