import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def _mock_settings():
    mock = MagicMock()
    mock.llm.max_tokens = 4096
    mock.llm.temperature = 0.7
    mock.llm.model = "test-model"
    mock.llm.cheap_model = "test-fallback"
    mock.llm.cost_limit_per_report = 0
    mock.llm.api_key = "test-key"
    mock.llm.base_url = "https://test.example.com"
    mock.llm.top_p = 1.0
    mock.llm.frequency_penalty = 0.0
    mock.llm.presence_penalty = 0.0
    return mock


class TestCallLlmIsNoneGuard:
    @pytest.mark.asyncio
    async def test_max_tokens_zero_not_overridden(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test", max_tokens=0)
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["max_tokens"] == 0

    @pytest.mark.asyncio
    async def test_temperature_zero_not_overridden(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test", temperature=0.0)
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_max_tokens_none_uses_default(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                await call_llm(prompt="test")
                call_kwargs = mock_api.call_args[1]
                assert call_kwargs["max_tokens"] == 4096


class TestCallLlmReturnFormat:
    @pytest.mark.asyncio
    async def test_success_has_content_key(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "hello"}}], "usage": {"total_tokens": 10}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")
                assert result["success"] is True
                assert result["content"] == "hello"
                assert "model" in result
                assert "usage" in result

    @pytest.mark.asyncio
    async def test_failure_also_has_content_key(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            from src.core.llm_client import call_llm
            result = await call_llm(prompt="")
            assert result["success"] is False
            assert result["content"] == ""
            assert "error" in result

    @pytest.mark.asyncio
    async def test_primary_fallback_has_content_key(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = [Exception("primary failed"), {"choices": [{"message": {"content": "fallback ok"}}], "usage": {}}]
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")
                assert result["success"] is True
                assert result["content"] == "fallback ok"
                assert result.get("fallback_used") is True

    @pytest.mark.asyncio
    async def test_both_models_fail(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = Exception("both fail")
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")
                assert result["success"] is False
                assert result["content"] == ""
                assert "Primary" in result["message"]
                assert "Fallback" in result["message"]


class TestCallback:
    @pytest.mark.asyncio
    async def test_callback_invoked_on_success(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 5}}
                from src.core.llm_client import call_llm, _on_complete_var
                cb = MagicMock()
                token = _on_complete_var.set(cb)
                try:
                    await call_llm(prompt="test")
                    cb.assert_called_once()
                    assert cb.call_args[0][0]["success"] is True
                finally:
                    _on_complete_var.reset(token)

    @pytest.mark.asyncio
    async def test_callback_invoked_on_api_failure(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = Exception("api down")
                from src.core.llm_client import call_llm, _on_complete_var
                cb = MagicMock()
                token = _on_complete_var.set(cb)
                try:
                    result = await call_llm(prompt="test")
                    cb.assert_called_once()
                    assert cb.call_args[0][0]["success"] is False
                finally:
                    _on_complete_var.reset(token)

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_caller(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm, _on_complete_var
                def bad_cb(result):
                    raise RuntimeError("callback crash")
                token = _on_complete_var.set(bad_cb)
                try:
                    result = await call_llm(prompt="test")
                    assert result["success"] is True
                finally:
                    _on_complete_var.reset(token)

    @pytest.mark.asyncio
    async def test_no_callback_when_not_set(self):
        with patch("src.core.llm_client.settings", _mock_settings()):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm, _on_complete_var
                assert _on_complete_var.get() is None
                result = await call_llm(prompt="test")
                assert result["success"] is True


class TestCostLimit:
    @pytest.mark.asyncio
    async def test_cost_limit_rejects(self):
        ms = _mock_settings()
        ms.llm.cost_limit_per_report = 0.001
        with patch("src.core.llm_client.settings", ms):
            from src.core.llm_client import call_llm
            result = await call_llm(prompt="test", max_tokens=10000)
            assert result["success"] is False
            assert result["error"] == "cost_limit"

    @pytest.mark.asyncio
    async def test_cost_limit_allows_under(self):
        ms = _mock_settings()
        ms.llm.cost_limit_per_report = 10.0
        with patch("src.core.llm_client.settings", ms):
            with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
                from src.core.llm_client import call_llm
                result = await call_llm(prompt="test")
                assert result["success"] is True


class TestSingletonClient:
    def test_get_client_returns_same_instance(self):
        from src.core.llm_client import _get_client, _reset_client
        with patch("src.core.llm_client.settings", _mock_settings()):
            _reset_client()
            c1 = _get_client()
            c2 = _get_client()
            assert c1 is c2
            _reset_client()

    def test_reset_client_creates_new(self):
        from src.core.llm_client import _get_client, _reset_client
        with patch("src.core.llm_client.settings", _mock_settings()):
            _reset_client()
            c1 = _get_client()
            _reset_client()
            c2 = _get_client()
            assert c1 is not c2
            _reset_client()
