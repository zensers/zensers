# -*- coding: utf-8 -*-
import json

import pytest

from tools.batch_case_pipeline import __main__ as bp
from tools.batch_case_pipeline.config import BatchConfig, CaseConfig

CASE = CaseConfig(case_id="bad", topic="中国量子计算产业深度研究报告",
                  domain_keywords=["量子", "比特", "退相干", "超导"])
CFG = BatchConfig(max_review_rounds=3, cases=[CASE])


class FailCtx:
    async def run_research(self, case, case_dir):
        raise RuntimeError("boom")

    async def run_charts(self, case, case_dir, research_result):
        raise AssertionError("不应到达")

    async def run_render(self, case, case_dir, research_result):
        raise AssertionError("不应到达")


class OkCtx:
    """全链路成功替身：产出可通过 review 的最小产物。"""
    async def run_research(self, case, case_dir):
        return {"title": case.topic, "sections": [
            {"title": "市场规模", "content": "量子比特退相干研究" * 300, "charts": []}]}

    async def run_charts(self, case, case_dir, research_result):
        return research_result, {"charts": 0}

    async def run_render(self, case, case_dir, research_result):
        # 最小合法 docx（含 zip 头即可，review 的 docx 分支对损坏文件走 warning 跳过）
        (case_dir / "report.html").write_text("<html/>", encoding="utf-8")
        (case_dir / "report_draft.docx").write_bytes(b"PK" + b"0" * 1024)
        return {"html": str(case_dir / "report.html"),
                "docx": str(case_dir / "report_draft.docx")}


@pytest.mark.asyncio
async def test_failure_isolated(tmp_path):
    summary = await bp.run_case(FailCtx(), CFG, CASE, tmp_path)
    assert summary["status"] == "failed" and "boom" in summary["error"]
    st = json.loads((tmp_path / "cases" / "bad" / "state.json").read_text(encoding="utf-8"))
    assert st["case_status"] == "failed"


@pytest.mark.asyncio
async def test_happy_path_finalizes(tmp_path):
    summary = await bp.run_case(OkCtx(), CFG, CASE, tmp_path)
    assert summary["status"] == "done"
    assert summary["final_score"] >= 70
    assert (tmp_path / "cases" / "bad" / "manifest.json").is_file()
    st = json.loads((tmp_path / "cases" / "bad" / "state.json").read_text(encoding="utf-8"))
    assert st["case_status"] == "done" and st["stages"]["finalize"]["status"] == "done"


@pytest.mark.asyncio
async def test_resume_skips_research(tmp_path):
    await bp.run_case(OkCtx(), CFG, CASE, tmp_path)
    ctx = OkCtx()
    summary = await bp.run_case(ctx, CFG, CASE, tmp_path)
    # 第二次运行：全阶段已完成 → finalize 复用，无研究调用
    assert summary["status"] == "done"
    st = json.loads((tmp_path / "cases" / "bad" / "state.json").read_text(encoding="utf-8"))
    assert st["stages"]["research"]["meta"].get("skipped") is True


class LeakCtx(OkCtx):
    def __init__(self):
        self.render_calls = 0
        self.chart_calls = 0

    async def run_research(self, case, case_dir):
        return {"title": case.topic, "sections": [
            {"title": "市场规模", "content": "量子比特退相干研究" * 300,
             "charts": [{"title": "t", "path": "x.png", "source": "content",
                         "caption": "n"}]}]}

    async def run_charts(self, case, case_dir, research_result):
        self.chart_calls += 1
        return research_result, {"charts": 1}

    async def run_render(self, case, case_dir, research_result):
        self.render_calls += 1
        (case_dir / "report.html").write_text("<html/>", encoding="utf-8")
        (case_dir / "report_draft.docx").write_bytes(b"PK" + b"0" * 1024)
        return {"html": "x", "docx": "y"}


@pytest.mark.asyncio
async def test_chart_leak_triggers_charts_and_render_rerun(tmp_path):
    ctx = LeakCtx()
    summary = await bp.run_case(ctx, CFG, CASE, tmp_path)
    assert ctx.render_calls >= 2
    assert summary["status"] == "done"
    rr = json.loads((tmp_path / "cases" / "bad" / "research_result.json")
                    .read_text(encoding="utf-8"))
    charts = rr["sections"][0]["charts"]
    assert all(c.get("source") != "content" for c in charts)


class UnfixableCtx(OkCtx):
    def __init__(self):
        self.render_calls = 0

    async def run_research(self, case, case_dir):
        rr = await super().run_research(case, case_dir)
        rr["defense_audit"] = {"issues": [
            {"code": "missing_source_url", "section": "s"}]}
        return rr

    async def run_render(self, case, case_dir, research_result):
        self.render_calls += 1
        return await super().run_render(case, case_dir, research_result)


@pytest.mark.asyncio
async def test_unfixable_high_goes_needs_human_without_rerun(tmp_path):
    ctx = UnfixableCtx()
    summary = await bp.run_case(ctx, CFG, CASE, tmp_path)
    assert summary["status"] == "needs_human"
    assert ctx.render_calls == 1
