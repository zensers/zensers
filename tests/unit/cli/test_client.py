"""Tests for ZensersClient and error hierarchy."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import httpx


class TestZensersErrorHierarchy:
    def test_base_error(self):
        from cli.client import ZensersError
        err = ZensersError("test error", status_code=400)
        assert err.message == "test error"
        assert err.status_code == 400
        assert str(err) == "test error"

    def test_base_error_no_status(self):
        from cli.client import ZensersError
        err = ZensersError("no status")
        assert err.status_code is None

    def test_connection_error_inherits(self):
        from cli.client import ZensersConnectionError, ZensersError
        err = ZensersConnectionError("refused")
        assert isinstance(err, ZensersError)
        assert err.message == "refused"

    def test_not_found_error_inherits(self):
        from cli.client import ZensersNotFoundError, ZensersError
        err = ZensersNotFoundError("missing", status_code=404)
        assert isinstance(err, ZensersError)
        assert err.status_code == 404

    def test_server_error_inherits(self):
        from cli.client import ZensersServerError, ZensersError
        err = ZensersServerError("internal", status_code=500)
        assert isinstance(err, ZensersError)
        assert err.status_code == 500


class TestZensersClientInit:
    def test_default_base_url(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            client = ZensersClient()
            assert client._base_url == "http://localhost:8000"

    def test_custom_base_url(self):
        from cli.client import ZensersClient
        client = ZensersClient(base_url="http://custom:9000")
        assert client._base_url == "http://custom:9000"

    def test_trailing_slash_stripped(self):
        from cli.client import ZensersClient
        client = ZensersClient(base_url="http://host:8000/")
        assert client._base_url == "http://host:8000"


class TestZensersClientContextManager:
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                assert isinstance(client, ZensersClient)

    @pytest.mark.asyncio
    async def test_aexit_closes(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            client = ZensersClient()
            mock_close = AsyncMock()
            client.close = mock_close
            async with client:
                pass
            mock_close.assert_called_once()


class TestZensersClientRequest:
    @pytest.mark.asyncio
    async def test_request_connection_error(self):
        from cli.client import ZensersClient, ZensersConnectionError
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                client._http.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
                with pytest.raises(ZensersConnectionError, match="Connection refused"):
                    await client._request("GET", "http://localhost:8000/test")

    @pytest.mark.asyncio
    async def test_request_timeout(self):
        from cli.client import ZensersClient, ZensersConnectionError
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                client._http.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
                with pytest.raises(ZensersConnectionError, match="timed out"):
                    await client._request("GET", "http://localhost:8000/test")

    @pytest.mark.asyncio
    async def test_request_404_raises_not_found(self):
        from cli.client import ZensersClient, ZensersNotFoundError
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 404
                client._http.request = AsyncMock(return_value=mock_resp)
                with pytest.raises(ZensersNotFoundError):
                    await client._request("GET", "http://localhost:8000/test")

    @pytest.mark.asyncio
    async def test_request_404_suppressed(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 404
                mock_resp.raise_for_status = Mock()
                client._http.request = AsyncMock(return_value=mock_resp)
                r = await client._request("GET", "http://localhost:8000/test", raise_on_404=False)
                assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_request_500_raises_server_error(self):
        from cli.client import ZensersClient, ZensersServerError
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 500
                client._http.request = AsyncMock(return_value=mock_resp)
                with pytest.raises(ZensersServerError, match="Server error"):
                    await client._request("GET", "http://localhost:8000/test")

    @pytest.mark.asyncio
    async def test_request_success(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                client._http.request = AsyncMock(return_value=mock_resp)
                r = await client._request("GET", "http://localhost:8000/test")
                assert r.status_code == 200


class TestZensersClientAPIMethods:
    @pytest.mark.asyncio
    async def test_research_start(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                mock_resp.json = Mock(return_value={"session_id": "abc123"})
                client._http.request = AsyncMock(return_value=mock_resp)
                result = await client.research_start("test requirement", user_id="u1")
                assert result["session_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_research_status(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                mock_resp.json = Mock(return_value={"status": "running"})
                client._http.request = AsyncMock(return_value=mock_resp)
                result = await client.research_status("task1")
                assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_research_sessions(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                mock_resp.json = Mock(return_value={"sessions": []})
                client._http.request = AsyncMock(return_value=mock_resp)
                result = await client.research_sessions()
                assert result["sessions"] == []

    @pytest.mark.asyncio
    async def test_llm_models(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                mock_resp.json = Mock(return_value={"models": ["gpt-4"]})
                client._http.request = AsyncMock(return_value=mock_resp)
                result = await client.llm_models()
                assert "gpt-4" in result["models"]

    @pytest.mark.asyncio
    async def test_changelog(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = Mock()
                mock_resp.json = Mock(return_value={"changelog": "v0.1.0"})
                client._http.request = AsyncMock(return_value=mock_resp)
                result = await client.changelog()
                assert result["changelog"] == "v0.1.0"

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                with pytest.raises(FileNotFoundError, match="File not found"):
                    await client.upload_file("/nonexistent/path.txt")

    @pytest.mark.asyncio
    async def test_download_404(self):
        from cli.client import ZensersClient
        with patch("cli.client.get_api_base_url", return_value="http://localhost:8000"):
            async with ZensersClient() as client:
                mock_resp = Mock()
                mock_resp.status_code = 404
                mock_resp.headers = {}
                client._http.request = AsyncMock(return_value=mock_resp)
                with pytest.raises(FileNotFoundError, match="Document not found"):
                    await client.download("nonexistent-task")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
