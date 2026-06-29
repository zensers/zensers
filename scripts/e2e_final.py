"""
端到端测试：真实数据+真实LLM生成完整报告。
三层降级：精炼数据 → 原始数据摘要 → 搜索补全
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance


def build_from_cache(cache_data):
    sections = cache_data.get("sections", [])
    sources = cache_data.get("sources", [])

    layered_content = {"analysis": {}}
    content_provenance = {}

    for sec in sections:
        agent_key = sec.get("id", "")
        layered_content["analysis"][agent_key] = sec.get("content", "")

        meta = {}
        if sec.get("data_points"):
            meta["data_points"] = sec["data_points"]
        if meta:
            layered_content["analysis"][f"{agent_key}__meta"] = meta

        content_provenance[agent_key] = ContentProvenance(
            source_key=agent_key, stage="analysis", agent_type="analysis", section_target=agent_key,
        )

    section_sources = [{"title": s.get("title",""), "url": s.get("url",""), "type": s.get("type","web")} for s in sources]

    return AggregationResult(
        data={"topic": cache_data.get("topic", "")},
        sources=section_sources,
        layered_content=layered_content,
        content_provenance=content_provenance,
    )


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

    cache_path = Path("data/research_60f0e1ed/research_result_cache.json")
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))

    aspects = cache_data.get("aspects", [])[:3]
    sections = cache_data.get("sections", [])[:3]

    cache_data_subset = dict(cache_data)
    cache_data_subset["aspects"] = aspects
    cache_data_subset["sections"] = sections
    cache_data_subset["sources"] = [s for s in cache_data.get("sources", [])
                                     if any(s.get("agent_id","").startswith(f"section_{i}") for i in range(3))]

    agg_result = build_from_cache(cache_data_subset)

    task_structure = {
        "topic": cache_data["topic"],
        "sections": [
            {"section_id": f"section_{i}", "section_name": a, "section_role": "analysis", "content_dependency": []}
            for i, a in enumerate(aspects)
        ],
    }
    framework_config = {"name": f"{cache_data['topic']}分析", "agent_config": {}, "section_weights": {}}

    for key, prov in agg_result.content_provenance.items():
        for i, a in enumerate(aspects):
            if i < len(sections) and sections[i].get("id","") == key:
                prov.section_target = f"section_{i}"

    print(f"主题: {cache_data['topic']}")
    print(f"章节: {aspects}")
    print(f"来源: {len(cache_data_subset['sources'])}")

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
            task_structure=task_structure, framework_config=framework_config,
            aggregated_result=agg_result, topic=cache_data["topic"],
        )
        elapsed = time.time() - start

        output = {
            "meta": {
                "topic": cache_data["topic"],
                "elapsed_seconds": round(elapsed, 1),
                "llm_calls": orchestrator._llm_call_count,
                "tokens_used": orchestrator._total_tokens_used,
                "output_sections": len(result["sections"]),
            },
            "report": result,
        }
        out_path = Path("data/e2e_final_report.json")
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n耗时: {elapsed:.1f}s | LLM调用: {orchestrator._llm_call_count}次 | Tokens: {orchestrator._total_tokens_used}")
        print(f"输出章节: {len(result['sections'])}")

        evaluate(result, cache_data_subset, orchestrator)

        # 生成HTML报告
        print("\n正在生成HTML报告...")
        doc_agent = DocumentGenerationAgent(agent_id="doc_gen_e2e")
        preview_result = doc_agent.execute({
            "action": "produce_document",
            "task_id": f"e2e_{int(time.time())}",
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


def evaluate(result, cache_data, orchestrator):
    import re
    from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

    lines = []
    lines.append("=" * 70)
    lines.append("报告质量评估")
    lines.append("=" * 70)

    input_content = "\n".join(s.get("content","") for s in cache_data.get("sections",[]))
    input_numbers = set()
    for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个)', input_content):
        input_numbers.add((m.group(1), m.group(2)))

    total_chars = 0
    total_dps = 0
    vague_dps = 0
    ungrounded = []

    for sec in result["sections"]:
        content = sec.get("content","")
        total_chars += len(content)
        for dp in sec.get("data_points",[]):
            total_dps += 1
            if _is_vague_source(dp.get("source","")):
                vague_dps += 1
        for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个)', content):
            val, unit = m.group(1), m.group(2)
            if (val, unit) not in input_numbers:
                ungrounded.append({"section": sec["id"], "value": f"{val} {unit}",
                                   "ctx": content[max(0,m.start()-25):m.end()+25]})

    lines.append(f"\n1. 基本指标")
    lines.append(f"   输出章节: {len(result['sections'])}")
    lines.append(f"   总字数: {total_chars}")
    lines.append(f"   数据点: {total_dps} (模糊来源: {vague_dps})")

    lines.append(f"\n2. 数据锚定")
    lines.append(f"   输入数值: {len(input_numbers)} 个")
    lines.append(f"   未锚定数值: {len(ungrounded)} 个")
    if ungrounded:
        for u in ungrounded[:8]:
            lines.append(f"   - [{u['section']}] {u['value']}: ...{u['ctx']}...")

    lines.append(f"\n3. 章节详情")
    for sec in result["sections"]:
        lines.append(f"   [{sec['id']}] {sec['title']}: {len(sec.get('content',''))}字, "
                      f"{len(sec.get('data_points',[]))}数据点, {len(sec.get('sources',[]))}来源")

    kf = result.get("key_findings",[])
    lines.append(f"\n4. 关键发现: {len(kf)}条")
    for i, k in enumerate(kf[:3]):
        lines.append(f"   [{i+1}] {k[:120]}...")

    Path("data/e2e_final_eval.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n评估已保存到 data/e2e_final_eval.txt")


if __name__ == "__main__":
    asyncio.run(run())
