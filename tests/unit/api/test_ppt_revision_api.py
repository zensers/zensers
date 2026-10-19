from pathlib import Path
from types import SimpleNamespace
import importlib

import pytest

research_api_module = importlib.import_module("src.api.research_api")
from src.api.research_api import PptRevisionAPIRequest, ResearchAPI


@pytest.mark.asyncio
async def test_ppt_revision_requires_persisted_context(monkeypatch):
    session = {"ppt_revision_context": {}}
    monkeypatch.setattr(research_api_module.session_manager, "get", lambda _: session)
    api = ResearchAPI.__new__(ResearchAPI)

    result = await api.handle_ppt_revision(PptRevisionAPIRequest(session_id="s1"))

    assert result["status"] == "failed"
    assert result["error_code"] == "PPT_REVISION_CONTEXT_MISSING"


@pytest.mark.asyncio
async def test_ppt_revision_rejects_stale_base_version(tmp_path, monkeypatch):
    data_dir = tmp_path / "ppt_state"
    session = {
        "ppt_revision_context": {
            "data_dir": str(data_dir),
            "pptx_path": str(tmp_path / "report.pptx"),
        }
    }
    monkeypatch.setattr(research_api_module.session_manager, "get", lambda _: session)
    api = ResearchAPI.__new__(ResearchAPI)

    from src.core.adjustment.slide_data_store import SlideDataStore
    store = SlideDataStore(str(data_dir), "s1")
    store.persist("s1", [{"slide_type": "content", "title": "x"}])
    store.set_pptx_path("s1", str(tmp_path / "report.pptx"))

    result = await api.handle_ppt_revision(
        PptRevisionAPIRequest(session_id="s1", base_version=0)
    )

    assert result["status"] == "conflict"
    assert result["error_code"] == "PPT_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_ppt_revision_api_passes_state_machine_and_returns_version(tmp_path, monkeypatch):
    pptx_path = tmp_path / "report.pptx"
    pptx_path.write_bytes(b"pptx")
    data_dir = tmp_path / "ppt_state"
    state_machine = SimpleNamespace(
        update_context=lambda *args: None,
        can_transition_to=lambda state: False,
        transition=lambda state: None,
    )
    session = {
        "state_machine": state_machine,
        "ppt_revision_context": {
            "data_dir": str(data_dir),
            "pptx_path": str(pptx_path),
        },
    }
    monkeypatch.setattr(research_api_module.session_manager, "get", lambda _: session)
    monkeypatch.setattr(research_api_module.session_manager, "force_save", lambda _: None)

    from src.core.adjustment.slide_data_store import SlideDataStore
    store = SlideDataStore(str(data_dir), "s1")
    store.persist("s1", [{"slide_type": "content", "title": "x"}])
    store.set_pptx_path("s1", str(pptx_path))

    class FakeService:
        def __init__(self, received_store):
            assert received_store.load("s1")[0]["title"] == "x"

        async def revise(self, request):
            assert request.state_machine is state_machine
            assert request.description == "更新标题"
            return SimpleNamespace(success=True, level="L3", message="ok", error=None)

    monkeypatch.setattr(
        "src.core.adjustment.ppt_revision_service.PptRevisionService", FakeService
    )

    result = await ResearchAPI.__new__(ResearchAPI).handle_ppt_revision(
        PptRevisionAPIRequest(session_id="s1", description="更新标题")
    )

    assert result["status"] == "success"
    assert result["level"] == "L3"


@pytest.mark.asyncio
async def test_failed_ppt_revision_does_not_leave_state_in_revising(tmp_path, monkeypatch):
    pptx_path = tmp_path / "report.pptx"
    pptx_path.write_bytes(b"pptx")
    data_dir = tmp_path / "ppt_state"

    class StateMachine:
        def __init__(self):
            self.current = "previewing"

        def update_context(self, *args):
            pass

        def can_transition_to(self, state):
            return True

        def transition(self, state):
            self.current = state.value

    state_machine = StateMachine()
    session = {
        "state_machine": state_machine,
        "ppt_revision_context": {"data_dir": str(data_dir), "pptx_path": str(pptx_path)},
    }
    monkeypatch.setattr(research_api_module.session_manager, "get", lambda _: session)
    monkeypatch.setattr(research_api_module.session_manager, "force_save", lambda _: None)

    from src.core.adjustment.slide_data_store import SlideDataStore
    store = SlideDataStore(str(data_dir), "s1")
    store.persist("s1", [{"slide_type": "content", "title": "x"}])
    store.set_pptx_path("s1", str(pptx_path))

    class FailingService:
        def __init__(self, received_store):
            pass

        async def revise(self, request):
            return SimpleNamespace(success=False, level="L3", message="", error="failed")

    monkeypatch.setattr(
        "src.core.adjustment.ppt_revision_service.PptRevisionService", FailingService
    )
    result = await ResearchAPI.__new__(ResearchAPI).handle_ppt_revision(
        PptRevisionAPIRequest(session_id="s1", description="失败修订")
    )

    assert result["status"] == "failed"
    assert state_machine.current == "previewing"
