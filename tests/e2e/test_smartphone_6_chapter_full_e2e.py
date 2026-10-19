"""Real end-to-end research run for a compact China smartphone report.

Unlike the deterministic routing test, this test enters the production
``ResearchOrchestrator.research`` API and executes the complete workflow with
the configured LLM/search providers.  Six chapters keep the run practical for
repeatable E2E validation.
"""

import os
import uuid

import pytest

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure
from src.core.orchestrator.orchestrator import ResearchOrchestrator


TOPIC = "中国智能手机行业分析"
CHAPTERS = [
    "市场规模与出货量",
    "品牌竞争格局",
    "产品结构与价格带",
    "渠道与用户需求",
    "芯片与操作系统生态",
    "政策环境与未来趋势",
]

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_llm]


def _has_llm_configuration() -> bool:
    return bool(
        os.environ.get("LLM_API_KEY")
        or os.environ.get("LLM_MODEL")
        or os.environ.get("OPENAI_API_KEY")
    )


@pytest.mark.asyncio
async def test_real_smartphone_six_chapter_research_completes():
    if not _has_llm_configuration():
        pytest.skip("real LLM configuration is required for this E2E")

    init_llm_infrastructure(settings.llm_profiles)
    task_id = f"e2e_smartphone6_{uuid.uuid4().hex[:8]}"
    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)

    # Deep research may legitimately spend a long time on retrieval,
    # verification, retries, and report refinement.  Do not impose a test-
    # level wall-clock limit; cancellation belongs to the external runner.
    result = await orchestrator.research(
        user_input={
            "session_id": task_id,
            "topic": TOPIC,
            "aspects": CHAPTERS,
            "output_type": "industry_report",
            "output_format": "html",
        },
        user_id="e2e",
        interaction_mode=False,
        output_type="industry_report",
        custom_aspects=CHAPTERS,
        framework="standard",
        output_format="html",
    )

    assert result.status in ("completed", "completed_with_warnings"), result.summary
    assert result.report and isinstance(result.report.get("sections"), list)
    assert len(result.report["sections"]) >= len(CHAPTERS)

    routing = result.intent_analysis or {}
    dag_audit = routing.get("dag_audit") or {}
    dag_document = routing.get("dag_document") or {}
    review_history = routing.get("dag_review_history") or []
    assert dag_audit.get("passed") is True
    assert len(dag_document.get("sections") or []) == len(CHAPTERS)
    assert review_history and review_history[-1].get("passed") is True

    report_text = str(result.report)
    assert TOPIC in report_text or "智能手机" in report_text
    assert not any(term in report_text for term in ("光伏", "新能源汽车", "动力电池"))
