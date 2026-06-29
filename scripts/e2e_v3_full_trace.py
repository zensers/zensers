"""
完整端到端测试v3：分步追踪每个环节的输出质量。
验证 write → review → rewrite → global_review → phase4 → exec_summary → assemble 全流程。
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteInput, ChapterWriteOutput, ChapterReviewInput,
    ReviewInput, DataPoint,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import (
    ReportOrchestrator, RetryPolicy, _is_vague_source,
)
from src.agents.fixed_agents.report_upgrade.global_reviewer import serialize_report_for_review


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


def assess_chapter(chapter, label=""):
    content = chapter.content
    dps = chapter.data_points_used
    vague = count_vague_sources([asdict(dp) for dp in dps])
    return {
        "label": label,
        "chars": len(content),
        "data_points": len(dps),
        "vague_sources": vague,
        "key_conclusions": len(chapter.key_conclusions),
        "numeric_mentions": count_data_metrics(content),
        "self_check_passed": chapter.self_check_passed,
        "self_check_issues": chapter.self_check_issues,
    }


from dataclasses import asdict


async def run():
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
    from src.skills.llm_skill import LLMSkill
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill

    cache_path = Path("data/research_24c2875c/research_result_cache.json")
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

    llm = LLMSkill()
    search = MultiSearchSkill()
    scraper = WebScraperSkill()
    pm = PromptManager()

    writer = ChapterWriter(llm_skill=llm, prompt_manager=pm)
    reviewer = ChapterReviewAgent(llm_skill=llm, prompt_manager=pm)
    global_reviewer = GlobalReviewAgent(llm_skill=llm, prompt_manager=pm)
    data_repair = DataRepairAgent(search_skill=search, web_scraper_skill=scraper, llm_skill=llm, prompt_manager=pm)
    conflict_resolver = ConflictResolver(llm_skill=llm, search_skill=search, web_scraper_skill=scraper, prompt_manager=pm)

    data_registry = DataRegistry()
    preceding_summary = ""

    log = []
    log.append(f"主题: {topic}")
    log.append(f"章节: {aspects}")
    log.append(f"来源: {len(agg_result.sources)}")

    # ========== Step 1: Write each chapter ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 1: Chapter Write")
    log.append(f"{'='*60}")

    chapters_after_write = []
    t0 = time.time()

    for i, section_spec in enumerate(task_structure["sections"]):
        section_id = section_spec["section_id"]
        chapter_data, raw_data_summary = ReportOrchestrator._extract_chapter_data(
            agg_result, section_id, section_spec.get("content_dependency", []),
        )

        log.append(f"\n  [{section_id}] 提取数据: chapter_data={len(json.dumps(chapter_data, ensure_ascii=False))}chars, raw_summary={len(raw_data_summary)}chars")

        chapter = await writer.write(ChapterWriteInput(
            framework_config=framework_config,
            task_structure=task_structure,
            chapter_spec=section_spec,
            chapter_data=chapter_data,
            raw_data_summary=raw_data_summary,
            preceding_summary=preceding_summary,
            used_metrics_summary=data_registry.serialize_used_metrics(),
        ))

        validated_dps = ReportOrchestrator._extract_and_validate_data_points(chapter)
        for dp in validated_dps:
            data_registry.register(
                metric=dp.metric, value=dp.value, unit=dp.unit,
                chapter_id=chapter.chapter_id, source=dp.source,
            )

        metrics = assess_chapter(chapter, "write")
        log.append(f"  WRITE结果: {metrics['chars']}字, {metrics['data_points']}数据点, {metrics['vague_sources']}模糊来源, {metrics['numeric_mentions']}数值, self_check={'PASS' if metrics['self_check_passed'] else 'FAIL'}")
        if metrics['self_check_issues']:
            log.append(f"    self_check_issues: {metrics['self_check_issues']}")

        chapters_after_write.append((chapter, section_spec, chapter_data, raw_data_summary))
        preceding_summary += f"\n【{chapter.title}】{'; '.join(str(c) for c in chapter.key_conclusions)}"

    log.append(f"\n  Write总耗时: {time.time()-t0:.1f}s")

    # ========== Step 2: Review each chapter ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 2: Chapter Review")
    log.append(f"{'='*60}")

    chapters_after_review = []
    t0 = time.time()

    for chapter, section_spec, chapter_data, raw_data_summary in chapters_after_write:
        section_id = chapter.chapter_id

        review = await reviewer.review(ChapterReviewInput(
            framework_config=framework_config,
            chapter_spec=section_spec,
            chapter_content=chapter.content,
            preceding_summary=preceding_summary,
            used_metrics_summary=data_registry.serialize_used_metrics(),
            topic=topic,
            writer_self_check_issues=chapter.self_check_issues,
            chapter_data=chapter_data,
        ))

        log.append(f"\n  [{section_id}] Review: score={review.score:.1f}, passed={review.passed}, issues={len(review.issues)}")
        for iss in review.issues[:3]:
            log.append(f"    [{iss.severity}] {iss.category}: {iss.description[:80]}")

        chapters_after_review.append((chapter, review, section_spec, chapter_data, raw_data_summary))

    log.append(f"\n  Review总耗时: {time.time()-t0:.1f}s")

    # ========== Step 3: Rewrite chapters that failed review ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 3: Chapter Rewrite (score < 60)")
    log.append(f"{'='*60}")

    chapters_final = []
    t0 = time.time()
    rewrite_count = 0

    for chapter, review, section_spec, chapter_data, raw_data_summary in chapters_after_review:
        section_id = chapter.chapter_id

        if review.passed or review.score >= RetryPolicy.MIN_REVIEW_SCORE_TO_ACCEPT:
            log.append(f"\n  [{section_id}] Review PASSED (score={review.score:.1f}), 无需rewrite")
            chapters_final.append(chapter)
            continue

        log.append(f"\n  [{section_id}] Review FAILED (score={review.score:.1f}), 执行rewrite...")

        before_metrics = assess_chapter(chapter, "before_rewrite")

        rewritten = await writer.rewrite(
            original_chapter=chapter,
            review_feedback=review,
            framework_config=framework_config,
            chapter_spec=section_spec,
            preceding_summary=preceding_summary,
            chapter_data=chapter_data,
        )

        after_metrics = assess_chapter(rewritten, "after_rewrite")
        rewrite_count += 1

        log.append(f"  REWRITE前: {before_metrics['chars']}字, {before_metrics['data_points']}数据点, {before_metrics['numeric_mentions']}数值")
        log.append(f"  REWRITE后: {after_metrics['chars']}字, {after_metrics['data_points']}数据点, {after_metrics['numeric_mentions']}数值")
        log.append(f"  变化: 字数{'+' if after_metrics['chars']>=before_metrics['chars'] else ''}{after_metrics['chars']-before_metrics['chars']}, 数据点{'+' if after_metrics['data_points']>=before_metrics['data_points'] else ''}{after_metrics['data_points']-before_metrics['data_points']}")

        # rewrite后再review一次
        re_review = await reviewer.review(ChapterReviewInput(
            framework_config=framework_config,
            chapter_spec=section_spec,
            chapter_content=rewritten.content,
            preceding_summary=preceding_summary,
            used_metrics_summary=data_registry.serialize_used_metrics(),
            topic=topic,
            writer_self_check_issues=rewritten.self_check_issues,
            chapter_data=chapter_data,
        ))
        log.append(f"  REWRITE后Review: score={re_review.score:.1f}, passed={re_review.passed} (原score={review.score:.1f})")

        chapters_final.append(rewritten)

    log.append(f"\n  Rewrite总耗时: {time.time()-t0:.1f}s, 共{rewrite_count}次rewrite")

    # ========== Step 4: Global Review ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 4: Global Review")
    log.append(f"{'='*60}")

    t0 = time.time()
    report_summary = serialize_report_for_review(chapters_final, data_registry)
    conflicts_summary = data_registry.serialize_conflicts()

    global_review = await global_reviewer.review(ReviewInput(
        framework_config=framework_config,
        report_summary=report_summary,
        conflicts_summary=conflicts_summary,
    ))

    log.append(f"  Global Review: overall_score={global_review.overall_score:.1f}")
    log.append(f"  dimension_scores: {json.dumps(global_review.dimension_scores, ensure_ascii=False)}")
    log.append(f"  issues: {len(global_review.issues)}")
    for iss in global_review.issues[:5]:
        log.append(f"    [{iss.severity}] {iss.dimension}: {iss.description[:100]}")
    log.append(f"  fix_suggestions: {len(global_review.fix_suggestions)}")

    log.append(f"\n  Global Review耗时: {time.time()-t0:.1f}s")

    # ========== Step 5: Verify Issues ==========
    if global_review.issues:
        log.append(f"\n{'='*60}")
        log.append("STEP 5: Verify Issues")
        log.append(f"{'='*60}")

        t0 = time.time()
        verified = await global_reviewer.verify_issues(global_review.issues, chapters_final)
        log.append(f"  原始issues: {len(global_review.issues)}, 验证后: {len(verified)}")
        for iss in verified[:3]:
            log.append(f"    [{iss.severity}] {iss.dimension}: {iss.description[:80]}")
        log.append(f"  Verify耗时: {time.time()-t0:.1f}s")

    # ========== Step 6: Phase4 Fix (if score < 80) ==========
    if global_review.overall_score < 80:
        log.append(f"\n{'='*60}")
        log.append(f"STEP 6: Phase4 Fix & Optimize (score={global_review.overall_score:.1f} < 80)")
        log.append(f"{'='*60}")

        t0 = time.time()
        orch = ReportOrchestrator(
            llm_skill=llm, chapter_writer=writer, chapter_reviewer=reviewer,
            global_reviewer=global_reviewer, data_repair_agent=data_repair,
            conflict_resolver=conflict_resolver, prompt_manager=pm,
        )
        orch._data_registry = data_registry
        orch._task_structure = task_structure
        orch._aggregated_result = agg_result

        fixed_chapters = await orch._phase4_fix_and_optimize(
            chapters_final, global_review, framework_config, topic,
        )

        for i, ch in enumerate(fixed_chapters):
            m = assess_chapter(ch, "phase4")
            log.append(f"  [{ch.chapter_id}] Phase4后: {m['chars']}字, {m['data_points']}数据点")

        chapters_final = fixed_chapters
        log.append(f"  Phase4耗时: {time.time()-t0:.1f}s")
    else:
        log.append(f"\n  STEP 6: 跳过 (global_score={global_review.overall_score:.1f} >= 80)")

    # ========== Step 7: Exec Summary ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 7: Exec Summary")
    log.append(f"{'='*60}")

    t0 = time.time()
    orch2 = ReportOrchestrator(
        llm_skill=llm, chapter_writer=writer, chapter_reviewer=reviewer,
        global_reviewer=global_reviewer, data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver, prompt_manager=pm,
    )
    orch2._data_registry = data_registry
    exec_summary = await orch2._generate_exec_summary(chapters_final, task_structure, topic)
    log.append(f"  执行摘要: {len(exec_summary)}字")
    log.append(f"  摘要前200字: {exec_summary[:200]}...")
    log.append(f"  Exec Summary耗时: {time.time()-t0:.1f}s")

    # ========== Step 8: Assemble Final Report ==========
    log.append(f"\n{'='*60}")
    log.append("STEP 8: Assemble Final Report")
    log.append(f"{'='*60}")

    original_sources = getattr(agg_result, 'sources', [])
    final_report = ReportOrchestrator._assemble_final_report(
        chapters_final, exec_summary, global_review, topic, original_sources,
    )

    total_chars = sum(len(s.get("content","")) for s in final_report["sections"])
    total_dps = sum(len(s.get("data_points",[])) for s in final_report["sections"])
    total_vague = sum(
        sum(1 for dp in s.get("data_points",[]) if _is_vague_source(str(dp.get("source",""))))
        for s in final_report["sections"]
    )
    kf = final_report.get("key_findings", [])

    log.append(f"  最终报告: {len(final_report['sections'])}章节, {total_chars}字, {total_dps}数据点, {total_vague}模糊来源")
    log.append(f"  关键发现: {len(kf)}条")
    for i, k in enumerate(kf):
        log.append(f"    [{i+1}] {k[:150]}")

    # ========== Summary ==========
    log.append(f"\n{'='*60}")
    log.append("QUALITY SUMMARY")
    log.append(f"{'='*60}")

    for i, ch in enumerate(chapters_final):
        m = assess_chapter(ch)
        log.append(f"  [{ch.chapter_id}] {ch.title}: {m['chars']}字, {m['data_points']}dp, {m['vague_sources']}模糊, {m['numeric_mentions']}数值")

    log.append(f"\n  全局评分: {global_review.overall_score:.1f}")
    log.append(f"  Rewrite次数: {rewrite_count}")
    log.append(f"  Phase4触发: {'是' if global_review.overall_score < 80 else '否'}")

    output = "\n".join(log)
    Path("data/e2e_v3_full_trace.txt").write_text(output, encoding="utf-8")

    final_report_path = Path("data/e2e_v3_report.json")
    final_report_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(output)


if __name__ == "__main__":
    asyncio.run(run())
