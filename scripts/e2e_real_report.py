"""
端到端测试：使用真实数据+真实LLM生成完整报告，并评估质量。

使用方式：python -m scripts.e2e_real_report
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance


def build_aggregation_result_from_cache(cache_data: Dict[str, Any]) -> AggregationResult:
    sections = cache_data.get("sections", [])
    sources = cache_data.get("sources", [])

    layered_content = {"analysis": {}}
    content_provenance = {}

    for sec in sections:
        sec_id = sec.get("id", "")
        sec_title = sec.get("title", "")
        content = sec.get("content", "")
        data_points = sec.get("data_points", [])

        agent_key = sec_id

        layered_content["analysis"][agent_key] = {
            "content": content,
            "title": sec_title,
            "data_points": data_points,
        }

        content_provenance[agent_key] = ContentProvenance(
            source_key=agent_key,
            stage=stage,
            agent_type="analysis",
            section_target=sec_id,
        )

    section_sources = []
    for src in sources:
        section_sources.append({
            "title": src.get("title", ""),
            "url": src.get("url", ""),
            "type": src.get("type", "web"),
            "agent_id": src.get("agent_id", ""),
        })

    return AggregationResult(
        data={"topic": cache_data.get("topic", "")},
        conflicts=[],
        stats={"section_count": len(sections), "source_count": len(sources)},
        sources=section_sources,
        layered_content=layered_content,
        content_provenance=content_provenance,
    )


def build_task_structure(cache_data: Dict[str, Any]) -> Dict[str, Any]:
    sections = []
    aspects = cache_data.get("aspects", [])
    for i, aspect in enumerate(aspects):
        sec_id = f"section_{i}"
        sections.append({
            "section_id": sec_id,
            "section_name": aspect,
            "section_role": "analysis",
            "content_dependency": [],
        })
    return {
        "topic": cache_data.get("topic", ""),
        "sections": sections,
    }


def build_framework_config(cache_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": f"{cache_data.get('topic', '研究')} 深度分析",
        "description": cache_data.get("topic", ""),
        "agent_config": {},
        "section_weights": {},
    }


def remap_provenance_to_task_structure(
    agg_result: AggregationResult,
    cache_data: Dict[str, Any],
    task_structure: Dict[str, Any],
) -> AggregationResult:
    aspects = cache_data.get("aspects", [])
    sections = cache_data.get("sections", [])
    new_provenance = {}

    for i, aspect in enumerate(aspects):
        sec_id = task_structure["sections"][i]["section_id"]
        if i < len(sections):
            original_key = sections[i].get("id", "")
            if original_key in agg_result.content_provenance:
                prov = agg_result.content_provenance[original_key]
                new_provenance[original_key] = ContentProvenance(
                    source_key=prov.source_key,
                    stage=prov.stage,
                    agent_type=prov.agent_type,
                    section_target=sec_id,
                )

    agg_result.content_provenance = new_provenance
    return agg_result


async def run_e2e():
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.skills.llm_skill import LLMSkill
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill

    cache_path = Path("data/research_60f0e1ed/research_result_cache.json")
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))

    cache_data["aspects"] = cache_data["aspects"][:3]
    cache_data["sections"] = cache_data["sections"][:3]
    cache_data["sources"] = [s for s in cache_data["sources"] if s.get("agent_id", "").startswith(
        tuple(f"section_{i}" for i in range(3))
    )]

    print("=" * 60)
    print(f"端到端测试：{cache_data['topic']}")
    print(f"章节数: {len(cache_data.get('sections', []))}")
    print(f"来源数: {len(cache_data.get('sources', []))}")
    print("=" * 60)

    agg_result = build_aggregation_result_from_cache(cache_data)
    task_structure = build_task_structure(cache_data)
    framework_config = build_framework_config(cache_data)
    agg_result = remap_provenance_to_task_structure(agg_result, cache_data, task_structure)

    print(f"\nlayered_content stages: {list(agg_result.layered_content.keys())}")
    print(f"content_provenance keys: {list(agg_result.content_provenance.keys())}")
    for key, prov in agg_result.content_provenance.items():
        print(f"  {key} -> section_target={prov.section_target}")

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
        llm_skill=llm,
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver,
        prompt_manager=pm,
    )

    start = time.time()
    try:
        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=agg_result,
            topic=cache_data["topic"],
        )
        elapsed = time.time() - start

        print(f"\n{'=' * 60}")
        print(f"报告生成完成！耗时: {elapsed:.1f}s")
        print(f"{'=' * 60}")

        output = {
            "meta": {
                "topic": cache_data["topic"],
                "elapsed_seconds": round(elapsed, 1),
                "input_sections": len(cache_data.get("sections", [])),
                "input_sources": len(cache_data.get("sources", [])),
                "output_sections": len(result["sections"]),
            },
            "report": result,
        }

        out_path = Path("data/e2e_real_report.json")
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"完整报告已保存到: {out_path}")

        evaluate_report(result, cache_data)

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n报告生成失败！耗时: {elapsed:.1f}s")
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


def evaluate_report(result: Dict[str, Any], cache_data: Dict[str, Any]):
    print(f"\n{'=' * 60}")
    print("报告质量评估")
    print(f"{'=' * 60}")

    input_content = "\n".join(s.get("content", "") for s in cache_data.get("sections", []))
    input_numbers = set()
    import re
    for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|亿美元|美元|台|万辆)', input_content):
        input_numbers.add(m.group(1))

    total_content = 0
    total_data_points = 0
    total_sourced_data_points = 0
    vague_data_points = 0
    ungrounded_numbers = []

    for sec in result["sections"]:
        content = sec.get("content", "")
        total_content += len(content)
        dps = sec.get("data_points", [])
        total_data_points += len(dps)
        for dp in dps:
            src = dp.get("source", "")
            if src and src.strip():
                total_sourced_data_points += 1
            from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source
            if _is_vague_source(src):
                vague_data_points += 1

        for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|亿美元|美元|台|万辆)', content):
            val = m.group(1)
            if val not in input_numbers:
                ungrounded_numbers.append({"section": sec["id"], "value": val, "unit": m.group(2), "context": content[max(0, m.start()-30):m.end()+30]})

    print(f"\n1. 基本指标")
    print(f"   输入章节数: {len(cache_data.get('sections', []))}")
    print(f"   输出章节数: {len(result['sections'])}")
    print(f"   总内容字数: {total_content}")
    print(f"   数据点总数: {total_data_points}")
    print(f"   有来源数据点: {total_sourced_data_points}")
    print(f"   模糊来源数据点: {vague_data_points}")

    print(f"\n2. 数据锚定度")
    print(f"   输入数据中的数值: {len(input_numbers)} 个")
    print(f"   输出中未在输入出现的数值: {len(ungrounded_numbers)} 个")
    if ungrounded_numbers:
        print(f"   未锚定数值详情:")
        for un in ungrounded_numbers[:10]:
            print(f"     - [{un['section']}] {un['value']} {un['unit']}: ...{un['context']}...")

    print(f"\n3. 数据来源覆盖率")
    if total_data_points > 0:
        sourced_pct = total_sourced_data_points / total_data_points * 100
        vague_pct = vague_data_points / total_data_points * 100
        print(f"   有来源标注: {sourced_pct:.1f}%")
        print(f"   模糊来源: {vague_pct:.1f}%")
    else:
        print(f"   无数据点")

    print(f"\n4. 章节详情")
    for sec in result["sections"]:
        content = sec.get("content", "")
        dps = sec.get("data_points", [])
        sec_srcs = sec.get("sources", [])
        print(f"   [{sec['id']}] {sec['title']}")
        print(f"     字数: {len(content)}, 数据点: {len(dps)}, 来源: {len(sec_srcs)}")

    key_findings = result.get("key_findings", [])
    print(f"\n5. 关键发现")
    print(f"   条目数: {len(key_findings)}")
    for i, kf in enumerate(key_findings[:3]):
        print(f"   [{i+1}] {kf[:100]}...")

    output_path = Path("data/e2e_evaluation.json")
    eval_result = {
        "total_content_chars": total_content,
        "total_data_points": total_data_points,
        "sourced_data_points": total_sourced_data_points,
        "vague_data_points": vague_data_points,
        "ungrounded_numbers_count": len(ungrounded_numbers),
        "ungrounded_numbers": ungrounded_numbers[:20],
        "input_numbers_count": len(input_numbers),
    }
    output_path.write_text(json.dumps(eval_result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评估结果已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(run_e2e())
