"""Continue and verify the real report-generation phase from a real run.

The preceding full lifecycle run already completed real search and analysis and
left report checkpoints on disk.  This test deliberately resumes that report
phase so it does not repeat the expensive collection calls.
"""

import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


RUN_ID = os.environ.get(
    "REAL_REPORT_E2E_RUN_ID", "e2e_smartphone6_56e991bf"
)
DATA_DIR = Path("data")


def _configure_generation_logging(run_id: str) -> tuple[logging.Logger, Path]:
    """Create an isolated, durable log for the real generation test."""
    log_dir = DATA_DIR / run_id / "real_report_e2e"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "generation.log"
    logger = logging.getLogger(f"real_report_e2e.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(handler, "baseFilename", None) == str(log_path.resolve())
               for handler in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
        ))
        logger.addHandler(handler)
    return logger, log_path


def _instrument_async_method(owner, method_name: str, logger: logging.Logger, label: str) -> None:
    """Log async boundaries without changing the wrapped method's behavior."""
    original = getattr(owner, method_name)

    async def logged_method(*args, **kwargs):
        started = time.perf_counter()
        logger.info("START %s", label)
        try:
            result = await original(*args, **kwargs)
            elapsed = time.perf_counter() - started
            logger.info("END %s elapsed=%.3fs", label, elapsed)
            return result
        except BaseException as exc:
            elapsed = time.perf_counter() - started
            logger.exception("FAIL %s elapsed=%.3fs error=%r", label, elapsed, exc)
            raise

    setattr(owner, method_name, logged_method)


