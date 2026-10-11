# -*- coding: utf-8 -*-
import pytest

from tools.batch_case_pipeline.revise import apply_fixes

LEAK_CHART = {"title": "t", "path": "x.png", "source": "content"}
OK_CHART = {"title": "t2", "path": "y.png", "source": "GGII"}


@pytest.mark.asyncio
async def test_chart_leak_fixes_metadata():
    rr = {"sections": [{"title": "s", "content": "c" * 100,
                        "charts": [dict(LEAK_CHART), OK_CHART]}]}
    async def no_llm(prompt, **kw):
        raise AssertionError("chart_leak 不应触发 LLM")
    rerun = await apply_fixes(
        [{"code": "chart_leak", "section": "s", "severity": "high", "detail": ""}],
        rr, llm_fn=no_llm)
    assert rr["sections"][0]["charts"][0]["source"] == "公开资料整理"
    assert rr["sections"][0]["charts"][1] == OK_CHART   # 合法图不动
    assert rerun == {"render"}


@pytest.mark.asyncio
async def test_content_issue_calls_llm():
    rr = {"sections": [{"title": "s", "content": "薄" * 60, "charts": []}]}
    calls = []

    async def fake_llm(prompt, **kw):
        calls.append(prompt)
        return {"success": True, "content": "修订后的充实内容" * 50}

    rerun = await apply_fixes(
        [{"code": "topic_drift", "section": "s", "severity": "medium", "detail": ""}],
        rr, domain_keywords=["量子"], llm_fn=fake_llm)
    assert calls and "薄" not in rr["sections"][0]["content"]
    assert "量子" in calls[0]        # 领域关键词进入提示词
    assert rerun == {"charts", "render"}


@pytest.mark.asyncio
async def test_llm_failure_keeps_content():
    rr = {"sections": [{"title": "s", "content": "原内容", "charts": []}]}

    async def bad_llm(prompt, **kw):
        return {"success": False, "message": "boom"}

    rerun = await apply_fixes(
        [{"code": "topic_drift", "section": "s", "severity": "medium", "detail": ""}],
        rr, llm_fn=bad_llm)
    assert rr["sections"][0]["content"] == "原内容"
    assert rerun == set()


@pytest.mark.asyncio
async def test_llm_exception_keeps_content():
    rr = {"sections": [{"title": "s", "content": "原内容", "charts": []}]}

    async def raise_llm(prompt, **kw):
        raise RuntimeError("network down")

    rerun = await apply_fixes(
        [{"code": "topic_drift", "section": "s", "severity": "medium", "detail": ""}],
        rr, llm_fn=raise_llm)
    assert rr["sections"][0]["content"] == "原内容"
    assert rerun == set()


@pytest.mark.asyncio
async def test_docx_issue_rerenders_only():
    rr = {"sections": []}
    rerun = await apply_fixes(
        [{"code": "docx_format", "section": "-", "severity": "low", "detail": ""}],
        rr, llm_fn=None)
    assert rerun == {"render"}


@pytest.mark.asyncio
async def test_missing_chart_dropped(tmp_path):
    keep = tmp_path / "y.png"
    keep.write_bytes(b"png")
    rr = {"sections": [{"title": "s", "content": "c" * 50, "charts": [
        {"title": "gone", "path": str(tmp_path / "nope.png"), "source": "ok"},
        {"title": "keep", "path": str(keep), "source": "ok"},
    ]}]}
    rerun = await apply_fixes(
        [{"code": "chart_missing", "section": "s", "severity": "high", "detail": ""}],
        rr, llm_fn=None)
    assert rr["sections"][0]["charts"] == [
        {"title": "keep", "path": str(keep), "source": "ok"}]
    assert rerun == {"charts", "render"}
