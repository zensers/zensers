# tests/unit/report_upgrade/test_content_contract_incidents.py
# -*- coding: utf-8 -*-
"""附录 A 事故夹具 × 健康语料：每起事故必须被判失败，健康语料零误伤。"""
import glob, os, pytest
from src.core.content_contract import check_content

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "content_contract")

INCIDENTS = sorted(glob.glob(os.path.join(FIXTURES, "incidents", "*.txt")))
HEALTHY = sorted(glob.glob(os.path.join(FIXTURES, "healthy", "*.txt")))


def _load(path):
    text = open(path, encoding="utf-8").read()
    kind = "chapter"
    lang = "zh"
    if text.startswith("KIND:"):
        first_nl = text.find("\n")
        kind = text[5:first_nl].strip()
        text = text[first_nl + 1:]
    if text.startswith("LANG:"):
        first_nl = text.find("\n")
        lang = text[5:first_nl].strip()
        text = text[first_nl + 1:]
    return text, kind, lang


@pytest.mark.parametrize("path", INCIDENTS, ids=[os.path.basename(p) for p in INCIDENTS])
def test_incident_fixture_fails(path):
    text, kind, lang = _load(path)
    v = check_content(text, kind=kind, data_points_count=0, language=lang)
    assert not v.passed, f"incident fixture passed: {path}"


@pytest.mark.parametrize("path", HEALTHY, ids=[os.path.basename(p) for p in HEALTHY])
def test_healthy_fixture_passes(path):
    text, kind, lang = _load(path)
    v = check_content(text, kind=kind, language=lang,
                      data_points_count=max(1, len(text) // 1000))
    assert v.passed, f"healthy fixture flagged: {path} -> {v.fail_codes}"


def test_corpus_sizes():
    assert len(INCIDENTS) >= 7
    assert len(HEALTHY) >= 10
