import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from src.core.llm_client import call_llm

async def test():
    r = await call_llm(prompt='Reply with ONLY this exact JSON wrapped in ```json``` code block:\n```json\n{"status": "ok", "score": 85}\n```', max_tokens=200, temperature=0)
    print("SUCCESS:", r.get("success"))
    content = r.get("content", "")
    print("CONTENT_START:")
    print(content)
    print(":CONTENT_END")
    print("HAS_JSON_BLOCK:", "```json" in content)

asyncio.run(test())
