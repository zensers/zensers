# -*- coding: utf-8 -*-
"""search_skill 超时护栏与共享 SSL 上下文"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.skills.search_skill import (
    MultiSearchSkill,
    _get_shared_ssl_context,
    _search_thread_timeout,
)


def test_shared_ssl_context_singleton():
    ctx1 = _get_shared_ssl_context()
    ctx2 = _get_shared_ssl_context()
    assert ctx1 is ctx2


def test_thread_timeout_env_default():
    import os
    os.environ.pop("ZENSERS_SEARCH_THREAD_TIMEOUT", None)
    assert _search_thread_timeout() >= 30.0


def test_thread_timeout_env_override():
    import os
    os.environ["ZENSERS_SEARCH_THREAD_TIMEOUT"] = "60"
    assert _search_thread_timeout() == 60.0
    os.environ.pop("ZENSERS_SEARCH_THREAD_TIMEOUT", None)


@pytest.mark.asyncio
async def test_baidu_api_thread_timeout(monkeypatch):
    skill = MultiSearchSkill()
    from baidu_serp_api import BaiduPc

    def slow_search(*a, **k):
        time.sleep(7)
        return {"code": 200, "data": {"results": []}}

    monkeypatch.setattr("baidu_serp_api.BaiduPc.search", slow_search, raising=False)
    monkeypatch.setenv("ZENSERS_SEARCH_THREAD_TIMEOUT", "1")
    t0 = time.time()
    with pytest.raises(asyncio.TimeoutError):
        await skill._search_with_baidu_api("测试查询", 3)
    assert time.time() - t0 < 7  # 未被同步睡眠拖住