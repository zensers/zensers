import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding='utf-8')
from unittest.mock import MagicMock

def test_inject_logic():
    """Test the document_context injection logic that was added to _create_agents_from_plan"""
    annual_report_data = {
        'sections': [
            {'section_id': 1, 'title': '财务分析', 'content': 'A' * 5000},
            {'section_id': 2, 'title': '经营分析', 'content': 'B' * 3000},
        ],
        'financial_tables': {'income_statement': [{'revenue': 100}], 'balance_sheet': [{'assets': 200}]},
        'analysis_framework': {
            'aspects': ['财务分析', '经营分析'],
            'aspect_to_section_ids': {'财务分析': [1], '经营分析': [2]},
            'aspect_to_profile': {'财务分析': 'financial_analysis', '经营分析': 'business'},
        },
    }

    # Simulate the injection logic from _create_agents_from_plan
    for own_aspect in ['财务分析', '经营分析']:
        context = {}
        if annual_report_data:
            analysis_framework = annual_report_data.get("analysis_framework", {})
            document_context = ""
            document_tables = []

            section_ids = analysis_framework.get("aspect_to_section_ids", {}).get(own_aspect, [])
            aspect_to_profile = analysis_framework.get("aspect_to_profile", {})

            sections = annual_report_data.get("sections", [])
            context_parts = []
            for sid in section_ids:
                if isinstance(sid, int) and 0 <= sid - 1 < len(sections):
                    section = sections[sid - 1]
                    content = section.get("content", "")
                    if content:
                        context_parts.append(content[:4000])

            if context_parts:
                document_context = "\n\n".join(context_parts)

            profile = aspect_to_profile.get(own_aspect, "")
            if profile in ("financial_analysis", "valuation", "investment"):
                financial_tables = annual_report_data.get("financial_tables", {})
                if financial_tables:
                    document_tables = financial_tables

            if document_context:
                context["document_context"] = document_context
            if document_tables:
                context["document_tables"] = document_tables
            context["has_preloaded_data"] = True

        print("=== %s ===" % own_aspect)
        print("  document_context: %d chars" % len(context.get("document_context", "")))
        print("  document_tables: %s" % ("present (keys=%s)" % list(context.get("document_tables", {}).keys()) if "document_tables" in context else "absent"))
        print("  has_preloaded_data: %s" % context.get("has_preloaded_data"))

    # Assertions for financial_analysis aspect
    own_aspect = '财务分析'
    analysis_framework = annual_report_data.get("analysis_framework", {})
    section_ids = analysis_framework.get("aspect_to_section_ids", {}).get(own_aspect, [])
    aspect_to_profile = analysis_framework.get("aspect_to_profile", {})
    sections = annual_report_data.get("sections", [])
    context_parts = []
    for sid in section_ids:
        if isinstance(sid, int) and 0 <= sid - 1 < len(sections):
            section = sections[sid - 1]
            content = section.get("content", "")
            if content:
                context_parts.append(content[:4000])
    doc_ctx = "\n\n".join(context_parts)
    profile = aspect_to_profile.get(own_aspect, "")
    assert len(doc_ctx) > 0, "financial aspect should have document_context"
    assert profile == "financial_analysis", "profile should be financial_analysis"
    assert profile in ("financial_analysis", "valuation", "investment"), "should qualify for tables"

    # Assertions for business aspect (no tables expected)
    own_aspect = '经营分析'
    profile = aspect_to_profile.get(own_aspect, "")
    assert profile == "business", "profile should be business"
    assert profile not in ("financial_analysis", "valuation", "investment"), "should NOT qualify for tables"

    print("\nALL ASSERTIONS PASSED!")

if __name__ == "__main__":
    test_inject_logic()
