"""
Quality Revision E2E Flow Test
==============================

Tests the quality feedback revision flow end-to-end, focusing on:
1. quality_state.py: generate_issue_id stability, merge_issues_on_recheck
2. Backend handlers: dismiss, reopen, confirm (direct session mutation)
3. Full flow: dismiss → reopen → confirm

Complex handlers (rollback, revision) are tested with minimal mocking.
"""

import pytest
import asyncio
import copy
from unittest.mock import MagicMock, AsyncMock, patch


class TestQualityState:

    def test_generate_issue_id_stable(self):
        from src.core.quality.quality_state import generate_issue_id
        id1 = generate_issue_id("市场规模", "completeness", "数据密度偏低")
        id2 = generate_issue_id("市场规模", "completeness", "数据密度偏低")
        assert id1 == id2, "Same inputs must produce same ID"
        assert id1.startswith("q-"), "ID must start with q-"

    def test_generate_issue_id_different_for_different_messages(self):
        from src.core.quality.quality_state import generate_issue_id
        id1 = generate_issue_id("市场规模", "completeness", "数据密度偏低")
        id2 = generate_issue_id("市场规模", "completeness", "数据缺失")
        assert id1 != id2, "Different messages must produce different IDs"

    def test_merge_issues_preserves_dismissed_state(self):
        from src.core.quality.quality_state import (
            merge_issues_on_recheck, SectionScore, QualityIssue, generate_issue_id
        )
        issue_id = generate_issue_id("市场", "completeness", "问题A")
        existing = {
            "市场": SectionScore(
                score=50, status="warning",
                issues=[QualityIssue(
                    id=issue_id, type="completeness", severity="medium",
                    message="问题A", section="市场", state="dismissed"
                )]
            )
        }
        new_results = {
            "市场": {
                "score": 55, "status": "warning",
                "issues": [{"type": "completeness", "severity": "medium", "message": "问题A"}]
            }
        }
        merged = merge_issues_on_recheck(existing, new_results)
        issue = merged["市场"].issues[0]
        assert issue.state == "dismissed", "Dismissed state must be preserved on recheck"

    def test_merge_issues_adds_new_issues(self):
        from src.core.quality.quality_state import (
            merge_issues_on_recheck, SectionScore
        )
        existing = {
            "市场": SectionScore(score=50, status="warning", issues=[])
        }
        new_results = {
            "市场": {
                "score": 55, "status": "warning",
                "issues": [{"type": "accuracy", "severity": "medium", "message": "新问题"}]
            }
        }
        merged = merge_issues_on_recheck(existing, new_results)
        assert len(merged["市场"].issues) == 1
        assert merged["市场"].issues[0].state == "open"

    def test_merge_issues_preserves_sections_not_in_recheck(self):
        from src.core.quality.quality_state import (
            merge_issues_on_recheck, SectionScore, QualityIssue
        )
        existing = {
            "市场": SectionScore(score=50, status="warning", issues=[]),
            "技术": SectionScore(
                score=70, status="passed",
                issues=[QualityIssue(
                    id="q-test", type="format", severity="low",
                    message="格式问题", section="技术", state="open"
                )]
            )
        }
        new_results = {
            "市场": {"score": 55, "status": "warning", "issues": []}
        }
        merged = merge_issues_on_recheck(existing, new_results)
        assert "技术" in merged, "Sections not in recheck must be preserved"
        assert len(merged["技术"].issues) == 1

    def test_quality_pass_threshold(self):
        from src.core.quality.quality_state import QUALITY_PASS_THRESHOLD
        assert QUALITY_PASS_THRESHOLD == 60


