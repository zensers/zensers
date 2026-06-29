import json
from pathlib import Path

cache_data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

sec0 = cache_data["sections"][0]
dps = sec0.get("data_points", [])

print(f"Section 0: {sec0['title']}")
print(f"data_points count: {len(dps)}")
print(f"first 3 data_points:")
for dp in dps[:3]:
    print(f"  {json.dumps(dp, ensure_ascii=False)[:200]}")

print(f"\nlast 3 data_points:")
for dp in dps[-3:]:
    print(f"  {json.dumps(dp, ensure_ascii=False)[:200]}")

dp_total = len(json.dumps(dps, ensure_ascii=False))
print(f"\ndata_points total size: {dp_total} chars (~{dp_total//4} tokens)")

content_size = len(sec0.get("content", ""))
print(f"content size: {content_size} chars (~{content_size//4} tokens)")
