import json
from pathlib import Path

data_dir = Path("data")
results = []
for cache_file in sorted(data_dir.glob("research_*/research_result_cache.json")):
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        topic = data.get("topic", "")
        sections = len(data.get("sections", []))
        sources = len(data.get("sources", []))
        aspects = data.get("aspects", [])
        content_lens = [len(s.get("content", "")) for s in data.get("sections", [])]
        total_content = sum(content_lens)
        results.append({
            "dir": cache_file.parent.name,
            "topic": topic,
            "aspects": aspects,
            "sections": sections,
            "sources": sources,
            "total_content_len": total_content,
        })
    except Exception as e:
        results.append({"dir": cache_file.parent.name, "error": str(e)})

results.sort(key=lambda x: x.get("total_content_len", 0), reverse=True)

output_lines = []
for r in results[:15]:
    if "error" in r:
        output_lines.append(f"{r['dir']}: ERROR - {r['error']}")
    else:
        output_lines.append(
            f"{r['dir']}: topic={r['topic'][:40]}, aspects={r['aspects']}, "
            f"sections={r['sections']}, sources={r['sources']}, content={r['total_content_len']}chars"
        )

Path("data/e2e_cache_scan.txt").write_text("\n".join(output_lines), encoding="utf-8")
