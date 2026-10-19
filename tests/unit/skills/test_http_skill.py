"""
HTTPSkill 测试 - TDD模式（使用 Mock）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestHTTPSkill:
    """测试 HTTP 请求 Skill"""

    @pytest.fixture
    def skill(self):
        from src.skills.http_skill import HTTPSkill
        from src.skills.base import SkillConfig
        return HTTPSkill(SkillConfig(name="http_skill", version="1.0.0"))

    @pytest.mark.asyncio
    async def test_get_request_success(self, skill):
        """测试 GET 请求成功"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>OK</html>")
        mock_resp.json = AsyncMock(return_value={"status": "ok"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await skill.execute(
                action="get",
                url="https://example.com/api"
            )

        assert result["success"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_post_request_success(self, skill):
        """测试 POST 请求成功"""
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.text = AsyncMock(return_value='{"id": 1}')
        mock_resp.json = AsyncMock(return_value={"id": 1})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await skill.execute(
                action="post",
                url="https://example.com/api",
                payload={"data": "test"}
            )

        assert result["success"] is True
        assert result["status_code"] == 201

    @pytest.mark.asyncio
    async def test_http_error_handling(self, skill):
        """测试 HTTP 错误处理"""
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("连接失败"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await skill.execute(
                action="get",
                url="https://unreachable.example.com"
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_timeout_handling(self, skill):
        """测试超时处理"""
        import asyncio

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await skill.execute(
                action="get",
                url="https://slow.example.com",
                timeout=5
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_custom_headers(self, skill):
        """测试自定义请求头"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="OK")
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await skill.execute(
                action="get",
                url="https://example.com",
                headers={"Authorization": "Bearer token123"}
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill):
        """测试未知动作"""
        result = await skill.execute(action="delete_all", url="https://example.com")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_ssrf_private_ip_blocked(self, skill):
        """测试 SSRF 攻击：私有 IP 被阻止"""
        # 尝试访问内网地址
        result = await skill.execute(
            action="get",
            url="http://192.168.1.1/admin"
        )
        assert result["success"] is False
        assert "内网地址" in result.get("error", "") or "验证失败" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_ssrf_localhost_blocked(self, skill):
        """测试 SSRF 攻击：localhost 被阻止"""
        result = await skill.execute(
            action="get",
            url="http://localhost:8080/internal"
        )
        assert result["success"] is False
        assert "内网地址" in result.get("error", "") or "验证失败" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_invalid_protocol_blocked(self, skill):
        """测试无效协议被阻止"""
        result = await skill.execute(
            action="get",
            url="file:///etc/passwd"
        )
        assert result["success"] is False
        assert "协议" in result.get("error", "") or "验证失败" in result.get("error", "")
