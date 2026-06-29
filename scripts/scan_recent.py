import json
from pathlib import Path
from datetime import datetime

data_dir = Path("data")
results = []
for cache_file in sorted(data_dir.glob("research_*/research_result_cache.json")):
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        topic = data.get("topic", "")
        sections = len(data.get("sections", []))
        sources = len(data.get("sources", []))
        aspects = data.get("aspects", [])
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime).strftime("%m-%d %H:%M")

        sec_ids = [s.get("id","")[:30] for s in data.get("sections",[])[:3]]

        layered_keys = set()
        lc = data.get("layered_content", {})
        if isinstance(lc, dict):
            for stage, items in lc.items():
                if isinstance(items, dict):
                    layered_keys.update(list(items.keys())[:3])

        dp_sample = ""
        for s in data.get("sections", []):
            dps = s.get("data_points", [])
            if dps and isinstance(dps[0], dict):
                dp_sample = str(list(dps[0].keys())[:5])
                break

        results.append({
            "dir": cache_file.parent.name,
            "mtime": mtime,
            "topic": topic[:30],
            "sections": sections,
            "sources": sources,
            "section_ids": sec_ids,
            "has_layered_content": bool(lc),
            "layered_keys": list(layered_keys)[:3],
            "dp_sample_keys": dp_sample,
        })
    except Exception as e:
        results.append({"dir": cache_file.parent.name, "error": str(e)})

results.sort(key=lambda x: x.get("mtime",""), reverse=True)

lines = []
for r in results[:20]:
    if "error" in r:
        lines.append(f"{r['dir']}: ERROR - {r['error']}")
    else:
        lines.append(f"[{r['mtime']}] {r['dir']}: {r['topic']} | {r['sections']}sec {r['sources']}src | has_lc={r['has_layered_content']} lc_keys={r['layered_keys']} | sec_ids={r['section_ids']} | dp_keys={r['dp_sample_keys']}")

Path("data/recent_data_scan.txt").write_text("\n".join(lines), encoding="utf-8")
