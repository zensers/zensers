import pytest
from unittest.mock import patch, MagicMock
from src.config.llm_profiles import LLMProfile
from src.core.llm_client_pool import LLMClientPool


def _mock_profile(name="test", api_key="sk-test", base_url="https://test.api.com/v1"):
    return LLMProfile(name=name, api_key=api_key, base_url=base_url)


class TestLLMClientPoolGetClient:
    @pytest.mark.asyncio
    async def test_get_client_creates_asyncopenai(self):
        pool = LLMClientPool()
        profile = _mock_profile()
        with patch("src.core.llm_client_pool.AsyncOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            client = await pool.get_client(profile)
            mock_openai.assert_called_once_with(api_key="sk-test", base_url="https://test.api.com/v1",
                                                max_retries=0)
            assert client == mock_instance

    @pytest.mark.asyncio
    async def test_get_client_returns_cached_instance(self):
        pool = LLMClientPool()
        profile = _mock_profile()
        with patch("src.core.llm_client_pool.AsyncOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            c1 = await pool.get_client(profile)
            c2 = await pool.get_client(profile)
            assert mock_openai.call_count == 1
            assert c1 is c2

    @pytest.mark.asyncio
    async def test_different_profiles_get_different_clients(self):
        pool = LLMClientPool()
        p1 = _mock_profile(name="deepseek")
        p2 = _mock_profile(name="zhipu")
        with patch("src.core.llm_client_pool.AsyncOpenAI") as mock_openai:
            mock1 = MagicMock()
            mock2 = MagicMock()
            mock_openai.side_effect = [mock1, mock2]
            c1 = await pool.get_client(p1)
            c2 = await pool.get_client(p2)
            assert c1 is mock1
            assert c2 is mock2
            assert mock_openai.call_count == 2


class TestLLMClientPoolInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_removes_cached_client(self):
        pool = LLMClientPool()
        profile = _mock_profile()
        with patch("src.core.llm_client_pool.AsyncOpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            await pool.get_client(profile)
            assert "test" in pool._clients
            pool.invalidate("test")
            assert "test" not in pool._clients
            await pool.get_client(profile)
            assert mock_openai.call_count == 2

    def test_invalidate_all_clears_cache(self):
        pool = LLMClientPool()
        pool._clients["deepseek"] = MagicMock()
        pool._clients["zhipu"] = MagicMock()
        pool.invalidate_all()
        assert pool._clients == {}
