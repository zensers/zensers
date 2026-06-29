import json
from pathlib import Path

data = json.loads(Path("data/research_01150942/research_result_cache.json").read_text(encoding="utf-8"))

output = []
output.append(f"topic: {data['topic']}")
output.append(f"title: {data['title']}")
output.append(f"aspects: {data['aspects']}")
output.append(f"sections: {len(data['sections'])}")
output.append(f"sources: {len(data['sources'])}")

for s in data['sections']:
    output.append(f"  section: id={s['id']}, title={s['title']}, content_len={len(s['content'])}, data_points={len(s.get('data_points',[]))}")

output.append("\nFirst 5 sources:")
for s in data['sources'][:5]:
    output.append(f"  {s.get('title','')[:50]} | {s.get('url','')[:60]} | agent_id={s.get('agent_id','')}")

Path("data/e2e_inspect.txt").write_text("\n".join(output), encoding="utf-8")
