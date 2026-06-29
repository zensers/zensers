import json
from pathlib import Path

cache_data = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

sec0 = cache_data["sections"][0]
print(f"Section: {sec0['title']}")
print(f"content length: {len(sec0['content'])} chars")
print(f"content preview (first 500 chars):")
print(sec0['content'][:500])
print(f"\ncontent preview (last 300 chars):")
print(sec0['content'][-300:])
