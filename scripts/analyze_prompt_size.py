import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

cache_data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

sections = cache_data.get("sections", [])
sources = cache_data.get("sources", [])

layered_content = {}
content_provenance = {}
for sec in sections:
    agent_key = sec.get("id", "")
    layered_content["analysis"] = {}
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

lines = []
lines.append("=" * 60)
lines.append("Prompt数据体积分析")
lines.append("=" * 60)

for i, sec in enumerate(sections):
    sec_id = sec.get("id", "")
    chapter_data = orch._extract_chapter_data(agg, sec_id, [])
    cd_json = json.dumps(chapter_data, ensure_ascii=False, indent=2)
    cd_chars = len(cd_json)
    cd_tokens_est = cd_chars // 4

    content_len = len(sec.get("content", ""))
    dp_count = len(sec.get("data_points", []))
    dp_json = json.dumps(sec.get("data_points", []), ensure_ascii=False)
    dp_chars = len(dp_json)

    lines.append(f"\n章节 {i}: {sec.get('title', '')}")
    lines.append(f"  content: {content_len} chars (~{content_len//4} tokens)")
    lines.append(f"  data_points: {dp_count} items, {dp_chars} chars (~{dp_chars//4} tokens)")
    lines.append(f"  chapter_data总计: {cd_chars} chars (~{cd_tokens_est} tokens)")

all_sources_json = json.dumps(
    [{"title": s.get("title",""), "url": s.get("url",""), "type": s.get("type","web")} for s in sources],
    ensure_ascii=False, indent=2
)
lines.append(f"\n全部sources: {len(sources)} items, {len(all_sources_json)} chars (~{len(all_sources_json)//4} tokens)")

lines.append(f"\n{'=' * 60}")
lines.append("Prompt模板体积")
lines.append("=" * 60)

from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
pm = PromptManager()
for name in ["chapter_write", "chapter_review", "chapter_rewrite", "global_review", "exec_summary"]:
    try:
        tmpl_path = pm._prompts_dir / f"{name}.tmpl"
        tmpl_text = tmpl_path.read_text(encoding="utf-8")
        lines.append(f"  {name}.tmpl: {len(tmpl_text)} chars (~{len(tmpl_text)//4} tokens)")
    except:
        lines.append(f"  {name}.tmpl: not found")

lines.append(f"\n{'=' * 60}")
lines.append("单次chapter_write Prompt估算")
lines.append("=" * 60)

sec0 = sections[0]
cd0 = orch._extract_chapter_data(agg, sec0.get("id",""), [])
cd0_json = json.dumps(cd0, ensure_ascii=False, indent=2)
tmpl = (pm._prompts_dir / "chapter_write.tmpl").read_text(encoding="utf-8")

prompt_est = len(tmpl) + len(cd0_json) + 500
lines.append(f"  模板: {len(tmpl)} chars")
lines.append(f"  chapter_data: {len(cd0_json)} chars")
lines.append(f"  其他变量(~500 chars)")
lines.append(f"  估算prompt总长: {prompt_est} chars (~{prompt_est//4} tokens)")
lines.append(f"  加上max_tokens=8192输出")
lines.append(f"  单次调用估算: ~{(prompt_est//4) + 8192} tokens")

Path("data/prompt_size_analysis.txt").write_text("\n".join(lines), encoding="utf-8")
