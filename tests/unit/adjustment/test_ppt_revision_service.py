import pytest
from unittest.mock import MagicMock, AsyncMock
from src.core.adjustment.ppt_revision_service import (
    PptRevisionService, PptRevisionRequest, PptRevisionResult,
)
from src.core.adjustment.revision_types import RevisionOpType


def _make_request(**overrides):
    defaults = {
        "task_id": "t1",
        "source": "click",
        "slide_index": 1,
        "revision_type": "replace_text",
        "revision_level": "L1",
        "target_field": "title",
        "new_value": "New Title",
        "description": "",
    }
    defaults.update(overrides)
    return PptRevisionRequest(**defaults)


class TestPptRevisionRequest:
    def test_defaults(self):
        req = PptRevisionRequest(task_id="t1")
        assert req.source == "natural_language"
        assert req.slide_index is None
        assert req.revision_type == "modify"
        assert req.revision_level is None
        assert req.rollback_version is None

    def test_click_request(self):
        req = _make_request()
        assert req.source == "click"
        assert req.target_field == "title"
        assert req.new_value == "New Title"


class TestPptRevisionResult:
    def test_success_result(self):
        result = PptRevisionResult(success=True, level="L1", message="done")
        assert result.success is True
        assert result.level == "L1"

    def test_failure_result(self):
        result = PptRevisionResult(success=False, level="L2", message="chart failed")
        assert result.success is False

    def test_l0_review_result(self):
        result = PptRevisionResult(
            success=True, level="L0", message="Review only"
        )
        assert result.level == "L0"


class TestValidateClickLevel:
    def test_modify_table_at_l1_corrected_to_l3(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="modify_table", revision_level="L1")
        result = svc._validate_click_level("L1", req)
        assert result == "L3"

    def test_modify_chart_at_l1_corrected_to_l2(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="modify_chart", revision_level="L1")
        result = svc._validate_click_level("L1", req)
        assert result == "L2"

    def test_add_at_l1_corrected_to_l4(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="add", revision_level="L1")
        result = svc._validate_click_level("L1", req)
        assert result == "L4"

    def test_delete_at_l3_corrected_to_l4(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="delete", revision_level="L3")
        result = svc._validate_click_level("L3", req)
        assert result == "L4"

    def test_valid_l1_replace_text_passes(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="replace_text", revision_level="L1")
        result = svc._validate_click_level("L1", req)
        assert result == "L1"

    def test_unknown_type_passes(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_type="custom_op", revision_level="L1")
        result = svc._validate_click_level("L1", req)
        assert result == "L1"


