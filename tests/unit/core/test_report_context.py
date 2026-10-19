from src.core.report_context import build_report_context


def test_build_report_context_supports_nested_report_and_quality_summary():
    session = {
        "research_context": {"topic": "新能源"},
        "output_format": "pptx",
        "research_result": {
            "status": "completed",
            "report": {
                "topic": "新能源",
                "sections": [
                    {"id": "s1", "title": "市场规模", "content": "一 二 三", "sources": [{"id": "a"}]},
                ],
            },
        },
        "quality_state": {
            "overall_score": 88,
            "overall_status": "warning",
            "section_scores": {
                "市场规模": {"status": "passed", "issues": [{"state": "open"}, {"state": "resolved"}]},
            },
        },
    }

    context = build_report_context("session-1", session, phase="completed")

    assert context["session_id"] == "session-1"
    assert context["report_phase"] == "completed"
    assert context["report_version"] == 0
    assert context["context_revision"] == 1
    assert context["sections"] == [{
        "id": "s1",
        "title": "市场规模",
        "order": 0,
        "status": "ready",
        "word_count": 3,
        "source_count": 1,
        "quality_status": "passed",
        "summary": None,
    }]
    assert context["quality"]["open_issue_count"] == 1


def test_build_report_context_is_monotonic_from_previous_snapshot():
    session = {
        "report_context": {
            "report_version": 4,
            "context_revision": 9,
            "report_phase": "revising",
            "last_revision": {"status": "executing"},
        },
        "research_result": {"status": "completed", "sections": []},
    }

    context = build_report_context(session_id="session-2", session=session, report_version_increment=True)

    assert context["report_version"] == 5
    assert context["context_revision"] == 10
    assert context["report_phase"] == "revising"
    assert context["last_revision"] == {"status": "executing"}


def test_read_repairs_stale_researching_context_for_reporting_session():
    session = {
        "status": "reporting",
        "output_format": "docx",
        "report_context": {
            "report_phase": "researching",
            "report_version": 1,
            "context_revision": 7,
        },
    }

    context = build_report_context("s-reporting", session)

    assert context["report_phase"] == "report_generating"
    assert context["report_version"] == 1
    assert context["context_revision"] == 8
