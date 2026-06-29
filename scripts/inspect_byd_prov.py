import json
from pathlib import Path

cache_data = json.loads(Path("data/research_24c2875c/research_result_cache.json").read_text(encoding="utf-8"))

lines = []
for i, sec in enumerate(cache_data.get("sections", [])):
    prov = sec.get("_provenance", {})
    lines.append(f"Section {i}: id={sec['id']}")
    lines.append(f"  _provenance: {json.dumps(prov, ensure_ascii=False)}")
    lines.append(f"  content: {len(sec.get('content',''))} chars")
    lines.append(f"  data_points: {len(sec.get('data_points',[]))} items")
    lines.append(f"  sources: {len(sec.get('sources',[]))} items")
    lines.append("")

Path("data/byd_provenance.txt").write_text("\n".join(lines), encoding="utf-8")
