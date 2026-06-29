import json
from pathlib import Path

data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

lines = []
lines.append(f"topic: {data['topic']}")
lines.append(f"aspects: {data['aspects']}")
lines.append(f"sections: {len(data['sections'])}")
lines.append(f"sources: {len(data['sources'])}")
lines.append("")

for i, s in enumerate(data['sections']):
    lines.append(f"=== Section {i} ===")
    lines.append(f"  id: {s['id']}")
    lines.append(f"  title: {s['title']}")
    lines.append(f"  content_len: {len(s['content'])}")
    lines.append(f"  data_points: {len(s.get('data_points', []))}")
    lines.append(f"  content_preview: {s['content'][:300]}")
    lines.append("")

lines.append("=== Sources by agent_id ===")
from collections import Counter
agent_counts = Counter(s.get('agent_id', 'unknown') for s in data['sources'])
for aid, cnt in agent_counts.most_common(10):
    lines.append(f"  {aid}: {cnt} sources")

Path("data/e2e_nvidia_inspect.txt").write_text("\n".join(lines), encoding="utf-8")
