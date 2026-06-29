import json, sys
sys.path.insert(0, ".")
from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

r = json.loads(open("data/e2e_v3_report.json", "r", encoding="utf-8").read())
for sec in r.get("sections", []):
    sid = sec["id"]
    dps = sec.get("data_points", [])
    vague = [dp for dp in dps if _is_vague_source(dp.get("source", ""))]
    print(f"[{sid}] {len(dps)} dps, {len(vague)} vague")

kf = r.get("key_findings", [])
print(f"\nkey_findings ({len(kf)}):")
for k in kf:
    print(f"  {k[:120]}")
