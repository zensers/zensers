"""True HTML-first PPT lifecycle E2E."""

from pathlib import Path
import shutil

from src.core.adjustment.html_ppt_artifact_store import HtmlPptArtifactStore
from src.core.adjustment.html_ppt_revision_service import (
    HtmlPptRevisionRequest,
    HtmlPptRevisionService,
)
from src.converters.html_to_ppt import HTMLToPPTConverter


def test_html_first_revision_then_confirm_then_export(tmp_path: Path):
    html = """
    <section class="slide" data-type="cover"><h1>新能源汽车市场报告</h1></section>
    <section class="slide" data-type="content"><h2>市场规模</h2><p>销量 950 万辆，同比增长 37.5%</p></section>
    <section class="slide" data-type="end"><h1>谢谢</h1></section>
    """
    store = HtmlPptArtifactStore(str(tmp_path), "html-first")
    store.initialize(html)
    service = HtmlPptRevisionService(store)

    # The preview/revision phase only changes HTML. No PPTX exists yet.
    revision = service.revise(HtmlPptRevisionRequest(
        task_id="html-first", level="L1", slide_index=1,
        target_field="title", new_value="市场规模与增长",
    ))
    assert revision.success is True
    assert not list(tmp_path.rglob("*.pptx"))

    service.confirm()
    output_dir = Path("data") / "_pytest_html_first"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "final.pptx"
    try:
        result = HTMLToPPTConverter().convert(store.load_html(), str(output))
        assert result.success is True
        assert output.exists()
        store.mark_exported(str(output))
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
    assert store.state()["status"] == "PPTX_EXPORTED"
