from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.fixed_agents.report_upgrade.evidence_acquisition import ReportEvidenceAcquirer
from src.agents.fixed_agents.report_upgrade.models import DataGap


@pytest.mark.asyncio
async def test_report_acquirer_searches_gateway_and_preserves_identity():
    gateway = SimpleNamespace(search=AsyncMock(return_value=SimpleNamespace(
        success=True,
        results=[SimpleNamespace(
            title="Market outlook", url="https://example.test/a",
            snippet="Growth is 12%", source="official",
            excerpt="Growth is 12%", evidence_id="ev_1",
            provenance_id="prov_1", locator="p1", task_id="t1",
            request_id="r1", retrieved_at="2026-01-01",
        )],
    )))
    acquirer = ReportEvidenceAcquirer(gateway)
    llm = {"success": True, "content": '{"found": true, "value": "12", "unit": "%", "source_title": "Market outlook", "period": "2025"}'}
    with patch("src.agents.fixed_agents.report_upgrade.evidence_acquisition.call_llm", new=AsyncMock(return_value=llm)):
        result = await acquirer.acquire(
            DataGap("market", "growth", "growth rate", ["growth"]), "industry",
        )
    assert result.found is True
    assert result.evidence_id == "ev_1"
    assert result.provenance_id == "prov_1"
    gateway.search.assert_awaited_once()
    assert gateway.search.call_args.kwargs["scope"] == "report_generation"


@pytest.mark.asyncio
async def test_report_acquirer_search_failure_is_insufficient_evidence():
    gateway = SimpleNamespace(search=AsyncMock(side_effect=RuntimeError("provider down")))
    result = await ReportEvidenceAcquirer(gateway).acquire(
        DataGap("market", "growth", "growth rate"), "industry",
    )
    assert result.found is False


def test_report_acquirer_rejects_url_outside_search_candidates():
    evidence = [{
        "title": "Official source",
        "url": "https://example.test/official",
        "source": "official",
        "evidence_id": "ev-official",
        "provenance_id": "prov-official",
    }]

    result = ReportEvidenceAcquirer._parse(
        '{"found": true, "value": "12", '
        '"source_url": "https://untrusted.example/answer"}',
        DataGap("market", "growth", "growth rate"),
        evidence,
    )

    assert result.found is False
