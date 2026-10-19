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


def resolve_section_types(section_id: str):
    if not section_id:
        return []
    sid_lower = section_id.lower()
    for key_part, types in SECTION_TYPE_MAP.items():
        if key_part in sid_lower:
            return types
    return []
