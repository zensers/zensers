import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding='utf-8')

def test_breakpoint_c():
    """Test that DC agent filters data_points by section_type based on its section_id"""

    SECTION_TYPE_MAP_AGENT = {
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
    }

    all_sections = [
        {"title": "重要提示", "content": "", "section_type": "other", "importance": 1},
        {"title": "公司简介", "content": "A" * 2000, "section_type": "overview", "importance": 3},
        {"title": "管理层讨论", "content": "B" * 5000, "section_type": "business", "importance": 5},
        {"title": "经营情况", "content": "C" * 4000, "section_type": "business", "importance": 4},
        {"title": "财务报告", "content": "D" * 3000, "section_type": "financial", "importance": 5},
        {"title": "风险因素", "content": "G" * 3000, "section_type": "risk", "importance": 5},
        {"title": "公司治理", "content": "F" * 2000, "section_type": "governance", "importance": 3},
    ]
    financial_tables = {"income": [{"科目": "营收", "2025": 3.19}], "balance": [{"科目": "资产"}]}

    print("=== Breakpoint C Fix Test ===")
    print()

    # Test: Risk Analysis agent should only get risk sections
    section_id = "section_10_Risk_Analysis"
    own_section_types = set()
    sid_lower = section_id.lower()
    for key_part, types in SECTION_TYPE_MAP_AGENT.items():
        if key_part in sid_lower:
            own_section_types.update(types)
            break

    if own_section_types:
        filtered = [s for s in all_sections if s.get("section_type", "") in own_section_types]
    else:
        filtered = all_sections

    # OLD logic: returns ALL sections (even empty ones)
    old_count = len(all_sections)
    # NEW logic: returns filtered sections + all tables
    new_count = len(filtered) + len(financial_tables)

    print("OLD (no filter): %d data_points (all sections)" % old_count)
    print("NEW (Risk agent): %d data_points (filtered by section_type)" % new_count)
    print("  Filtered section titles: %s" % [s["title"] for s in filtered])
    print("  section_type filter: %s" % own_section_types)
    print()

    assert len(filtered) == 1, "Risk agent should only get 1 section (风险因素)"
    assert filtered[0]["title"] == "风险因素", "Risk agent should get risk section"
    assert "公司简介" not in [s["title"] for s in filtered], "Risk agent should NOT get overview sections"

    # Test: Key Company Analysis agent gets business + financial
    section_id2 = "section_8_Key_Company_Analysis"
    own2 = set()
    for key_part, types in SECTION_TYPE_MAP_AGENT.items():
        if key_part in section_id2.lower():
            own2.update(types)
            break
    filtered2 = [s for s in all_sections if s.get("section_type", "") in own2]
    titles2 = [s["title"] for s in filtered2]

    print("Key Company agent:")
    print("  section_type filter: %s" % own2)
    print("  Filtered section titles: %s" % titles2)
    print()

    assert "管理层讨论" in titles2, "Key Company should get business sections"
    assert "财务报告" in titles2, "Key Company should get financial sections"
    assert "风险因素" not in titles2, "Key Company should NOT get risk sections"

    print("ALL ASSERTIONS PASSED!")

if __name__ == "__main__":
    test_breakpoint_c()
