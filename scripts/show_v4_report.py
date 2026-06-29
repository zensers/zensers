import json
r = json.loads(open("data/e2e_v4_report.json", encoding="utf-8").read())

for sec in r.get("sections", []):
    c = sec.get("content", "")
    dps = sec.get("data_points", [])
    print(f"\n{'='*60}")
    print(f"[{sec['id']}] {sec['title']}")
    print(f"  {len(c)}字, {len(dps)}数据点")
    print(f"{'='*60}")
    print(c)

kf = r.get("key_findings", [])
print(f"\n{'='*60}")
print("KEY FINDINGS")
print(f"{'='*60}")
for i, k in enumerate(kf):
    print(f"[{i+1}] {k}")

qr = r.get("quality_report", {})
print(f"\n{'='*60}")
print("QUALITY REPORT")
print(f"{'='*60}")
print(f"overall_score: {qr.get('overall_score')}")
print(f"convergence_rounds: {qr.get('convergence_rounds')}")
print(f"converged: {qr.get('converged')}")
