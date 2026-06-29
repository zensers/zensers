import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

cache_data = json.loads(Path("data/research_24c2875c/research_result_cache.json").read_text(encoding="utf-8"))

sections = cache_data.get("sections", [])
sources = cache_data.get("sources", [])

lines = []
lines.append(f"Topic: {cache_data.get('topic','')}")
lines.append(f"Aspects: {cache_data.get('aspects',[])}")
lines.append(f"Sections: {len(sections)}, Sources: {len(sources)}")
lines.append("")

for i, sec in enumerate(sections):
    sec_id = sec.get("id","")
    content = sec.get("content","")
    dp = sec.get("data_points", [])
    prov = sec.get("_provenance", {})

    lines.append(f"--- Section {i}: {sec_id} ---")
    lines.append(f"  content: {len(content)} chars")
    lines.append(f"  data_points: {len(dp)} items")
    if dp and isinstance(dp[0], dict):
        lines.append(f"  dp keys: {list(dp[0].keys())}")
    lines.append(f"  _provenance: {json.dumps(prov, ensure_ascii=False)[:200] if prov else 'none'}")

    # 模拟 AggregationResult 构建
    layered_content = {"analysis": {sec_id: content}}
    content_provenance = {sec_id: ContentProvenance(
        source_key=sec_id, stage="analysis", agent_type="analysis", section_target=sec_id,
    )}
    agg = AggregationResult(
        data={"topic": cache_data.get("topic","")},
        sources=[{"title": s.get("title",""), "url": s.get("url",""), "type": s.get("type","web")} for s in sources],
        layered_content=layered_content,
        content_provenance=content_provenance,
    )

    class FakeX: pass
    orch = ReportOrchestrator(
        llm_skill=FakeX(), chapter_writer=FakeX(), chapter_reviewer=FakeX(),
        global_reviewer=FakeX(), data_repair_agent=FakeX(), conflict_resolver=FakeX(),
        prompt_manager=FakeX(),
    )

    chapter_data, raw_summary = orch._extract_chapter_data(agg, sec_id, [])
    lines.append(f"  chapter_data keys: {list(chapter_data.keys()) if isinstance(chapter_data, dict) else type(chapter_data)}")
    lines.append(f"  chapter_data size: {len(json.dumps(chapter_data, ensure_ascii=False))} chars")
    lines.append(f"  raw_summary: {'有' if raw_summary else '无'} ({len(raw_summary)} chars)")
    lines.append("")

Path("data/byd_data_inspect.txt").write_text("\n".join(lines), encoding="utf-8")
