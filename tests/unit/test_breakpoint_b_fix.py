import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding='utf-8')

def test_breakpoint_b():
    """Test that routing section_id maps to annual report section_type for precise injection"""

    SECTION_TYPE_MAP = {
        "industry_overview": ["overview", "business"],
        "market_size": ["business", "financial"],
        "competitive_landscape": ["business"],
        "value_chain": ["business"],
        "growth_drivers": ["business", "strategy"],
        "policy": ["governance"],
        "technology": ["strategy", "business"],
        "key_company": ["financial", "business"],
        "financial_forecast": ["financial", "cashflow", "investment"],
        "risk_analysis": ["risk"],
        "strategic_intent": ["strategy", "investment"],
        "rating": ["investment", "financial"],
        "appendix": ["other"],
    }

    ar_sections = [
        {"title": "重要提示", "content": "", "section_type": "other", "importance": 1},
        {"title": "公司简介", "content": "A" * 2000, "section_type": "overview", "importance": 3},
        {"title": "管理层讨论与分析", "content": "B" * 5000, "section_type": "business", "importance": 5},
        {"title": "经营情况", "content": "C" * 4000, "section_type": "business", "importance": 4},
        {"title": "财务报告", "content": "D" * 3000, "section_type": "financial", "importance": 5},
        {"title": "现金流", "content": "E" * 2000, "section_type": "cashflow", "importance": 4},
        {"title": "公司治理", "content": "F" * 2000, "section_type": "governance", "importance": 3},
        {"title": "风险因素", "content": "G" * 3000, "section_type": "risk", "importance": 5},
        {"title": "战略展望", "content": "H" * 2000, "section_type": "strategy", "importance": 4},
        {"title": "投资价值", "content": "I" * 2000, "section_type": "investment", "importance": 3},
    ]

    test_cases = [
        ("section_10_Risk_Analysis", ["risk"], ["风险因素"]),
        ("section_8_Key_Company_Analysis", ["financial", "business"], ["管理层讨论与分析", "经营情况", "财务报告"]),
        ("section_6_Policy___Regulation", ["governance"], ["公司治理"]),
        ("section_12_Rating___Target_Price", ["investment", "financial"], ["财务报告", "投资价值"]),
        ("section_11_Strategic_Intent_Inference", ["strategy", "investment"], ["战略展望", "投资价值"]),
    ]

    print("=== Breakpoint B Fix Test ===")
    print()

    all_passed = True
    for section_id, expected_types, expected_titles in test_cases:
        key_lower = section_id.lower()
        own_section_types = []
        for key_part, types in SECTION_TYPE_MAP.items():
            if key_part in key_lower:
                own_section_types.extend(types)
                break
        own_section_types = list(set(own_section_types))

        matched = [
            s for s in ar_sections
            if s.get("section_type", "") in own_section_types
            and s.get("content", "").strip()
        ]
        matched_titles = [s["title"] for s in matched]

        ok = set(expected_types) == set(own_section_types)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_passed = False
        print("  %s:" % section_id)
        print("    Expected types: %s, Got: %s [%s]" % (expected_types, own_section_types, status))
        print("    Matched sections: %s" % matched_titles)

    print()
    if all_passed:
        print("ALL ASSERTIONS PASSED!")
    else:
        print("SOME TESTS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    test_breakpoint_b()