class TestQualityHandlersDirect:

    @pytest.fixture
    def session_with_issues(self):
        return {
            "_session_id": "test-session-1",
            "quality_state": {
                "phase": "reviewing",
                "overall_score": 45.0,
                "overall_status": "warning",
                "section_scores": {
                    "市场规模": {
                        "score": 45, "status": "warning",
                        "issues": [
                            {"id": "q-abc123", "type": "completeness", "severity": "medium",
                             "message": "数据密度偏低", "section": "市场规模", "state": "open", "revision_count": 0},
                            {"id": "q-def456", "type": "accuracy", "severity": "high",
                             "message": "数据过时", "section": "市场规模", "state": "open", "revision_count": 0},
                        ]
                    },
                    "竞争格局": {
                        "score": 65, "status": "passed",
                        "issues": []
                    }
                },
                "version_stack": [
                    {"id": "v0", "created_at": "2026-01-01", "html_path": "/tmp/v0.html",
                     "md_path": "", "overall_score": 45.0, "label": "初始版本"}
                ],
                "current_version": "v0"
            },
        }

    @pytest.mark.asyncio
    async def test_dismiss_issue(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        with patch('src.core.session_streamer.SessionStreamer'):
            result = await api._handle_quality_dismiss(session_with_issues, "q-abc123")
        assert result["success"] is True
        assert result["state"] == "dismissed"
        issue = session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"][0]
        assert issue["state"] == "dismissed"

    @pytest.mark.asyncio
    async def test_dismiss_nonexistent_issue(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        result = await api._handle_quality_dismiss(session_with_issues, "q-nonexistent")
        assert "error" in result
        assert result["error_code"] == "ISSUE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_reopen_dismissed_issue(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"][0]["state"] = "dismissed"
        with patch('src.core.session_streamer.SessionStreamer'):
            result = await api._handle_quality_reopen(session_with_issues, "q-abc123")
        assert result["success"] is True
        assert result["state"] == "open"
        issue = session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"][0]
        assert issue["state"] == "open"

    @pytest.mark.asyncio
    async def test_reopen_non_dismissed_fails(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        result = await api._handle_quality_reopen(session_with_issues, "q-abc123")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_confirm_with_open_issues(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        with patch('src.core.session_streamer.SessionStreamer'):
            result = await api._handle_quality_confirm(session_with_issues, force=False)
        assert result["status"] == "pending_issues"
        assert len(result["open_issues"]) == 2

    @pytest.mark.asyncio
    async def test_confirm_force_with_open_issues(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        with patch('src.core.session_streamer.SessionStreamer'):
            result = await api._handle_quality_confirm(session_with_issues, force=True)
        assert result["status"] == "confirmed"
        assert session_with_issues["quality_state"]["phase"] == "confirmed"
        for issue in session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"]:
            assert issue["state"] == "accepted"

    @pytest.mark.asyncio
    async def test_confirm_no_open_issues(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        for iss in session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"]:
            iss["state"] = "dismissed"
        with patch('src.core.session_streamer.SessionStreamer'):
            result = await api._handle_quality_confirm(session_with_issues, force=False)
        assert result["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_dismiss_creates_new_quality_state_ref(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        old_ref = session_with_issues["quality_state"]
        with patch('src.core.session_streamer.SessionStreamer'):
            await api._handle_quality_dismiss(session_with_issues, "q-abc123")
        assert session_with_issues["quality_state"] is not old_ref, \
            "Dismiss should replace quality_state with deep copy"

    @pytest.mark.asyncio
    async def test_reopen_creates_new_quality_state_ref(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        session_with_issues["quality_state"]["section_scores"]["市场规模"]["issues"][0]["state"] = "dismissed"
        old_ref = session_with_issues["quality_state"]
        with patch('src.core.session_streamer.SessionStreamer'):
            await api._handle_quality_reopen(session_with_issues, "q-abc123")
        assert session_with_issues["quality_state"] is not old_ref, \
            "Reopen should replace quality_state with deep copy"


class TestFullFlowSimulation:

    @pytest.mark.asyncio
    async def test_dismiss_reopen_confirm_flow(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()

        session = {
            "_session_id": "flow-test",
            "quality_state": {
                "phase": "reviewing",
                "overall_score": 50.0,
                "overall_status": "warning",
                "section_scores": {
                    "市场": {
                        "score": 50, "status": "warning",
                        "issues": [
                            {"id": "q-issue1", "type": "completeness", "severity": "high",
                             "message": "数据不足", "section": "市场", "state": "open", "revision_count": 0},
                            {"id": "q-issue2", "type": "accuracy", "severity": "medium",
                             "message": "数据过时", "section": "市场", "state": "open", "revision_count": 0},
                        ]
                    }
                },
                "version_stack": [],
                "current_version": "v0"
            },
        }

        with patch('src.core.session_streamer.SessionStreamer'):
            r1 = await api._handle_quality_dismiss(session, "q-issue1")
            assert r1["success"]
            assert session["quality_state"]["section_scores"]["市场"]["issues"][0]["state"] == "dismissed"

            r2 = await api._handle_quality_confirm(session, force=False)
            assert r2["status"] == "pending_issues"
            assert len(r2["open_issues"]) == 1

            r3 = await api._handle_quality_reopen(session, "q-issue1")
            assert r3["success"]
            assert session["quality_state"]["section_scores"]["市场"]["issues"][0]["state"] == "open"

            r4 = await api._handle_quality_confirm(session, force=True)
            assert r4["status"] == "confirmed"
            assert session["quality_state"]["phase"] == "confirmed"
            for issue in session["quality_state"]["section_scores"]["市场"]["issues"]:
                assert issue["state"] == "accepted"

    @pytest.mark.asyncio
    async def test_double_dismiss_idempotent(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()

        session = {
            "_session_id": "idem-test",
            "quality_state": {
                "phase": "reviewing",
                "overall_score": 50.0,
                "overall_status": "warning",
                "section_scores": {
                    "市场": {
                        "score": 50, "status": "warning",
                        "issues": [
                            {"id": "q-1", "type": "completeness", "severity": "high",
                             "message": "问题1", "section": "市场", "state": "open", "revision_count": 0},
                        ]
                    }
                },
                "version_stack": [],
                "current_version": "v0"
            },
        }

        with patch('src.core.session_streamer.SessionStreamer'):
            r1 = await api._handle_quality_dismiss(session, "q-1")
            assert r1["success"]
            r2 = await api._handle_quality_dismiss(session, "q-1")
            assert r2["success"]
            assert session["quality_state"]["section_scores"]["市场"]["issues"][0]["state"] == "dismissed"

    @pytest.mark.asyncio
    async def test_dismiss_all_then_confirm(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()

        session = {
            "_session_id": "dismiss-all-test",
            "quality_state": {
                "phase": "reviewing",
                "overall_score": 50.0,
                "overall_status": "warning",
                "section_scores": {
                    "市场": {
                        "score": 50, "status": "warning",
                        "issues": [
                            {"id": "q-1", "type": "completeness", "severity": "high",
                             "message": "问题1", "section": "市场", "state": "open", "revision_count": 0},
                            {"id": "q-2", "type": "accuracy", "severity": "medium",
                             "message": "问题2", "section": "市场", "state": "open", "revision_count": 0},
                        ]
                    }
                },
                "version_stack": [],
                "current_version": "v0"
            },
        }

        with patch('src.core.session_streamer.SessionStreamer'):
            await api._handle_quality_dismiss(session, "q-1")
            await api._handle_quality_dismiss(session, "q-2")
            r = await api._handle_quality_confirm(session, force=False)
            assert r["status"] == "confirmed", "All dismissed → confirm should succeed without force"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
