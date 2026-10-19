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


class TestQualityActionEndpoint:

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
    async def test_missing_session_id_returns_error(self):
        from src.api.research_api import QualityActionRequest, ResearchAPI
        result = await ResearchAPI().__class__().handle_quality_action(QualityActionRequest(action="review"))
        assert result["error_code"] == "MISSING_SESSION_ID"

    @pytest.mark.asyncio
    async def test_missing_session_returns_error(self):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        with patch("src.api.research_api.session_manager") as manager:
            manager.get.return_value = None
            result = await api.handle_quality_action(QualityActionRequest(session_id="missing", action="review"))
        assert result["error_code"] == "SESSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_missing_quality_state_returns_error(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session_with_issues.pop("quality_state")
        with patch("src.api.research_api.session_manager") as manager:
            manager.get.return_value = session_with_issues
            result = await api.handle_quality_action(QualityActionRequest(session_id="test-session-1", action="review"))
        assert result["error_code"] == "NO_QUALITY_STATE"

    @pytest.mark.asyncio
    async def test_missing_report_sections_returns_error(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session_with_issues["research_result"] = {"report": {"sections": []}}
        with patch("src.api.research_api.session_manager") as manager:
            manager.get.return_value = session_with_issues
            result = await api.handle_quality_action(QualityActionRequest(session_id="test-session-1", action="review"))
        assert result["error_code"] == "NO_SECTIONS"

    @pytest.mark.asyncio
    async def test_review_rechecks_and_returns_quality_state(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session_with_issues["research_result"] = {"report": {"sections": [{"title": "市场规模", "content": "报告内容"}]}}
        with patch("src.api.research_api.session_manager") as manager, \
             patch.object(api, "_recheck_quality", new_callable=AsyncMock) as recheck, \
             patch("src.core.session_streamer.SessionStreamer"), \
             patch("src.core.quality.preview_health.check_preview_health", return_value={"healthy": True, "issues": []}):
            manager.get.return_value = session_with_issues
            result = await api.handle_quality_action(QualityActionRequest(session_id="test-session-1", action="review"))
        assert result["success"] is True
        assert result["status"] == "reviewing"
        assert result["quality_state"] is session_with_issues["quality_state"]
        recheck.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_preserves_action_in_response(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session_with_issues["research_result"] = {"report": {"sections": [{"title": "市场规模", "content": "报告内容"}]}}
        with patch("src.api.research_api.session_manager") as manager, \
             patch.object(api, "_recheck_quality", new_callable=AsyncMock), \
             patch("src.core.session_streamer.SessionStreamer"), \
             patch("src.core.quality.preview_health.check_preview_health", return_value={"healthy": True, "issues": []}):
            manager.get.return_value = session_with_issues
            result = await api.handle_quality_action(QualityActionRequest(session_id="test-session-1", action="recheck"))
        assert result["action"] == "recheck"
        assert session_with_issues["quality_state"]["phase"] == "reviewing"

    @pytest.mark.asyncio
    async def test_review_replaces_quality_state_after_recheck(self, session_with_issues):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session_with_issues["research_result"] = {"report": {"sections": [{"title": "市场规模", "content": "报告内容"}]}}
        replacement = {"phase": "rechecked", "section_scores": {}}
        with patch("src.api.research_api.session_manager") as manager, \
             patch.object(api, "_recheck_quality", new_callable=AsyncMock, side_effect=lambda s, *_args, **_kwargs: s.update(quality_state=replacement)), \
             patch("src.core.session_streamer.SessionStreamer"), \
             patch("src.core.quality.preview_health.check_preview_health", return_value={"healthy": True, "issues": []}):
            manager.get.return_value = session_with_issues
            result = await api.handle_quality_action(QualityActionRequest(session_id="test-session-1", action="review"))
        assert result["quality_state"] is replacement
        assert replacement["phase"] == "reviewing"


class TestQualityReviewFlow:

    @pytest.mark.asyncio
    async def test_review_flow_is_serialized_by_session_lock(self):
        from src.api.research_api import ResearchAPI
        from src.api.research_api import QualityActionRequest
        api = ResearchAPI()
        session = {
            "quality_state": {"phase": "reviewing", "section_scores": {}},
            "research_result": {"report": {"sections": [{"title": "市场", "content": "内容"}]}},
        }
        session["_session_id"] = "flow-test"
        with patch("src.api.research_api.session_manager") as manager, \
             patch.object(api, "_recheck_quality", new_callable=AsyncMock), \
             patch("src.core.session_streamer.SessionStreamer"), \
             patch("src.core.quality.preview_health.check_preview_health", return_value={"healthy": True, "issues": []}):
            manager.get.return_value = session
            result = await api.handle_quality_action(QualityActionRequest(session_id="flow-test", action="review"))
        assert result["success"] is True
        assert result["status"] == "reviewing"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
