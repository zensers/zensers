"""
端到端测试v4：完整调用 generate_report，验证质量收敛6个改动点的效果。
与v3对比：收敛循环(3轮) + StructuredDataRepairAgent + L1/L2/L3分类 + 搜索关键词双语优化。
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.orchestrator import (
    ReportOrchestrator, RetryPolicy, _is_vague_source,
)


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


def count_data_metrics(content):
    pattern = re.compile(
        r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万|元)',
        re.IGNORECASE,
    )
    return len(pattern.findall(content))


def count_vague_sources(data_points):
    return sum(1 for dp in data_points if _is_vague_source(str(dp.get("source", ""))))


async def run():
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.registry import SkillRegistry

    log = []

    cache_path = Path("data/research_24c2875c/research_result_cache.json")
    if not cache_path.exists():
        print(f"Cache not found: {cache_path}")
        return
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    topic = cache_data.get("topic", "")

    max_sections = 3
    aspects = cache_data.get("aspects", [])[:max_sections]
    sections = cache_data.get("sections", [])[:max_sections]

    cache_subset = dict(cache_data)
    cache_subset["aspects"] = aspects
    cache_subset["sections"] = sections
    cache_subset["sources"] = cache_data.get("sources", [])

    agg_result, _ = build_from_cache(cache_subset, max_sections=max_sections)

    task_structure = {
        "topic": topic,
        "sections": [
            {"section_id": sec["id"], "section_name": aspects[i] if i < len(aspects) else sec.get("title", sec["id"]), "section_role": "analysis", "content_dependency": []}
            for i, sec in enumerate(sections)
        ],
    }
    framework_config = {"name": f"{topic}分析", "agent_config": {}, "section_weights": {}}

    search = MultiSearchSkill()
    scraper = WebScraperSkill()
    pm = PromptManager()

    writer = ChapterWriter(llm_skill=None, prompt_manager=pm)
    reviewer = ChapterReviewAgent(llm_skill=None, prompt_manager=pm)
    global_reviewer = GlobalReviewAgent(llm_skill=None, prompt_manager=pm)
    data_repair = DataRepairAgent(search_skill=search, web_scraper_skill=scraper, llm_skill=None, prompt_manager=pm)
    conflict_resolver = ConflictResolver(llm_skill=None, search_skill=search, web_scraper_skill=scraper, prompt_manager=pm)

    skill_registry = SkillRegistry()
    skill_registry.register_core_skills()
    try:
        from src.skills.analysis import StockDataSkill
        skill_registry.register_factory("stock_data", StockDataSkill)
    except Exception:
        pass

    log.append(f"e2e v4: 质量收敛完整测试")
    log.append(f"主题: {topic}")
    log.append(f"章节: {aspects}")
    log.append(f"来源: {len(agg_result.sources)}")
    log.append(f"skill_registry: stock_data={'YES' if skill_registry.get('stock_data') else 'NO'}, knowledge_query={'YES' if skill_registry.get('knowledge_query') else 'NO'}")

    orch = ReportOrchestrator(
        llm_skill=None,
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver,
        prompt_manager=pm,
        skill_registry=skill_registry,
    )

    t_start = time.time()

    result = await orch.generate_report(
        task_structure=task_structure,
        framework_config=framework_config,
        aggregated_result=agg_result,
        topic=topic,
    )

    elapsed = time.time() - t_start

    log.append(f"\n总耗时: {elapsed:.1f}s")
    log.append(f"LLM调用次数: {orch._llm_call_count}")
    log.append(f"LLM令牌消耗: {orch._total_tokens_used}")

    quality_report = result.get("quality_report")
    if quality_report:
        log.append(f"\n{'='*60}")
        log.append("QUALITY CONVERGENCE REPORT")
        log.append(f"{'='*60}")
        log.append(f"  overall_score: {quality_report['overall_score']}")
        log.append(f"  target_score: {quality_report['target_score']}")
        log.append(f"  convergence_rounds: {quality_report['convergence_rounds']}")
        log.append(f"  converged: {quality_report['converged']}")
        for cd in quality_report.get("chapter_diagnostics", []):
            log.append(f"  chapter: {cd['chapter_id']}, score={cd['score']}, layer={cd['source_layer']}")
            if cd.get("gaps"):
                log.append(f"    gaps: {cd['gaps']}")
            if cd.get("remediations"):
                log.append(f"    remediations: {cd['remediations']}")

    log.append(f"\n{'='*60}")
    log.append("FINAL REPORT SUMMARY")
    log.append(f"{'='*60}")

    total_chars = sum(len(s.get("content", "")) for s in result["sections"])
    total_dps = sum(len(s.get("data_points", [])) for s in result["sections"])
    total_vague = sum(
        sum(1 for dp in s.get("data_points", []) if _is_vague_source(str(dp.get("source", ""))))
        for s in result["sections"]
    )
    kf = result.get("key_findings", [])

    for sec in result["sections"]:
        sec_dps = len(sec.get("data_points", []))
        sec_vague = sum(1 for dp in sec.get("data_points", []) if _is_vague_source(str(dp.get("source", ""))))
        sec_numerics = count_data_metrics(sec.get("content", ""))
        log.append(f"  [{sec['id']}] {sec['title']}: {len(sec.get('content', ''))}字, {sec_dps}dp, {sec_vague}模糊, {sec_numerics}数值")

    log.append(f"\n  总计: {total_chars}字, {total_dps}数据点, {total_vague}模糊来源")
    log.append(f"  关键发现: {len(kf)}条")

    llm_trace = result.get("llm_trace", [])
    if llm_trace:
        phase_counts = {}
        for entry in llm_trace:
            phase = entry.get("phase", "unknown")
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
        log.append(f"\n  LLM调用分布: {phase_counts}")

    output = "\n".join(log)
    Path("data/e2e_v4_convergence_trace.txt").write_text(output, encoding="utf-8")
    Path("data/e2e_v4_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print(output)
    print(f"\n结果已保存到 data/e2e_v4_convergence_trace.txt 和 data/e2e_v4_report.json")


if __name__ == "__main__":
    asyncio.run(run())