class _ResumableAggregation:
    def __init__(self, cache: dict, aspects: list[str]):
        self.sources = cache.get("sources", [])
        self.conflicts = []
        self.stats = {}
        self.layered_content = {"analysis": {}}
        self.content_provenance = {}
        agent_contents = cache.get("agent_contents", {})
        for index, aspect in enumerate(aspects):
            agent_id = f"phase_2_agent_{index}"
            payload = agent_contents.get(agent_id, {})
            content = payload.get("content", "") if isinstance(payload, dict) else str(payload)
            section_id = f"section_{index}_{aspect}"
            section = {"id": section_id, "title": aspect, "content": content}
            self.layered_content["analysis"][agent_id] = section
            self.content_provenance[agent_id] = {
                "source_key": agent_id,
                "section_target": section_id,
            }


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_resume_real_report_generation_to_final_report():
    logger, log_path = _configure_generation_logging(RUN_ID)
    logger.info("TEST START run_id=%s", RUN_ID)
    cache_path = DATA_DIR / "results" / RUN_ID / "result.json"
    task_path = DATA_DIR / "tasks" / f"{RUN_ID}.json"
    checkpoint_dir = DATA_DIR / RUN_ID / "checkpoints"
    if not cache_path.exists() or not task_path.exists() or not checkpoint_dir.exists():
        details = (
            f"prerequisite_missing cache={cache_path.exists()} "
            f"task={task_path.exists()} checkpoints={checkpoint_dir.exists()}"
        )
        logger.error("E2E BLOCKED %s", details)
        pytest.fail(
            "Real report-resume E2E prerequisite_missing: "
            f"{details}. Set REAL_REPORT_E2E_RUN_ID to an available run."
        )

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    task = json.loads(task_path.read_text(encoding="utf-8"))
    # The persisted task input is a legacy truncated repr, so use the
    # authoritative framework recorded in the session archive/checkpoints.
    topic = "中国新能源汽车市场"
    aspects = [
        "市场规模与增长趋势", "主要品牌的竞争格局", "技术发展",
        "政策环境与补贴影响", "消费者偏好与购买行为", "产业链分析",
    ]

    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver, DataRepairAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

    from src.core.search import AnySearchProvider, LocalSkillProvider, SearchGateway, get_search_config
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.services.chart_planner import ChartPlannerAgent
    from src.services.chart_generator import ChartGenerator

    search_skill = MultiSearchSkill()
    web_scraper = WebScraperSkill()
    search_config = get_search_config()
    search_gateway = SearchGateway(
        task_id=RUN_ID,
        providers={
            "anysearch": AnySearchProvider(),
            "local": LocalSkillProvider(search_skill, name="local"),
        },
        primary_provider="anysearch",
        fallback_providers=["local"],
        task_max_searches=search_config.task_max_searches,
        default_scope_max_searches=search_config.default_scope_max_searches,
        scope_max_searches={"report_repair": 8, "conflict_resolver": 4},
        quality_threshold=40.0,
        max_provider_retries=1,
        max_provider_switches=1,
    )
    prompts = PromptManager()
    chart_output_dir = DATA_DIR / RUN_ID / "real_report_e2e" / "charts"
    chart_output_dir.mkdir(parents=True, exist_ok=True)
    orchestrator = ReportOrchestrator(
        chapter_writer=ChapterWriter(prompt_manager=prompts),
        chapter_reviewer=ChapterReviewAgent(prompt_manager=prompts),
        global_reviewer=GlobalReviewAgent(prompt_manager=prompts),
        data_repair_agent=DataRepairAgent(
            search_skill=search_skill,
            web_scraper_skill=web_scraper,
            search_gateway=search_gateway,
            prompt_manager=prompts,
        ),
        conflict_resolver=ConflictResolver(
            search_skill=search_skill,
            web_scraper_skill=web_scraper,
            search_gateway=search_gateway,
            prompt_manager=prompts,
        ),
        prompt_manager=prompts,
        search_gateway=search_gateway,
        search_skill=search_skill,
        web_scraper_skill=web_scraper,
        chart_planner=ChartPlannerAgent(search_gateway=search_gateway),
        chart_generator=ChartGenerator(output_dir=chart_output_dir),
    )
    logger.info("ORCHESTRATOR READY sections=%d checkpoint_dir=%s log=%s",
                len(aspects), checkpoint_dir, log_path)
    _instrument_async_method(search_gateway, "search", logger, "search_gateway.search")
    for method_name in ("write", "patch_data", "rewrite"):
        _instrument_async_method(
            orchestrator._chapter_writer, method_name, logger,
            f"chapter_writer.{method_name}",
        )
    _instrument_async_method(
        orchestrator._chapter_reviewer, "review", logger, "chapter_reviewer.review",
    )
    for method_name in ("review", "verify_issues"):
        _instrument_async_method(
            orchestrator._global_reviewer, method_name, logger,
            f"global_reviewer.{method_name}",
        )
    for method_name in ("_checkpoint_chapter", "_restore_from_checkpoint"):
        _instrument_async_method(
            orchestrator, method_name, logger, f"orchestrator.{method_name}",
        )

    task_structure = {
        "topic": topic,
        "sections": [
            {
                "section_id": f"section_{i}_{aspect}",
                "section_name": aspect,
                "section_role": "analysis",
                "content_dependency": [],
            }
            for i, aspect in enumerate(aspects)
        ],
    }
    framework_config = {"name": "行业研究报告", "content": {"min_section_length": 200}}
    logger.info("GENERATE START task_id=%s", RUN_ID)
    try:
        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=_ResumableAggregation(cache, aspects),
            topic=topic,
            task_id=RUN_ID,
        )
    except BaseException:
        logger.exception("GENERATE FAILED task_id=%s", RUN_ID)
        raise
    logger.info("GENERATE END sections=%d", len(result.get("sections", [])))

    assert result["topic"] == topic
    assert len(result.get("sections", [])) == len(aspects)
    assert all(section.get("content") for section in result["sections"])
    assert result.get("sources")
    assert "quality_report" in result or "global_review_score" in result

    # Verify the actual document-producing boundary as well.
    output_dir = DATA_DIR / RUN_ID / "real_report_e2e"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_out = output_dir / "research_result_cache.json"
    cache_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    from src.content.content_orchestrator import ContentOrchestrator
    from src.converters.html_to_word import HTMLToWordConverter
    from docx import Document

    html = ContentOrchestrator().transform_to_html(
        result, output_format="docx", output_dir=str(output_dir)
    )
    html_path = output_dir / "report_preview.html"
    html_path.write_text(html, encoding="utf-8")
    assert len(html) > 1000
    assert all(section["title"] in html for section in result["sections"])

    docx_path = output_dir / "final_report.docx"
    converted = HTMLToWordConverter().convert(html=html, output_path=str(docx_path))
    assert converted.success, converted.error
    assert docx_path.exists() and docx_path.stat().st_size > 1000
    document = Document(str(docx_path))
    assert len(document.paragraphs) > 0
    logger.info("TEST END SUCCESS sections=%d docx=%s bytes=%d",
                len(result["sections"]), docx_path, docx_path.stat().st_size)
