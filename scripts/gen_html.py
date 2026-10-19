import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

async def main():
    report_data = json.loads(Path("data/e2e_final_report.json").read_text(encoding="utf-8"))["report"]

    doc_agent = DocumentGenerationAgent(agent_id="doc_gen_e2e")
    result = await doc_agent.execute({
        "action": "produce_document",
        "task_id": "e2e_final",
        "output_format": "html",
        "research_result": report_data,
    })

    if result.get("success"):
        print(f"HTML报告: {result.get('document_path')}")
    else:
        print(f"失败: {result.get('error')}")

asyncio.run(main())
