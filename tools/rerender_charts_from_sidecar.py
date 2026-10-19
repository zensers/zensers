# -*- coding: utf-8 -*-
"""Rerender all charts from sidecar records (no LLM, content untouched)."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASE_DIR = ROOT / "output" / "cases" / "humanoid_robot"
JSON_FILE = CASE_DIR / "research_result.json"
SIDECAR_FILE = CASE_DIR / "charts.json"
CHART_PERSIST_DIR = ROOT / "data" / "html_reports" / "charts"
CHART_COPY_DIR = CASE_DIR / "charts"


def main() -> None:
    from src.services.chart_generator import ChartGenerator, ChartSidecar
    CHART_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    generator = ChartGenerator(output_dir=str(CHART_PERSIST_DIR))
    sidecar = ChartSidecar(str(SIDECAR_FILE))
    ok, fail = 0, 0
    for chart_id, rec in list(sidecar._records.items()):
        try:
            spec = ChartSidecar(str(SIDECAR_FILE)).get(chart_id)
            if spec is None:
                from src.services.chart_generator import ChartSpec
                spec = ChartSpec.from_record(rec)
            rendered = generator.generate(spec)
            if not rendered.success or not rendered.image_path:
                print(f"  !! render failed [{chart_id}]: {rendered.error}", flush=True)
                fail += 1
                continue
            rec["path"] = rendered.image_path
            ok += 1
        except Exception as exc:
            print(f"  !! render raised [{chart_id}]: {exc}", flush=True)
            fail += 1
    sidecar.save()
    path_by_id = {cid: r.get("path", "") for cid, r in sidecar._records.items()}
    report = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    for sec in report.get("sections", []):
        for ch in sec.get("charts", []):
            cid = ch.get("chart_id", "")
            if cid in path_by_id and path_by_id[cid]:
                ch["path"] = path_by_id[cid]
    JSON_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    CHART_COPY_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for p in path_by_id.values():
        src = Path(str(p))
        if src.is_file():
            shutil.copy2(src, CHART_COPY_DIR / src.name)
            copied += 1
    print(f"DONE ok={ok} fail={fail} copied={copied}")


if __name__ == "__main__":
    main()
