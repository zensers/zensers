from unittest.mock import Mock, patch

import requests

from src.core import akshare_transport


def test_push2_prefers_requests_when_proxy_is_healthy():
    original_request = Mock(return_value=Mock(status_code=200))
    original_session = requests.Session
    original_sessions_session = requests.sessions.Session
    try:
        with patch.object(original_session, "request", original_request), \
             patch.object(akshare_transport, "_PATCHED", False), \
             patch.object(akshare_transport, "_detect_proxy", return_value="http://proxy"):
            assert akshare_transport.patch_akshare_requests()
            result = requests.Session().get("https://push2.eastmoney.com/api")
    finally:
        requests.Session = original_session
        requests.sessions.Session = original_sessions_session
        akshare_transport._PATCHED = False

    assert result.status_code == 200
    original_request.assert_called_once()
    call_kwargs = original_request.call_args.kwargs
    assert call_kwargs["verify"] is False
    assert call_kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
