"""
Dry-run验证：不调用LLM，只验证数据构建和_extract_chapter_data是否正确提取。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


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


def dry_run(cache_path_str, max_sections, label):
    cache_data = json.loads(Path(cache_path_str).read_text(encoding="utf-8"))
    agg_result, sections = build_from_cache(cache_data, max_sections=max_sections)

    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"[{label}] {cache_data.get('topic','')}")
    lines.append(f"{'='*70}")
    lines.append(f"sections: {len(sections)}, sources: {len(agg_result.sources)}")
    lines.append(f"layered_content stages: {list(agg_result.layered_content.keys())}")
    for stage, items in agg_result.layered_content.items():
        lines.append(f"  {stage}: keys={list(items.keys())}")

    lines.append(f"\ncontent_provenance:")
    for key, prov in agg_result.content_provenance.items():
        lines.append(f"  {key} -> section_target={prov.section_target}, stage={prov.stage}")

    class FakeX: pass
    orch = ReportOrchestrator(
        llm_skill=FakeX(), chapter_writer=FakeX(), chapter_reviewer=FakeX(),
        global_reviewer=FakeX(), data_repair_agent=FakeX(), conflict_resolver=FakeX(),
        prompt_manager=FakeX(),
    )

    lines.append(f"\n_extract_chapter_data results:")
    for sec in sections:
        sec_id = sec.get("id", "")
        chapter_data, raw_summary = orch._extract_chapter_data(agg_result, sec_id, [])

        lines.append(f"\n  Section: {sec_id}")
        if isinstance(chapter_data, dict):
            lines.append(f"    chapter_data keys: {list(chapter_data.keys())}")
            content_val = chapter_data.get("content", "")
            lines.append(f"    content: {len(content_val)} chars")
            if content_val:
                lines.append(f"    content preview: {content_val[:100]}...")
        else:
            lines.append(f"    chapter_data type: {type(chapter_data)}")

        lines.append(f"    raw_summary: {'有' if raw_summary else '无'} ({len(raw_summary)} chars)")
        if raw_summary:
            lines.append(f"    raw_summary preview: {raw_summary[:200]}...")

        dp_count = len(sec.get("data_points", []))
        lines.append(f"    original data_points: {dp_count} items")

    return "\n".join(lines)


all_lines = []

result = dry_run(
    "data/research_24c2875c/research_result_cache.json",
    max_sections=8,
    label="BYD_8ch",
)
all_lines.append(result)

result = dry_run(
    "data/research_233fdf0e/research_result_cache.json",
    max_sections=3,
    label="Latest_3ch",
)
all_lines.append(result)

Path("data/dry_run_results.txt").write_text("\n\n".join(all_lines), encoding="utf-8")
print("Done. See data/dry_run_results.txt")
