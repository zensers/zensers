from pathlib import Path

from src.core.adjustment.ppt_auditor import PptAuditor
from src.core.adjustment.ppt_structure_editor import PptStructureEditor


def _slides():
    return [
        {"slide_type": "cover", "title": "研究报告", "content": "", "items": [], "table_data": [], "images": []},
        {"slide_type": "content", "title": "市场规模", "content": "", "items": [], "table_data": [], "images": [{"src": "", "image_type": "image"}]},
        {"slide_type": "end", "title": "谢谢", "content": "", "items": [], "table_data": [], "images": []},
    ]


def test_structure_and_content_audit_passes_for_rendered_deck(tmp_path: Path):
    data = _slides()
    output = tmp_path / "report.pptx"
    result = PptStructureEditor().edit(data, pptx=str(output), output_path=str(output))
    assert result.success is True

    report = PptAuditor().audit(data, str(output), require_render=True)
    assert report.passed is True, report.to_dict()
    assert "structure" in report.checked
    assert "content_consistency" in report.checked
    assert "render_geometry" in report.checked


def test_structure_audit_blocks_missing_cover_and_empty_page():
    data = _slides()
    data[0]["slide_type"] = "content"
    data.insert(1, {"slide_type": "content", "title": "", "content": "", "items": [], "table_data": [], "images": []})
    report = PptAuditor().audit(data)
    assert report.passed is False
    assert any("第一页" in item.message for item in report.errors)
    assert any("必须有标题" in item.message for item in report.errors)


def test_content_audit_detects_missing_numeric_token(tmp_path: Path):
    data = _slides()
    output = tmp_path / "report.pptx"
    PptStructureEditor().edit(data, pptx=str(output), output_path=str(output))
    data[1]["items"] = ["销量 999 万辆，同比增长 99.9%"]
    report = PptAuditor().audit(data, str(output), require_render=True)
    assert report.passed is False
    assert any("数值 token" in item.message for item in report.errors)


def test_html_render_audit_checks_slide_contract_and_data_binding():
    html = """
    <section class="slide" data-type="cover"><h1>研究报告</h1></section>
    <section class="slide" data-type="content">
      <h2>市场规模</h2><div style="left:10%;top:10%;width:70%;height:60%">销量 950 万辆</div>
    </section>
    <section class="slide" data-type="end"><h1>谢谢</h1></section>
    """
    report = PptAuditor().audit(
        [
            {"slide_type": "cover", "title": "研究报告", "content": "", "items": [], "table_data": [], "images": []},
            {"slide_type": "content", "title": "市场规模", "content": "销量 950 万辆", "items": [], "table_data": [], "images": []},
            {"slide_type": "end", "title": "谢谢", "content": "", "items": [], "table_data": [], "images": []},
        ],
        html=html,
    )
    assert report.passed is True, report.to_dict()
    assert "html_render" in report.checked
