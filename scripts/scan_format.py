import json
from pathlib import Path

# 取3个不同时期的数据做对比
files = [
    ("最新(06-26)", "data/research_233fdf0e/research_result_cache.json"),
    ("中期(06-25)", "data/research_efbdc8ef/research_result_cache.json"),
    ("早期(06-19)", "data/research_24c2875c/research_result_cache.json"),
]

lines = []
for label, fpath in files:
    data = json.loads(Path(fpath).read_text(encoding="utf-8"))
    lines.append(f"{'='*70}")
    lines.append(f"{label}: {data.get('topic','')}")
    lines.append(f"{'='*70}")
    lines.append(f"top-level keys: {list(data.keys())}")
    lines.append(f"sections: {len(data.get('sections',[]))}, sources: {len(data.get('sources',[]))}")
    lines.append(f"aspects: {data.get('aspects',[])}")

    for i, sec in enumerate(data.get("sections",[])[:2]):
        lines.append(f"\n  Section {i}: id={sec.get('id','')}, title={sec.get('title','')[:40]}")
        lines.append(f"    keys: {list(sec.keys())}")
        lines.append(f"    content len: {len(sec.get('content',''))}")

        dp = sec.get("data_points", [])
        lines.append(f"    data_points count: {len(dp)}")
        if dp and isinstance(dp[0], dict):
            lines.append(f"    data_points[0] keys: {list(dp[0].keys())}")
            lines.append(f"    data_points[0]: {json.dumps(dp[0], ensure_ascii=False)[:200]}")
            if len(dp) > 1:
                lines.append(f"    data_points[1]: {json.dumps(dp[1], ensure_ascii=False)[:200]}")

        charts = sec.get("charts", [])
        if charts:
            lines.append(f"    charts: {len(charts)}, charts[0] keys: {list(charts[0].keys()) if charts else 'N/A'}")

    srcs = data.get("sources", [])
    if srcs:
        lines.append(f"\n  sources[0] keys: {list(srcs[0].keys())}")
        lines.append(f"  sources[0]: {json.dumps(srcs[0], ensure_ascii=False)[:200]}")

Path("data/data_format_deep_scan.txt").write_text("\n".join(lines), encoding="utf-8")
