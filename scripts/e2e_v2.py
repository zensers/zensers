"""
端到端测试v2：用近期真实数据验证报告生成。
支持三种cache数据格式：
  A) 有content+data_points+_provenance（如比亚迪06-19）
  B) 有content但无data_points（如比亚迪06-25）
  C) phase_X_agent_Y格式，content为LLM分析文本（如06-26）
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


def build_task_structure(cache_data, sections):
    aspects = cache_data.get("aspects", [])
    task_sections = []
    for i, sec in enumerate(sections):
        sec_id = sec.get("id", "")
        aspect_name = aspects[i] if i < len(aspects) else sec.get("title", sec_id)
        task_sections.append({
            "section_id": sec_id,
            "section_name": aspect_name,
            "section_role": "analysis",
            "content_dependency": [],
        })
    return {
        "topic": cache_data.get("topic", ""),
        "sections": task_sections,
    }


def evaluate(result, cache_data, sections, orchestrator):
    from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

    lines = []
    lines.append("=" * 70)
    lines.append("报告质量评估")
    lines.append("=" * 70)

    input_content = "\n".join(s.get("content", "") for s in sections if isinstance(s.get("content"), str))
    input_numbers = set()
    for m in re.finditer(
        r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万)',
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
            r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万)',
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

    return "\n".join(lines)


async def run_single(cache_path_str, max_sections=None, label=""):
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.skills.llm_skill import LLMSkill
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill

    cache_path = Path(cache_path_str)
    if not cache_path.exists():
        print(f"[{label}] Cache not found: {cache_path}")
        return

    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    topic = cache_data.get("topic", "unknown")

    agg_result, sections = build_from_cache(cache_data, max_sections=max_sections)
    task_structure = build_task_structure(cache_data, sections)
    framework_config = {
        "name": f"{topic}分析",
        "agent_config": {},
        "section_weights": {},
    }

    print(f"\n{'='*60}")
    print(f"[{label}] 主题: {topic}")
    print(f"  章节数: {len(sections)}")
    print(f"  来源数: {len(cache_data.get('sources', []))}")
    print(f"  layered_content stages: {list(agg_result.layered_content.keys())}")
    for stage, items in agg_result.layered_content.items():
        print(f"    {stage}: {list(items.keys())[:5]}...")
    print(f"  content_provenance keys: {list(agg_result.content_provenance.keys())[:5]}...")

    for key, prov in agg_result.content_provenance.items():
        print(f"    {key} -> section_target={prov.section_target}")

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

        eval_text = evaluate(result, cache_data, sections, orchestrator)

        safe_label = label.replace(" ", "_").replace("/", "_")
        out_path = Path(f"data/e2e_v2_{safe_label}_report.json")
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        eval_path = Path(f"data/e2e_v2_{safe_label}_eval.txt")
        eval_path.write_text(eval_text, encoding="utf-8")

        print(f"\n耗时: {elapsed:.1f}s | LLM调用: {orchestrator._llm_call_count}次 | Tokens: {orchestrator._total_tokens_used}")
        print(eval_text)

        return result

    except Exception as e:
        elapsed = time.time() - start
        print(f"失败: {elapsed:.1f}s | 错误: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    test_cases = [
        {
            "label": "BYD_8ch",
            "cache": "data/research_24c2875c/research_result_cache.json",
            "max_sections": 8,
            "desc": "比亚迪财务分析(06-19) - 8章节完整数据",
        },
        {
            "label": "Latest_5ch",
            "cache": "data/research_233fdf0e/research_result_cache.json",
            "max_sections": 3,
            "desc": "测试主题(06-26) - phase_X_agent_Y格式",
        },
    ]

    print("端到端测试v2 - 近期真实数据验证")
    print("=" * 60)

    for tc in test_cases:
        print(f"\n>>> {tc['desc']}")
        result = await run_single(tc["cache"], max_sections=tc["max_sections"], label=tc["label"])
        if result:
            print(f"  成功: {len(result.get('sections', []))}章节")
        else:
            print(f"  失败")


if __name__ == "__main__":
    asyncio.run(main())