class TestDispatchL0:
    @pytest.mark.asyncio
    async def test_l0_returns_review_result(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        req = _make_request(revision_level="L0")
        result = await svc._dispatch("L0", req)
        assert result.success is True
        assert result.level == "L0"
        assert "no modification" in result.message.lower() or "review" in result.message.lower()


class TestDispatchProductionGuards:
    def _service(self, slide_data=None, editor_result=None):
        svc = PptRevisionService.__new__(PptRevisionService)
        svc.pptx_path = "missing.pptx"
        svc.store = MagicMock()
        svc.store.load.return_value = slide_data or [{"slide_type": "content"}]
        svc.store.persist = MagicMock()
        svc.page = MagicMock()
        svc.page.edit.return_value = editor_result
        svc.structure = MagicMock()
        svc.structure.edit.return_value = editor_result
        return svc

    def _data_revision_service(self, editor_result, render_result, tmp_path):
        svc = self._service(slide_data=[{"slide_type": "content", "title": "old"}])
        pptx = tmp_path / "report.pptx"
        pptx.write_bytes(b"pptx")
        svc.pptx_path = str(pptx)
        svc.atomic = MagicMock()
        svc.element = MagicMock()
        svc.atomic.edit.return_value = editor_result
        svc.element.edit.return_value = editor_result
        svc.structure.edit.return_value = render_result
        return svc

    @pytest.mark.asyncio
    async def test_l1_success_also_rerenders_pptx(self, tmp_path):
        editor_result = PptRevisionResult(success=True, level="L1", message="data changed")
        render_result = MagicMock(success=True)
        svc = self._data_revision_service(editor_result, render_result, tmp_path)

        result = await svc._dispatch("L1", _make_request(revision_level="L1"))

        assert result.success is True
        svc.atomic.edit.assert_called_once()
        svc.structure.edit.assert_called_once_with(
            [{"slide_type": "content", "title": "old"}],
            pptx=str(tmp_path / "report.pptx"),
            output_path=str(tmp_path / "report.pptx"),
        )

    @pytest.mark.asyncio
    async def test_l2_render_failure_restores_original_slide_data(self, tmp_path):
        editor_result = PptRevisionResult(success=True, level="L2", message="element changed")
        svc = self._data_revision_service(editor_result, None, tmp_path)
        svc.store.persist.reset_mock()

        result = await svc._dispatch("L2", _make_request(revision_level="L2"))

        assert result.success is False
        svc.store.persist.assert_called_with(
            "t1", [{"slide_type": "content", "title": "old"}]
        )

    @pytest.mark.asyncio
    async def test_l1_without_pptx_cannot_report_success(self):
        editor_result = PptRevisionResult(success=True, level="L1", message="data changed")
        svc = self._service(slide_data=[{"slide_type": "content", "title": "old"}])
        svc.atomic = MagicMock()
        svc.atomic.edit.return_value = editor_result
        svc.pptx_path = None

        result = await svc._dispatch("L1", _make_request(revision_level="L1"))

        assert result.success is False
        assert "pptx" in (result.error or "").lower()

    def test_l3_does_not_report_success_when_editor_returns_none(self):
        svc = self._service(editor_result=None)
        result = svc._dispatch_l3(_make_request(revision_level="L3", slide_index=0))
        assert result.success is False
        assert "editor" in (result.error or "").lower()
        assert svc.page.edit.call_args.kwargs["pptx"] == svc.pptx_path
        svc.store.persist.assert_not_called()

    def test_l4_does_not_report_success_when_editor_returns_none(self):
        svc = self._service(editor_result=None)
        result = svc._dispatch_l4(_make_request(revision_level="L4"))
        assert result.success is False
        assert "editor" in (result.error or "").lower()
        assert svc.structure.edit.call_args.kwargs["pptx"] == svc.pptx_path
        svc.store.persist.assert_not_called()

    def test_l3_editor_exception_is_reported_as_failure(self):
        svc = self._service(editor_result=None)
        svc.page.edit.side_effect = NotImplementedError("XML swap not implemented")
        result = svc._dispatch_l3(_make_request(revision_level="L3", slide_index=0))
        assert result.success is False
        assert "editor failed" in (result.error or "").lower()
        svc.store.persist.assert_not_called()

    def test_l4_editor_exception_is_reported_as_failure(self):
        svc = self._service(editor_result=None)
        svc.structure.edit.side_effect = RuntimeError("converter failed")
        result = svc._dispatch_l4(_make_request(revision_level="L4"))
        assert result.success is False
        assert "editor failed" in (result.error or "").lower()
        svc.store.persist.assert_not_called()

    def test_l4_partial_file_write_is_restored_on_failure(self, tmp_path):
        pptx = tmp_path / "report.pptx"
        pptx.write_bytes(b"original")
        svc = self._service(slide_data=[{"slide_type": "content", "title": "old"}], editor_result=None)
        svc.pptx_path = str(pptx)

        def partial_write(*args, **kwargs):
            pptx.write_bytes(b"partial")
            return None

        svc.structure.edit.side_effect = partial_write
        result = svc._dispatch_l4(_make_request(revision_level="L4"))

        assert result.success is False
        assert pptx.read_bytes() == b"original"
        svc.store.persist.assert_not_called()

    def test_negative_l3_slide_index_is_rejected(self):
        svc = self._service(editor_result=MagicMock(success=True))
        result = svc._dispatch_l3(_make_request(revision_level="L3", slide_index=-1))
        assert result.success is False
        assert "out of range" in (result.error or "").lower()
        svc.page.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_l5_without_state_machine_fails_safely(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        result = await svc._rollback_framework(_make_request(revision_level="L5"))
        assert result.success is False
        assert "ConversationStateMachine" in (result.error or "")

    @pytest.mark.asyncio
    async def test_l5_rollback_restores_ppt_and_slide_data_and_records_state(self, tmp_path):
        svc = PptRevisionService.__new__(PptRevisionService)
        active = tmp_path / "active.pptx"
        active.write_bytes(b"active")
        svc.pptx_path = str(active)
        svc.store = MagicMock()
        svc.store.persist = MagicMock()
        svc.version_mgr = MagicMock()
        svc.version_mgr.rollback.return_value = [{"slide_type": "content", "title": "v1"}]
        state_machine = MagicMock()
        request = _make_request(
            revision_level="L5",
            rollback_version=1,
            state_machine=state_machine,
        )

        result = await svc._rollback_framework(request)

        assert result.success is True
        svc.version_mgr.rollback.assert_called_once_with("t1", 1, str(active))
        svc.store.persist.assert_called_once_with(
            "t1", [{"slide_type": "content", "title": "v1"}]
        )
        state_machine.update_context.assert_any_call("ppt_last_rollback_version", 1)

    @pytest.mark.asyncio
    async def test_l5_without_explicit_state_or_version_is_safe_failure(self):
        svc = PptRevisionService.__new__(PptRevisionService)
        request = _make_request(revision_level="L5")
        result = await svc._rollback_framework(request)
        assert result.success is False
        assert "ConversationStateMachine" in (result.error or "")

    @pytest.mark.asyncio
    async def test_l5_missing_slide_snapshot_does_not_change_ppt(self, tmp_path):
        active = tmp_path / "active.pptx"
        active.write_bytes(b"current")
        svc = PptRevisionService.__new__(PptRevisionService)
        svc.pptx_path = str(active)
        svc.store = MagicMock()
        svc.version_mgr = MagicMock()
        svc.version_mgr.get_snapshot_slide_data.return_value = None
        state_machine = MagicMock()
        request = _make_request(
            revision_level="L5", rollback_version=1, state_machine=state_machine
        )

        result = await svc._rollback_framework(request)

        assert result.success is False
        assert active.read_bytes() == b"current"
        svc.version_mgr.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_l5_state_machine_failure_restores_file_and_slide_data(self, tmp_path):
        active = tmp_path / "active.pptx"
        active.write_bytes(b"current")
        svc = PptRevisionService.__new__(PptRevisionService)
        svc.pptx_path = str(active)
        svc.store = MagicMock()
        original = [{"slide_type": "content", "title": "current"}]
        svc.store.load.return_value = original
        svc.version_mgr = MagicMock()
        svc.version_mgr.get_snapshot_slide_data.return_value = [{"title": "old"}]

        def rollback(*args):
            active.write_bytes(b"rolled-back")
            return [{"slide_type": "content", "title": "old"}]

        svc.version_mgr.rollback.side_effect = rollback
        state_machine = MagicMock()
        state_machine.update_context.side_effect = RuntimeError("state commit failed")
        request = _make_request(
            revision_level="L5", rollback_version=1, state_machine=state_machine
        )

        result = await svc._rollback_framework(request)

        assert result.success is False
        assert active.read_bytes() == b"current"
        svc.store.persist.assert_called_with("t1", original)
