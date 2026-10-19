from pathlib import Path

import pytest

from src.core.adjustment.html_ppt_artifact_store import HtmlPptArtifactStore
from src.core.adjustment.html_ppt_revision_service import (
    HtmlPptRevisionRequest,
    HtmlPptRevisionService,
)


HTML = """
<section class="slide" data-type="cover"><h1>报告</h1></section>
<section class="slide" data-type="content"><h2>原始标题</h2><p>销量 950 万辆</p></section>
<section class="slide" data-type="end"><h1>谢谢</h1></section>
"""


def test_html_l1_revision_commits_after_audit(tmp_path: Path):
    store = HtmlPptArtifactStore(str(tmp_path), "t1")
    store.initialize(HTML)
    result = HtmlPptRevisionService(store).revise(HtmlPptRevisionRequest(
        task_id="t1", level="L1", slide_index=1,
        target_field="title", new_value="修订标题",
    ))
    assert result.success is True
    assert result.version == 2
    assert "修订标题" in store.load_html()
    assert store.state()["status"] == "HTML_AUDITED"


def test_html_l3_replaces_only_target_section(tmp_path: Path):
    store = HtmlPptArtifactStore(str(tmp_path), "t2")
    store.initialize(HTML)
    replacement = '<section class="slide" data-type="content"><h2>新页面</h2><p>新内容</p></section>'
    result = HtmlPptRevisionService(store).revise(HtmlPptRevisionRequest(
        task_id="t2", level="L3", slide_index=1, new_html=replacement,
    ))
    output = store.load_html()
    assert result.success is True
    assert "新页面" in output
    assert "原始标题" not in output
    assert "报告" in output and "谢谢" in output


def test_html_confirmation_requires_audit_and_exports_only_after_confirm(tmp_path: Path):
    store = HtmlPptArtifactStore(str(tmp_path), "t3")
    store.initialize(HTML)
    service = HtmlPptRevisionService(store)
    result = service.revise(HtmlPptRevisionRequest(
        task_id="t3", level="L1", slide_index=1,
        target_field="title", new_value="最终标题",
    ))
    assert result.success is True
    state = service.confirm()
    assert state["status"] == "HTML_CONFIRMED"
    assert store.state()["status"] == "HTML_CONFIRMED"


def test_l5_does_not_fake_a_pptx_rollback(tmp_path: Path):
    store = HtmlPptArtifactStore(str(tmp_path), "t4")
    store.initialize(HTML)
    result = HtmlPptRevisionService(store).revise(HtmlPptRevisionRequest(
        task_id="t4", level="L5", description="重新收集数据",
    ))
    assert result.success is False
    assert result.recovery_action == "framework_regeneration"
    assert result.error == "requires_framework_regeneration"


def test_regenerated_html_replaces_existing_draft_and_keeps_revision_history(tmp_path: Path):
    store = HtmlPptArtifactStore(str(tmp_path), "t5")
    store.initialize(HTML)
    replacement = HTML.replace("原始标题", "重新生成标题")
    state = store.initialize(replacement, replace=True)
    assert state["version"] == 2
    assert "重新生成标题" in store.load_html()
    assert (store.revisions_dir / "v1.html").exists()
    assert (store.revisions_dir / "v2.html").exists()
