# -*- coding: utf-8 -*-
import asyncio
import os
import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


_load_dotenv()


def _get_llm_config():
    return {
        "provider": os.environ.get("LLM_PROVIDER", ""),
        "model": os.environ.get("LLM_MODEL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "api_endpoint": os.environ.get("LLM_API_ENDPOINT", ""),
    }


def _has_llm_config():
    cfg = _get_llm_config()
    return bool(cfg["api_key"] or cfg["model"])


@pytest.fixture(scope="session")
def llm_config():
    return _get_llm_config()


@pytest.fixture(scope="session")
def has_llm():
    return _has_llm_config()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from src.api.main import app
    from tests.e2e.helpers.api_client import ZensersClient
    c = ZensersClient(app)
    yield c
    await c.aclose()


@pytest.fixture
def new_energy_topic():
    return "中国新能源汽车市场"


@pytest.fixture
def byd_topic():
    return "比亚迪财务分析"


@pytest.fixture(autouse=True)
def cleanup_test_sessions():
    _created = []
    yield _created
    from src.core.session_manager import SessionManager
    sm = SessionManager.get_instance()
    for sid in _created:
        try:
            sm.delete(sid)
        except Exception:
            pass
        session_dir = Path("data/sessions") / f"{sid}.json"
        if session_dir.exists():
            try:
                session_dir.unlink()
            except Exception:
                pass


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: End-to-end tests (test full workflows)")
    config.addinivalue_line("markers", "slow: Slow tests (skip in quick mode)")
    config.addinivalue_line("markers", "requires_llm: Tests that require real LLM API access")


def pytest_collection_modifyitems(config, items):
    skip_e2e = pytest.mark.skip(reason="need -m e2e option to run")
    skip_llm = pytest.mark.skip(reason="need LLM API key to run")
    for item in items:
        if "e2e" in item.keywords and not config.getoption("-m", default=""):
            pass
        if "requires_llm" in item.keywords and not _has_llm_config():
            item.add_marker(skip_llm)
