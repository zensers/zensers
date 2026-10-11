# -*- coding: utf-8 -*-
from tools.batch_case_pipeline.state import STAGES, CaseState


def test_stage_order():
    assert STAGES == ["research", "charts", "render", "review", "finalize"]


def test_mark_and_skip(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    assert cs.current_stage() == "research"
    cs.mark_done("research", {"sections": 12})
    cs.mark_done("charts", {"charts": 23})
    cs.save()
    cs2 = CaseState.load(tmp_path / "state.json", "c1")
    assert cs2.is_done("research") and cs2.is_done("charts")
    assert cs2.current_stage() == "render"
    assert cs2.meta("research") == {"sections": 12}


def test_reset_from_stage(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    for s in STAGES:
        cs.mark_done(s, {})
    cs.reset_from("render")
    assert cs.is_done("research") and cs.is_done("charts")
    assert not cs.is_done("render") and not cs.is_done("review")
    assert cs.current_stage() == "render"


def test_status_lifecycle(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    cs.set_case_status("running")
    cs.set_case_status("needs_human")
    cs.save()
    cs2 = CaseState.load(tmp_path / "state.json", "c1")
    assert cs2.case_status == "needs_human"


def test_next_stage_after_done_all(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    for s in STAGES:
        cs.mark_done(s, {})
    assert cs.current_stage() is None
