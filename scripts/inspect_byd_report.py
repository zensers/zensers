import json
from pathlib import Path

report = json.loads(Path("data/e2e_v2_byd3_report.json").read_text(encoding="utf-8"))

meta = report.get("meta", {})
print(f"Meta: {json.dumps(meta, ensure_ascii=False)}")

sections = report.get("report", {}).get("sections", [])
for sec in sections:
    content = sec.get("content", "")
    print(f"\n[{sec.get('id','')}] {sec.get('title','')}: {len(content)} chars")
    print(f"  data_points: {len(sec.get('data_points',[]))}")
    print(f"  sources: {len(sec.get('sources',[]))}")
    print(f"  content[:200]: {content[:200]}")
