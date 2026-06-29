import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator.aggregation.result_aggregator import AggregationResult, ContentProvenance

cache_data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

aspects = cache_data.get("aspects", [])
sections = cache_data.get("sections", [])

print("Aspects:", aspects)
print("Sections:")
for i, s in enumerate(sections):
    print(f"  {i}: id={s['id']}, title={s['title']}")

layered_content = {}
content_provenance = {}

for sec in sections:
    agent_key = sec.get("id", "")
    stage = "analysis"
    layered_content[stage] = {}
    layered_content[stage][agent_key] = {
        "content": sec.get("content", ""),
        "title": sec.get("title", ""),
        "data_points": sec.get("data_points", []),
    }
    content_provenance[agent_key] = ContentProvenance(
        source_key=agent_key,
        stage=stage,
        agent_type="analysis",
        section_target=agent_key,
    )

task_structure = {
    "topic": cache_data.get("topic", ""),
    "sections": [
        {"section_id": f"section_{i}", "section_name": a, "section_role": "analysis", "content_dependency": []}
        for i, a in enumerate(aspects)
    ],
}

print("\nTask structure sections:")
for ts in task_structure["sections"]:
    print(f"  {ts['section_id']}: {ts['section_name']}")

print("\nProvenance mapping:")
for key, prov in content_provenance.items():
    print(f"  {key} -> section_target={prov.section_target}")

remapped_provenance = {}
for i, aspect in enumerate(aspects):
    sec_id = task_structure["sections"][i]["section_id"]
    if i < len(sections):
        original_key = sections[i].get("id", "")
        if original_key in content_provenance:
            prov = content_provenance[original_key]
            remapped_provenance[original_key] = ContentProvenance(
                source_key=prov.source_key,
                stage=prov.stage,
                agent_type=prov.agent_type,
                section_target=sec_id,
            )
            print(f"\n  Remap: {original_key} -> {sec_id}")

agg_result = AggregationResult(
    data={"topic": cache_data.get("topic", "")},
    sources=[{"title": s.get("title",""), "url": s.get("url",""), "type": s.get("type","web")} for s in cache_data.get("sources", [])],
    layered_content=layered_content,
    content_provenance=content_provenance,
)

from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

class FakeWriter:
    pass
class FakeReviewer:
    pass
class FakeGlobal:
    pass
class FakeRepair:
    pass
class FakeConflict:
    pass
class FakeLLM:
    pass
class FakePM:
    pass

orch = ReportOrchestrator(
    llm_skill=FakeLLM(),
    chapter_writer=FakeWriter(),
    chapter_reviewer=FakeReviewer(),
    global_reviewer=FakeGlobal(),
    data_repair_agent=FakeRepair(),
    conflict_resolver=FakeConflict(),
    prompt_manager=FakePM(),
)

for ts in task_structure["sections"]:
    sec_id = ts["section_id"]
    chapter_data = orch._extract_chapter_data(agg_result, sec_id, [])
    print(f"\n_extract_chapter_data('{sec_id}'): {bool(chapter_data)}, keys={list(chapter_data.keys()) if chapter_data else 'None'}")
    if chapter_data:
        content = chapter_data.get("content", "")
        print(f"  content preview: {content[:100]}")
