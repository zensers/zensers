# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from tools.batch_case_pipeline import stages
from tools.batch_case_pipeline.config import CaseConfig
from tools.batch_case_pipeline.state import CaseState

CASE = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                  domain_keywords=["量子", "比特", "退相干", "超导"])


class FakeCtx:
    def __init__(self):
        self.research_calls = 0
        self.chart_calls = 0
        self.render_calls = 0

    async def run_research(self, case, case_dir):
        self.research_calls += 1
        return {"title": case.topic, "sections": [{"title": "a", "content": "b" * 60}]}

    async def run_charts(self, case, case_dir, research_result):
        self.chart_calls += 1
        research_result["sections"][0]["charts"] = [{"title": "t", "path": "p.png"}]
        return research_result, {"charts": 1}

    async def run_render(self, case, case_dir, research_result):
        self.render_calls += 1
        (case_dir / "report.html").write_text("<html></html>", encoding="utf-8")
        (case_dir / "report_draft.docx").write_bytes(b"PK" + b"0" * 1024)
        return {"html": str(case_dir / "report.html"),
                "docx": str(case_dir / "report_draft.docx")}


@pytest.mark.asyncio
async def test_research_skips_existing(tmp_path):
    (tmp_path / "research_result.json").write_text(
        json.dumps({"sections": [{"title": "a", "content": "b" * 60}]}), encoding="utf-8")
    ctx = FakeCtx()
    state = CaseState(tmp_path / "state.json", "c1")
    meta = await stages.run_research(ctx, CASE, tmp_path, state)
    assert ctx.research_calls == 0
    assert state.is_done("research") and meta["skipped"] is True


@pytest.mark.asyncio
async def test_research_runs_when_missing(tmp_path):
    ctx = FakeCtx()
    state = CaseState(tmp_path / "state.json", "c1")
    meta = await stages.run_research(ctx, CASE, tmp_path, state)
    assert ctx.research_calls == 1
    assert state.is_done("research")
    saved = json.loads((tmp_path / "research_result.json").read_text(encoding="utf-8"))
    assert saved["sections"]


@pytest.mark.asyncio
async def test_charts_persists_sidecar(tmp_path):
    ctx = FakeCtx()
    state = CaseState(tmp_path / "state.json", "c1")
    rr = {"title": "T", "sections": [{"title": "a", "content": "b" * 60, "charts": []}]}
    meta = await stages.run_charts(ctx, CASE, tmp_path, state, rr)
    assert ctx.chart_calls == 1 and meta == {"charts": 1}
    sidecar = json.loads((tmp_path / "charts.json").read_text(encoding="utf-8"))
    assert sidecar["charts"][0]["title"] == "t"


@pytest.mark.asyncio
async def test_render_writes_artifacts(tmp_path):
    ctx = FakeCtx()
    state = CaseState(tmp_path / "state.json", "c1")
    rr = {"title": "T", "sections": []}
    meta = await stages.run_render(ctx, CASE, tmp_path, state, rr)
    assert ctx.render_calls == 1 and state.is_done("render")
    assert Path(meta["docx"]).exists() and Path(meta["html"]).exists()


def test_finalize_copies_and_manifest(tmp_path):
    state = CaseState(tmp_path / "state.json", "c1")
    (tmp_path / "research_result.json").write_text(
        json.dumps({"title": "量子报告", "sections": [{"title": "a"}]}, ensure_ascii=False),
        encoding="utf-8")
    (tmp_path / "report_draft.docx").write_bytes(b"PK")
    manifest = stages.run_finalize(CASE, tmp_path, state, final_score=88.0, rounds=2)
    final = tmp_path / "量子报告.docx"
    assert final.is_file() and manifest["docx"] == str(final)
    assert manifest["status"] == "pending" and manifest["review_rounds"] == 2
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["final_score"] == 88.0


def test_finalize_missing_draft_raises(tmp_path):
    state = CaseState(tmp_path / "state.json", "c1")
    with pytest.raises(RuntimeError, match="report_draft"):
        stages.run_finalize(CASE, tmp_path, state, 0, 0)


def test_finalize_sanitizes_bad_title(tmp_path):
    state = CaseState(tmp_path / "state.json", "c1")
    (tmp_path / "research_result.json").write_text(
        json.dumps({"title": '坏标题: *?"<>|/\\..', "sections": [{"title": "a"}]},
                   ensure_ascii=False), encoding="utf-8")
    (tmp_path / "report_draft.docx").write_bytes(b"PK")
    manifest = stages.run_finalize(CASE, tmp_path, state, 1.0, 1)
    assert Path(manifest["docx"]).parent == tmp_path
    assert Path(manifest["docx"]).is_file()


def test_load_research_rejects_non_list_sections(tmp_path):
    (tmp_path / "research_result.json").write_text(
        '{"sections": "x"}', encoding="utf-8")
    assert stages.load_research_result(tmp_path) == {}


def test_absolutize_chart_srcs(tmp_path):
    charts = tmp_path / "charts"
    charts.mkdir()
    html = '<html><body><img src="charts/a.png"/><img src="https://x/b.png"/><img src="charts/sub/c.png"/></body></html>'
    out = stages._absolutize_chart_srcs(html, tmp_path)
    assert f'src="{(tmp_path / "charts" / "a.png").as_posix()}"' in out
    assert 'src="https://x/b.png"' in out            # 外链不动
    assert f'src="{(tmp_path / "charts" / "sub" / "c.png").as_posix()}"' in out


def test_finalize_fallback_on_locked_target(tmp_path, monkeypatch):
    state = CaseState(tmp_path / "state.json", "c1")
    (tmp_path / "research_result.json").write_text(
        json.dumps({"title": "量子报告", "sections": [{"title": "a"}]}, ensure_ascii=False),
        encoding="utf-8")
    (tmp_path / "report_draft.docx").write_bytes(b"PK")

    import shutil as _shutil
    calls = {"n": 0}
    real_copy2 = _shutil.copy2

    def flaky_copy2(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:   # 前两次目标被占用
            raise PermissionError(32, "另一个程序正在使用此文件。")
        return real_copy2(src, "E:\\market_report_systerm\\temp\\copy_ok.docx")

    monkeypatch.setattr(stages.shutil, "copy2", flaky_copy2)
    monkeypatch.setattr(stages.time, "sleep", lambda s: None)
    manifest = stages.run_finalize(CASE, tmp_path, state, 1.0, 1)
    # 降级为带时间戳的回退文件名，且不再指向被锁的目标
    assert Path(manifest["docx"]).name.startswith("量子报告_")
    assert calls["n"] == 3
