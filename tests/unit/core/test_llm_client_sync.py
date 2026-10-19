import pytest
from unittest.mock import patch, AsyncMock
from src.config.llm_profiles import RoutingHint


class TestCallLlmSync:
    @patch("src.core.llm_client._router", None)
    @patch("src.core.llm_client.settings")
    def test_sync_call_returns_result(self, mock_settings):
        mock_settings.llm.model = "gpt-4o"
        mock_settings.llm.api_key = "sk-test"
        mock_settings.llm.base_url = "https://api.openai.com/v1"
        mock_settings.llm.max_tokens = 2048
        mock_settings.llm.temperature = 0.7
        mock_settings.llm.cheap_model = "gpt-4o-mini"
        mock_settings.llm.top_p = 1.0
        mock_settings.llm.frequency_penalty = 0.0
        mock_settings.llm.presence_penalty = 0.0
        mock_settings.llm.cost_limit_per_report = 0.0

        from src.core.llm_client import call_llm_sync

        with patch("src.core.llm_client.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "content": "hello", "model": "gpt-4o"}
            result = call_llm_sync(prompt="test", routing_hint=RoutingHint(action="quality_judge"))
            assert result["success"] is True
            assert result["content"] == "hello"
            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args
            assert call_kwargs.kwargs.get("routing_hint") == RoutingHint(action="quality_judge")

    @patch("src.core.llm_client._router", None)
    @patch("src.core.llm_client.settings")
    def test_sync_call_without_routing_hint(self, mock_settings):
        mock_settings.llm.model = "gpt-4o"
        mock_settings.llm.api_key = "sk-test"
        mock_settings.llm.base_url = "https://api.openai.com/v1"
        mock_settings.llm.max_tokens = 2048
        mock_settings.llm.temperature = 0.7
        mock_settings.llm.cheap_model = "gpt-4o-mini"
        mock_settings.llm.top_p = 1.0
        mock_settings.llm.frequency_penalty = 0.0
        mock_settings.llm.presence_penalty = 0.0
        mock_settings.llm.cost_limit_per_report = 0.0

        from src.core.llm_client import call_llm_sync

        with patch("src.core.llm_client.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "content": "result"}
            result = call_llm_sync(prompt="test")
            assert result["success"] is True

    @patch("src.core.llm_client._router", None)
    @patch("src.core.llm_client.settings")
    def test_sync_call_handles_exception(self, mock_settings):
        mock_settings.llm.model = "gpt-4o"
        mock_settings.llm.api_key = "sk-test"
        mock_settings.llm.base_url = "https://api.openai.com/v1"
        mock_settings.llm.max_tokens = 2048
        mock_settings.llm.temperature = 0.7
        mock_settings.llm.cheap_model = "gpt-4o-mini"
        mock_settings.llm.top_p = 1.0
        mock_settings.llm.frequency_penalty = 0.0
        mock_settings.llm.presence_penalty = 0.0
        mock_settings.llm.cost_limit_per_report = 0.0

        from src.core.llm_client import call_llm_sync

        with patch("src.core.llm_client.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API error")
            result = call_llm_sync(prompt="test")
            assert result["success"] is False
            assert "API error" in result.get("message", "")
