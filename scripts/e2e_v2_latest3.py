"""
端到端测试v2：最新数据(06-26) phase_X_agent_Y格式
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance


def build_from_cache(cache_data, max_sections=None):
    sections = cache_data.get("sections", [])
    sources = cache_data.get("sources", [])
    if max_sections:
        sections = sections[:max_sections]

    layered_content = {"analysis": {}}
    content_provenance = {}

    for sec in sections:
        sec_id = sec.get("id", "")
        content = sec.get("content", "")
        prov = sec.get("_provenance", {})

        matched_key = prov.get("matched_key", sec_id) if isinstance(prov, dict) else sec_id
        matched_stage = prov.get("matched_stage", "analysis") if isinstance(prov, dict) else "analysis"

        if isinstance(content, dict):
            content_str = json.dumps(content, ensure_ascii=False)
        elif isinstance(content, str):
            content_str = content
        else:
            content_str = str(content)

        if matched_stage not in layered_content:
            layered_content[matched_stage] = {}

        layered_content[matched_stage][matched_key] = content_str

        meta = {}
        if sec.get("data_points"):
            meta["data_points"] = sec["data_points"]
        if sec.get("charts"):
            meta["charts"] = sec["charts"]
        if sec.get("sources"):
            meta["sources"] = sec["sources"]
        if meta:
            layered_content[matched_stage][f"{matched_key}__meta"] = meta

        content_provenance[matched_key] = ContentProvenance(
            source_key=matched_key,
            stage=matched_stage,
            agent_type=matched_stage,
            section_target=sec_id,
        )

    section_sources = []
    seen_urls = set()
    for s in sources:
        url = s.get("url", s.get("href", ""))
        if url and url not in seen_urls:
            seen_urls.add(url)
            section_sources.append({
                "title": s.get("title", ""),
                "url": url,
                "type": s.get("type", "web"),
            })

    return AggregationResult(
        data={"topic": cache_data.get("topic", "")},
        sources=section_sources,
        layered_content=layered_content,
        content_provenance=content_provenance,
    ), sections


async def run():
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.skills.llm_skill import LLMSkill
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill

    cache_path = Path("data/research_233fdf0e/research_result_cache.json")
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    topic = cache_data.get("topic", "")

    max_sections = 3
    aspects = cache_data.get("aspects", [])[:max_sections]
    sections = cache_data.get("sections", [])[:max_sections]

    cache_subset = dict(cache_data)
    cache_subset["aspects"] = aspects
    cache_subset["sections"] = sections

    agg_result, _ = build_from_cache(cache_subset, max_sections=max_sections)

    task_structure = {
        "topic": topic,
        "sections": [
            {"section_id": sec["id"], "section_name": aspects[i] if i < len(aspects) else sec.get("title", sec["id"]), "section_role": "analysis", "content_dependency": []}
            for i, sec in enumerate(sections)
        ],
    }
    framework_config = {"name": f"{topic}分析", "agent_config": {}, "section_weights": {}}

    print(f"主题: {topic}")
    print(f"章节IDs: {[s['id'] for s in sections]}")
    print(f"来源: {len(agg_result.sources)}")
    print(f"layered_content keys: {list(agg_result.layered_content.get('analysis', {}).keys())}")

    llm = LLMSkill()
    search = MultiSearchSkill()
    scraper = WebScraperSkill()
    pm = PromptManager()

    writer = ChapterWriter(llm_skill=llm, prompt_manager=pm)
    reviewer = ChapterReviewAgent(llm_skill=llm, prompt_manager=pm)
    global_reviewer = GlobalReviewAgent(llm_skill=llm, prompt_manager=pm)
    data_repair = DataRepairAgent(search_skill=search, web_scraper_skill=scraper, llm_skill=llm, prompt_manager=pm)
    conflict_resolver = ConflictResolver(llm_skill=llm, search_skill=search, web_scraper_skill=scraper, prompt_manager=pm)

    orchestrator = ReportOrchestrator(
        llm_skill=llm, chapter_writer=writer, chapter_reviewer=reviewer,
        global_reviewer=global_reviewer, data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver, prompt_manager=pm,
    )

    start = time.time()
    try:
        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=agg_result,
            topic=topic,
        )
        elapsed = time.time() - start

        output = {
            "meta": {
                "topic": topic,
                "elapsed_seconds": round(elapsed, 1),
                "llm_calls": orchestrator._llm_call_count,
                "tokens_used": orchestrator._total_tokens_used,
                "output_sections": len(result["sections"]),
                "data_source": "Latest_0626",
                "max_sections": max_sections,
            },
            "report": result,
        }
        out_path = Path("data/e2e_v2_latest3_report.json")
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n耗时: {elapsed:.1f}s | LLM调用: {orchestrator._llm_call_count}次 | Tokens: {orchestrator._total_tokens_used}")
        print(f"输出章节: {len(result['sections'])}")

        for sec in result["sections"]:
            print(f"  [{sec.get('id','')}] {sec.get('title','')}: {len(sec.get('content',''))}字, {len(sec.get('data_points',[]))}数据点")

    except Exception as e:
        elapsed = time.time() - start
        print(f"失败: {elapsed:.1f}s | 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run())
