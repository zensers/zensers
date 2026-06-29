import json
from pathlib import Path

d = json.loads(Path("data/e2e_final_report.json").read_text(encoding="utf-8"))

lines = []
for sec in d["report"]["sections"]:
    lines.append(f"{'='*60}")
    lines.append(f"[{sec['id']}] {sec['title']} ({len(sec['content'])}字, {len(sec['data_points'])}数据点)")
    lines.append(f"{'='*60}")
    lines.append(sec["content"][:2000])
    lines.append("...\n")
    lines.append("数据点:")
    for dp in sec["data_points"][:8]:
        lines.append(f"  - {dp.get('metric','')}: {dp.get('value','')} {dp.get('unit','')} | 来源: {dp.get('source','')}")
    if len(sec["data_points"]) > 8:
        lines.append(f"  ... 还有{len(sec['data_points'])-8}个")
    lines.append("")

lines.append(f"{'='*60}")
lines.append("关键发现")
lines.append(f"{'='*60}")
for i, kf in enumerate(d["report"]["key_findings"]):
    lines.append(f"[{i+1}] {kf}")

Path("data/e2e_full_content.txt").write_text("\n".join(lines), encoding="utf-8")
