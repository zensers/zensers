import json
from pathlib import Path

cache_data = json.loads(Path("data/research_233fdf0e/research_result_cache.json").read_text(encoding="utf-8"))

lines = []
lines.append(f"Topic: {cache_data.get('topic','')}")
lines.append(f"Aspects: {cache_data.get('aspects',[])}")
lines.append(f"Sections: {len(cache_data.get('sections',[]))}")
lines.append(f"Sources: {len(cache_data.get('sources',[]))}")
lines.append(f"key_findings: {cache_data.get('key_findings',[])}")
lines.append("")

for i, sec in enumerate(cache_data.get("sections", [])):
    lines.append(f"Section {i}:")
    lines.append(f"  id: {sec.get('id','')}")
    lines.append(f"  title: {sec.get('title','')}")
    lines.append(f"  content: {sec.get('content','')[:200]}")
    lines.append(f"  data_points: {sec.get('data_points',[])}")
    lines.append(f"  charts: {sec.get('charts',[])}")
    lines.append(f"  sources: {len(sec.get('sources',[]))} items")
    lines.append(f"  _provenance: {sec.get('_provenance',{})}")
    lines.append(f"  ALL keys: {list(sec.keys())}")
    lines.append("")

lines.append(f"\nSources sample:")
for s in cache_data.get("sources",[])[:3]:
    lines.append(f"  {json.dumps(s, ensure_ascii=False)[:150]}")

Path("data/latest_data_detail.txt").write_text("\n".join(lines), encoding="utf-8")
