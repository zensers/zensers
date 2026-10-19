# -*- coding: utf-8 -*-
"""ses_baf7a884 实证回归：质检返工骨架替换丢失报告级字段（Word 缺
口径前置节/交付签名）。_preserve_report_level_fields 必须跨代保全。"""
from src.core.orchestrator.orchestrator import _preserve_report_level_fields


def test_preserves_report_level_fields_from_previous_generation():
    previous = {
        "sections": [{"section_id": "s0", "title": "旧", "content": "旧内容"}],
        "key_findings": ["旧发现"],
        "methodology_notes": ["全球与中国市场统计口径不同，不合并比较。"],
        "delivery_signature": {"delivery_class": "formal", "quality_gate": "passed"},
        "defense_audit": {"passed": True, "score": 92.0, "layers": {}},
        "exec_summary": "摘要",
        "claims": [{"metric": "规模"}],
    }
    rebuilt = {
        "sections": [{"section_id": "s0", "title": "新", "content": "修复后的新内容"}],
        "title": "人工智能行业",
    }
    out = _preserve_report_level_fields(previous, rebuilt)
    assert out["sections"][0]["title"] == "新", "新代章节内容必须保留（返工成果）"
    assert out["methodology_notes"] == previous["methodology_notes"]
    assert out["delivery_signature"] == previous["delivery_signature"]
    assert out["defense_audit"] == previous["defense_audit"]
    assert out["exec_summary"] == "摘要"
    assert out["claims"] == previous["claims"]
    assert out["key_findings"] == previous["key_findings"]


def test_rebuilt_nonempty_fields_win_over_previous():
    """新代已有的非空字段不被旧代覆盖（返工修正不被回滚）。"""
    previous = {
        "key_findings": ["旧发现"],
        "methodology_notes": ["旧口径"],
    }
    rebuilt = {
        "key_findings": ["返工后的新发现"],
        "sections": [],
    }
    out = _preserve_report_level_fields(previous, rebuilt)
    assert out["key_findings"] == ["返工后的新发现"]
    assert out["methodology_notes"] == ["旧口径"]


def test_no_previous_fields_leaves_rebuilt_untouched():
    rebuilt = {"sections": [], "title": "T"}
    assert _preserve_report_level_fields({}, rebuilt) == {"sections": [], "title": "T"}
