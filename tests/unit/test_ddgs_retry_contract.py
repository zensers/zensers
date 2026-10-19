"""Regression tests for transient DuckDuckGo failures."""

import asyncio
from unittest.mock import AsyncMock, patch

from src.skills.search_skill import MultiSearchSkill


def test_ddgs_direct_timeout_retries_once():
    skill = MultiSearchSkill()
    fake_result = [{"title": "ok", "href": "https://example.com", "body": "body"}]

    async def run():
        with patch(
            "src.skills.search_skill.asyncio.to_thread",
            new=AsyncMock(side_effect=[TimeoutError("temporary"), fake_result]),
        ) as to_thread:
            result = await skill._search_with_ddgs("egg price trend", 5)
        assert result == fake_result
        assert to_thread.await_count == 2

    asyncio.run(run())
