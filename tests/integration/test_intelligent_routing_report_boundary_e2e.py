"""Deterministic E2E boundary test for the collection -> report hand-off.

This uses the persisted ``research_5690d293`` collection artifact as a
production-shaped fixture and replaces only the LLM writer/reviewers.  It is
intended to answer the diagnostic question "did report generation lose the
section identity?" without issuing real search or LLM calls.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.fixed_agents.report_upgrade.models import (
    ChapterReviewOutput,
    ChapterWriteOutput,
    ReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


RUN_ID = "research_5690d293"


@dataclass
class _Provenance:
    source_key: str
    section_target: str
    stage: str = "analysis"


class _PersistedAggregation:
    """Adapter matching the live AggregationResult identity contract."""

    def __init__(self, payload: dict):
        self.sources = payload.get("sources", [])
        self.conflicts = []
        self.stats = {}
        self.data = {"data_points": payload.get("data_points", [])}
        self.layered_content = {"analysis": {}}
        self.content_provenance = {}

        for agent_id, agent_payload in payload.get("agent_contents", {}).items():
            # The persisted cache stores agent_id -> content.  The stable
            # section identity is carried separately by provenance in a live
            # aggregation object; this is the exact seam under test.
            section_id = "section_0_市场规模"
            content = agent_payload.get("content", "") if isinstance(agent_payload, dict) else str(agent_payload)
            self.layered_content["analysis"][agent_id] = {
                "content": content,
                "data_points": payload.get("data_points", []),
            }
            self.content_provenance[agent_id] = _Provenance(
                source_key=agent_id,
                section_target=section_id,
            )


def _load_sample() -> dict:
    path = Path("data") / "results" / RUN_ID / "result.json"
    if not path.exists():
        pytest.skip(f"production-shaped sample is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_collection_artifact_reaches_report_with_stable_section_id(tmp_path):
    payload = _load_sample()
    aggregation = _PersistedAggregation(payload)
    section_id = "section_0_市场规模"

    writer = AsyncMock()
    writer.write.return_value = ChapterWriteOutput(
        chapter_id=section_id,
        title="市场规模",
        content="### 市场规模\n全球市场规模及增长证据。",
    )
    reviewer = AsyncMock()
    reviewer.review.return_value = ChapterReviewOutput(passed=True, score=90)
    global_reviewer = AsyncMock()
    global_reviewer.review.return_value = ReviewOutput(overall_score=90)

    orchestrator = ReportOrchestrator(
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        prompt_manager=PromptManager(),
    )
    task_structure = {
        "topic": payload.get("topic", "锂电池行业市场规模"),
        "sections": [{
            "section_id": section_id,
            "section_name": "市场规模",
            "section_role": "analysis",
            "content_dependency": [],
        }],
    }

    extracted, _ = orchestrator._extract_chapter_data(aggregation, section_id, [])
    assert extracted.get("content"), "report boundary lost the collected content"
    assert "锂电池" in extracted["content"]

    result = await orchestrator.generate_report(
        task_structure=task_structure,
        framework_config={"name": "行业研究报告"},
        aggregated_result=aggregation,
        topic=task_structure["topic"],
        # No task_id keeps this deterministic seam test from creating a
        # checkpoint that could affect a later rerun.
    )

    assert [item["id"] for item in result["sections"]] == [section_id]
    assert result["sections"][0]["content"]
    assert result["sources"], "source catalog was dropped before report assembly"
    assert writer.write.await_count == 1


def test_persisted_sample_is_incomplete_before_report_boundary():
    payload = _load_sample()
    assert payload["status"] == "collecting"
    assert payload.get("sections") == []
    assert payload.get("agent_contents")
    assert payload.get("sources")
