import json
from pathlib import Path

r = json.loads(Path("data/e2e_v2_latest3_report.json").read_text(encoding="utf-8"))
print(f"Meta: {json.dumps(r['meta'], ensure_ascii=False)}")
for sec in r["report"]["sections"]:
    cid = sec["id"]
    title = sec["title"]
    clen = len(sec["content"])
    dps = len(sec.get("data_points", []))
    srcs = len(sec.get("sources", []))
    print(f"  [{cid}] {title}: {clen}字, {dps}数据点, {srcs}来源")

print()
print(r["report"]["sections"][2]["content"][:800])
