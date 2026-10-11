# -*- coding: utf-8 -*-
import json
from pathlib import Path

from tools.batch_case_pipeline.config import CaseConfig
from tools.batch_case_pipeline.review import collect_issues, save_review_report

CASE = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                  domain_keywords=["量子", "比特", "退相干", "超导"])


def _rr(charts=None, content="量子比特退相干研究" * 200):
    return {
        "title": "中国量子计算产业深度研究报告",
        "sections": [{"title": "市场规模", "content": content, "charts": charts or []}],
    }


def test_no_issues(tmp_path):
    report = collect_issues(_rr(), CASE, tmp_path)
    assert report["pass"] is True and report["score"] >= 70


def test_chart_source_leak(tmp_path):
    charts = [{"title": "t", "path": "x.png", "source": "content"}]
    report = collect_issues(_rr(charts), CASE, tmp_path)
    codes = [i["code"] for i in report["issues"]]
    assert "chart_leak" in codes
    assert report["pass"] is False


def test_topic_drift(tmp_path):
    rr = _rr(content="钢铁煤炭纺织" * 300)
    report = collect_issues(rr, CASE, tmp_path)
    assert any(i["code"] == "topic_drift" for i in report["issues"])


def test_missing_chart_png(tmp_path):
    charts = [{"title": "t", "path": str(tmp_path / "nope.png"), "source": "ok",
               "caption": "n"}]
    report = collect_issues(_rr(charts), CASE, tmp_path)
    assert any(i["code"] == "chart_missing" for i in report["issues"])


def test_report_saved(tmp_path):
    report = collect_issues(_rr(), CASE, tmp_path)
    save_review_report(tmp_path, round_num=1, report=report)
    saved = Path(tmp_path / "review_report.json")
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["round"] == 1 and "issues" in data


def test_metadata_issues(tmp_path):
    rr = _rr()
    rr["formal_complete"] = False
    rr["quality_gate_status"] = "blocked"
    rr["defense_audit"] = {"issues": [{"code": "missing_source_url", "section": "s1"}]}
    report = collect_issues(rr, CASE, tmp_path)
    codes = [i["code"] for i in report["issues"]]
    assert {"formal_incomplete", "quality_gate", "missing_source_url"} <= set(codes)
    assert report["pass"] is False   # missing_source_url 为 high


def test_chart_no_caption(tmp_path):
    charts = [{"title": "t", "path": str(tmp_path / "x.png"), "source": "ok"}]
    (tmp_path / "x.png").write_bytes(b"png")
    report = collect_issues(_rr(charts), CASE, tmp_path)
    assert any(i["code"] == "chart_no_caption" for i in report["issues"])
    assert report["pass"] is True     # 仅 low 不 fail


def test_none_path_no_false_positive(tmp_path):
    charts = [{"title": "t", "path": None, "source": "ok", "caption": "n"}]
    report = collect_issues(_rr(charts), CASE, tmp_path)
    assert not any(i["code"] == "chart_missing" for i in report["issues"])


def test_empty_keywords_skip_drift(tmp_path):
    case = CaseConfig(case_id="c2", topic="中国量子计算产业深度研究报告",
                      domain_keywords=[])
    report = collect_issues(_rr(content="无关键词内容" * 300), case, tmp_path)
    assert not any(i["code"] == "topic_drift" for i in report["issues"])
