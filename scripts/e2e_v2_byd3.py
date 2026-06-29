"""
端到端测试v2：比亚迪3章节+真实LLM
验证近期真实数据（06-19比亚迪财务分析）的报告生成质量
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
    from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
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

    print(f"主题: {topic}")
    print(f"章节: {aspects}")
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
                "data_source": "BYD_0619",
                "max_sections": max_sections,
            },
            "report": result,
        }
        out_path = Path("data/e2e_v2_byd3_report.json")
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n耗时: {elapsed:.1f}s | LLM调用: {orchestrator._llm_call_count}次 | Tokens: {orchestrator._total_tokens_used}")
        print(f"输出章节: {len(result['sections'])}")

        evaluate(result, cache_subset, sections, orchestrator)

        print("\n正在生成HTML报告...")
        doc_agent = DocumentGenerationAgent(agent_id="doc_gen_byd3")
        preview_result = doc_agent.execute({
            "action": "produce_document",
            "task_id": f"e2e_byd3_{int(time.time())}",
            "output_format": "html",
            "research_result": result,
        })
        if preview_result.get("success"):
            html_path = preview_result.get("document_path", "")
            print(f"HTML报告: {html_path}")
        else:
            print(f"HTML生成失败: {preview_result.get('error','unknown')}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"失败: {elapsed:.1f}s | 错误: {e}")
        import traceback
        traceback.print_exc()


def evaluate(result, cache_data, sections, orchestrator):
    from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

    lines = []
    lines.append("=" * 70)
    lines.append("报告质量评估 - 比亚迪(06-19) 3章节")
    lines.append("=" * 70)

    input_content = "\n".join(s.get("content", "") for s in sections if isinstance(s.get("content"), str))
    input_numbers = set()
    for m in re.finditer(
        r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万|元)',
        input_content
    ):
        input_numbers.add((m.group(1), m.group(2)))

    total_chars = 0
    total_dps = 0
    vague_dps = 0
    ungrounded = []

    for sec in result.get("sections", []):
        content = sec.get("content", "")
        total_chars += len(content)
        for dp in sec.get("data_points", []):
            total_dps += 1
            if _is_vague_source(dp.get("source", "")):
                vague_dps += 1
        for m in re.finditer(
            r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万|元)',
            content
        ):
            val, unit = m.group(1), m.group(2)
            if (val, unit) not in input_numbers:
                ungrounded.append({
                    "section": sec.get("id", ""),
                    "value": f"{val} {unit}",
                    "ctx": content[max(0, m.start() - 25):m.end() + 25],
                })

    lines.append(f"\n1. 基本指标")
    lines.append(f"   输出章节: {len(result.get('sections', []))}")
    lines.append(f"   总字数: {total_chars}")
    lines.append(f"   数据点: {total_dps} (模糊来源: {vague_dps})")
    lines.append(f"   LLM调用: {orchestrator._llm_call_count}次")
    lines.append(f"   Tokens: {orchestrator._total_tokens_used}")

    lines.append(f"\n2. 数据锚定")
    lines.append(f"   输入数值: {len(input_numbers)} 个")
    lines.append(f"   未锚定数值: {len(ungrounded)} 个")
    if ungrounded:
        for u in ungrounded[:10]:
            lines.append(f"   - [{u['section']}] {u['value']}: ...{u['ctx']}...")

    lines.append(f"\n3. 章节详情")
    for sec in result.get("sections", []):
        lines.append(
            f"   [{sec.get('id', '')}] {sec.get('title', '')}: "
            f"{len(sec.get('content', ''))}字, "
            f"{len(sec.get('data_points', []))}数据点, "
            f"{len(sec.get('sources', []))}来源"
        )

    kf = result.get("key_findings", [])
    lines.append(f"\n4. 关键发现: {len(kf)}条")
    for i, k in enumerate(kf[:5]):
        lines.append(f"   [{i + 1}] {k[:150]}...")

    eval_path = Path("data/e2e_v2_byd3_eval.txt")
    eval_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n评估已保存到 {eval_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(run())
