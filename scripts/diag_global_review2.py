"""诊断脚本v2：用e2e实际报告数据测试GlobalReviewAgent"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent, serialize_report_for_review
from src.agents.fixed_agents.report_upgrade.models import ReviewInput, ChapterWriteOutput, DataPoint
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

async def test():
    report_data = json.loads(Path("data/e2e_v4_report.json").read_text(encoding="utf-8"))
    
    chapters = []
    for sec in report_data.get("sections", []):
        dps = [DataPoint(**dp) for dp in sec.get("data_points", [])]
        ch = ChapterWriteOutput(
            chapter_id=sec["id"],
            title=sec["title"],
            content=sec["content"],
            data_points_used=dps,
            key_conclusions=sec.get("key_conclusions", []),
        )
        chapters.append(ch)
    
    registry = DataRegistry()
    report_summary = serialize_report_for_review(chapters, registry)
    print(f"report_summary length: {len(report_summary)} chars")
    print(f"report_summary first 200: {report_summary[:200]}")
    print()
    
    pm = PromptManager()
    agent = GlobalReviewAgent(prompt_manager=pm)
    
    result = await agent.review(ReviewInput(
        framework_config={"name": report_data.get("title", "")},
        report_summary=report_summary,
        conflicts_summary="无数据冲突",
    ))
    
    print(f"overall_score: {result.overall_score}")
    print(f"dimension_scores: {result.dimension_scores}")
    print(f"issues count: {len(result.issues)}")

asyncio.run(test())
