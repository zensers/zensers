"""Behavioral E2E tests for the PPT revision quality micro-loop."""

from pathlib import Path

import pytest

from src.core.adjustment.ppt_auditor import PptAuditFinding, PptAuditReport
from src.core.adjustment.ppt_revision_service import PptRevisionRequest, PptRevisionService
from src.core.adjustment.ppt_structure_editor import PptStructureEditor
from src.core.adjustment.slide_data_store import SlideDataStore


def _deck():
    return [
        {"slide_type": "cover", "title": "研究报告", "content": "", "items": [], "table_data": [], "images": []},
        {"slide_type": "content", "title": "原始标题", "content": "", "items": [], "table_data": [], "images": [{"src": "", "image_type": "image"}]},
        {"slide_type": "end", "title": "谢谢", "content": "", "items": [], "table_data": [], "images": []},
    ]


@pytest.mark.asyncio
async def test_revision_micro_loop_audits_and_commits(tmp_path: Path):
    data_dir = tmp_path / "slide_data"
    data_dir.mkdir()
    pptx = tmp_path / "report.pptx"
    slides = _deck()
    assert PptStructureEditor().edit(slides, pptx=str(pptx), output_path=str(pptx)).success
    store = SlideDataStore(str(data_dir), task_id="micro")
    store.persist("micro", slides)
    store.set_pptx_path("micro", str(pptx))

    result = await PptRevisionService(store).revise(PptRevisionRequest(
        task_id="micro", source="click", slide_index=1,
        revision_type="replace_text", revision_level="L1",
        target_field="title", new_value="修订后标题",
    ))

    assert result.success is True
    assert result.attempted_levels == ["L1"]
    assert result.audit_report is not None
    assert result.audit_report.passed is True
    assert store.load("micro")[1]["title"] == "修订后标题"


@pytest.mark.asyncio
async def test_failed_audit_rolls_back_logical_and_file_state(tmp_path: Path):
    data_dir = tmp_path / "slide_data"
    data_dir.mkdir()
    pptx = tmp_path / "report.pptx"
    slides = _deck()
    assert PptStructureEditor().edit(slides, pptx=str(pptx), output_path=str(pptx)).success
    original_bytes = pptx.read_bytes()
    store = SlideDataStore(str(data_dir), task_id="micro-fail")
    store.persist("micro-fail", slides)
    store.set_pptx_path("micro-fail", str(pptx))
    service = PptRevisionService(store)

    def always_fail(*args, **kwargs):
        return PptAuditReport(
            passed=False,
            findings=[PptAuditFinding("render", "error", "synthetic visual failure")],
            checked=["structure", "content_consistency", "render_geometry"],
        )

    service.auditor.audit = always_fail
    result = await service.revise(PptRevisionRequest(
        task_id="micro-fail", source="click", slide_index=1,
        revision_type="replace_text", revision_level="L1",
        target_field="title", new_value="不应提交",
    ))

    assert result.success is False
    assert result.recovery_action == "rollback"
    assert result.attempted_levels == ["L1", "L2"]
    assert store.load("micro-fail")[1]["title"] == "原始标题"
    assert pptx.read_bytes() == original_bytes
