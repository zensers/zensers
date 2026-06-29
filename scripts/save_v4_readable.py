import json
from pathlib import Path
r = json.loads(open("data/e2e_v4_report.json", encoding="utf-8").read())
lines = []
for sec in r.get("sections", []):
    c = sec.get("content", "")
    dps = sec.get("data_points", [])
    lines.append(f"\n{'='*60}")
    lines.append(f"[{sec['id']}] {sec['title']}")
    lines.append(f"  {len(c)}字, {len(dps)}数据点")
    lines.append(f"{'='*60}")
    lines.append(c)

kf = r.get("key_findings", [])
lines.append(f"\n{'='*60}")
lines.append("KEY FINDINGS")
lines.append(f"{'='*60}")
for i, k in enumerate(kf):
    lines.append(f"[{i+1}] {k}")

qr = r.get("quality_report", {})
lines.append(f"\n{'='*60}")
lines.append("QUALITY REPORT")
lines.append(f"{'='*60}")
lines.append(f"overall_score: {qr.get('overall_score')}")
lines.append(f"convergence_rounds: {qr.get('convergence_rounds')}")
lines.append(f"converged: {qr.get('converged')}")

Path("data/e2e_v4_readable.txt").write_text("\n".join(lines), encoding="utf-8")
print("Saved to data/e2e_v4_readable.txt")
