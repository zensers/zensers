# tests/unit/core/test_failure_audit.py
# -*- coding: utf-8 -*-
import json, os
from src.core.failure_audit import FailureAudit


def test_record_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("FAILURE_AUDIT_DIR", str(tmp_path))
    FailureAudit.record(stage="report.defense.rescue", subject_id="section_5",
                        action="skip", reason="no cached material",
                        severity="warn", delivery_impact="degraded",
                        task_id="t1")
    path = os.path.join(str(tmp_path), "t1.jsonl")
    assert os.path.exists(path)
    row = json.loads(open(path, encoding="utf-8").read().strip())
    assert row["stage"] == "report.defense.rescue"
    assert row["subject_id"] == "section_5"
    assert row["action"] == "skip"
    assert row["severity"] == "warn"
    assert row["delivery_impact"] == "degraded"
    assert "timestamp" in row

def test_record_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("FAILURE_AUDIT_DIR", str(tmp_path) + "/nonexistent/deep")
    FailureAudit.record(stage="s", subject_id="x", action="skip", reason="r")
    # 不抛异常即通过（留痕失败只 log）
