import json
import sys
from pathlib import Path
sys.path.insert(0, ".")
from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

r = json.loads(Path("data/e2e_v2_byd3_report.json").read_text(encoding="utf-8"))
for sec in r["report"]["sections"]:
    for dp in sec.get("data_points", []):
        src = dp.get("source", "")
        if _is_vague_source(src):
            print(f"  [{sec['id']}] metric={dp['metric']}, source=<{src}>")
