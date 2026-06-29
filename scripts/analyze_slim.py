import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

cache_data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

sections = cache_data.get("sections", [])

layered_content = {"analysis": {}}
content_provenance = {}
for sec in sections:
    agent_key = sec.get("id", "")
    layered_content["analysis"][agent_key] = {
        "content": sec.get("content", ""),
        "title": sec.get("title", ""),
        "data_points": sec.get("data_points", []),
    }
    content_provenance[agent_key] = ContentProvenance(
        source_key=agent_key, stage="analysis", agent_type="analysis", section_target=agent_key,
    )

agg = AggregationResult(
    data={"topic": cache_data.get("topic", "")},
    sources=[],
    layered_content=layered_content,
    content_provenance=content_provenance,
)

class FakeX: pass
orch = ReportOrchestrator(
    llm_skill=FakeX(), chapter_writer=FakeX(), chapter_reviewer=FakeX(),
    global_reviewer=FakeX(), data_repair_agent=FakeX(), conflict_resolver=FakeX(),
    prompt_manager=FakeX(),
)

lines = []
for i, sec in enumerate(sections):
    sec_id = sec.get("id", "")
    raw_data = layered_content["analysis"].get(sec_id, {})
    raw_json = json.dumps(raw_data, ensure_ascii=False)
    raw_tokens = len(raw_json) // 4

    slim_data = orch._slim_chapter_data(raw_data)
    slim_json = json.dumps(slim_data, ensure_ascii=False)
    slim_tokens = len(slim_json) // 4

    lines.append(f"Chapter {i} ({sec.get('title','')[:30]}):")
    lines.append(f"  RAW: {len(raw_json)} chars (~{raw_tokens} tokens)")
    lines.append(f"  SLIM: {len(slim_json)} chars (~{slim_tokens} tokens)")
    lines.append(f"  压缩比: {slim_tokens/raw_tokens*100:.1f}%" if raw_tokens > 0 else "  N/A")
    lines.append("")

total_raw = sum(len(json.dumps(layered_content["analysis"].get(sec.get("id",""),{}), ensure_ascii=False)) for sec in sections)
total_slim = sum(len(json.dumps(orch._slim_chapter_data(layered_content["analysis"].get(sec.get("id",""),{})), ensure_ascii=False)) for sec in sections)
lines.append(f"TOTAL RAW: {total_raw} chars (~{total_raw//4} tokens)")
lines.append(f"TOTAL SLIM: {total_slim} chars (~{total_slim//4} tokens)")
lines.append(f"总压缩比: {total_slim/total_raw*100:.1f}%")

Path("data/slim_analysis.txt").write_text("\n".join(lines), encoding="utf-8")
