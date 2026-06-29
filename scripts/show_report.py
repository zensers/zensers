import json
from pathlib import Path
import sys
sys.path.insert(0, ".")
from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

r = json.loads(Path("data/e2e_v3_report.json").read_text(encoding="utf-8"))

print("=" * 70)
print("  报告全文")
print("=" * 70)

for sec in r["sections"]:
    print(f"\n{'='*60}")
    print(f"  章节: {sec['title']} ({sec['id']})")
    print(f"{'='*60}")
    print(sec["content"])
    print(f"\n  --- 数据点 ({len(sec.get('data_points',[]))}个) ---")
    for dp in sec.get("data_points", [])[:5]:
        print(f"  {dp.get('metric','')} = {dp.get('value','')} {dp.get('unit','')} [来源: {dp.get('source','')[:50]}]")
    if len(sec.get("data_points",[])) > 5:
        print(f"  ... 还有{len(sec['data_points'])-5}个")

print(f"\n{'='*60}")
print("  关键发现")
print(f"{'='*60}")
for i, k in enumerate(r.get("key_findings", [])):
    print(f"  [{i+1}] {k}")
