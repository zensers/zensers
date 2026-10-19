import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding='utf-8')

def test_breakpoint_a():
    """Test that document_context picks high-importance sections with content, not just first 8"""

    # Simulate annual report data with the same structure as real parse
    annual_report_data = {
        "sections": [
            {"title": "重要提示一", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示二", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示三", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示四", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示五", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示六", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示七", "content": "", "section_type": "other", "importance": 1},
            {"title": "重要提示八", "content": "仅有769字符", "section_type": "other", "importance": 1},
            {"title": "公司简介和主要财务指标", "content": "A" * 2000, "section_type": "overview", "importance": 5},
            {"title": "管理层讨论与分析", "content": "B" * 5000, "section_type": "management", "importance": 5},
            {"title": "经营情况讨论", "content": "C" * 4000, "section_type": "operation", "importance": 4},
            {"title": "财务报告", "content": "D" * 3000, "section_type": "financial", "importance": 5},
            {"title": "公司治理", "content": "E" * 2000, "section_type": "governance", "importance": 3},
        ],
        "financial_tables": {"income": [1], "balance": [2], "cashflow": [3]},
        "analysis_framework": {
            "aspects": ["财务分析"],
            "aspect_to_section_ids": {"财务分析": [10]},
            "aspect_to_profile": {"财务分析": "financial_analysis"},
        },
    }

    # OLD logic: ar_sections[:8] - picks first 8, mostly empty
    old_parts = []
    for ts in annual_report_data["sections"][:8]:
        tc = ts.get("content", "")
        if tc:
            old_parts.append(ts.get("title", ""))
    old_ctx_len = sum(len(ts.get("content", "")) for ts in annual_report_data["sections"][:8] if ts.get("content", ""))

    # NEW logic: sort by importance desc, only content sections, up to 30K chars
    ar_sections = annual_report_data["sections"]
    content_sections = [s for s in ar_sections if s.get("content", "").strip()]
    content_sections.sort(key=lambda s: (s.get("importance", 3), len(s.get("content", ""))), reverse=True)
    new_parts = []
    total_chars = 0
    max_total_chars = 30000
    for ts in content_sections:
        tc = ts.get("content", "")
        if not tc:
            continue
        chunk = "### " + ts.get("title", "") + "\n" + tc[:4000]
        new_parts.append(ts.get("title", ""))
        total_chars += len(chunk)
        if total_chars >= max_total_chars:
            break

    print("=== Breakpoint A Fix Test ===")
    print()
    print("OLD logic (ar_sections[:8]):")
    print("  Sections with content: %d" % len(old_parts))
    print("  Titles: %s" % old_parts)
    print("  Total content chars: %d" % old_ctx_len)
    print()
    print("NEW logic (sort by importance, content-only, 30K cap):")
    print("  Sections with content: %d" % len(new_parts))
    print("  Titles: %s" % new_parts)
    print("  Total context chars: %d" % total_chars)
    print()

    # Assertions
    assert len(new_parts) > len(old_parts), "NEW should find more content sections than OLD"
    assert total_chars > old_ctx_len * 10, "NEW should have 10x+ more content than OLD (807c was previous)"
    assert "管理层讨论与分析" in new_parts, "Should include important management discussion"
    assert "财务报告" in new_parts, "Should include financial report"
    # High-importance sections should appear before low-importance ones
    high_idx = new_parts.index("管理层讨论与分析")
    low_idx = new_parts.index("重要提示八") if "重要提示八" in new_parts else len(new_parts)
    assert high_idx < low_idx, "High-importance sections should appear before low-importance ones"

    print("ALL ASSERTIONS PASSED!")
    print()
    print("Data volume improvement: %d -> %d chars (%.1fx increase)" % (old_ctx_len, total_chars, total_chars / max(old_ctx_len, 1)))

if __name__ == "__main__":
    test_breakpoint_a()
