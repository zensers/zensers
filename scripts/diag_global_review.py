"""诊断脚本：单独测试GlobalReviewAgent，捕获LLM原始输出"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
from src.agents.fixed_agents.report_upgrade.models import ReviewInput
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

async def test():
    pm = PromptManager()
    
    fake_report_summary = """### 第1章：比亚迪核心财务指标
核心结论：营收1502亿元
正文前段：比亚迪2026Q1实现营收1502.25亿元...
关键数据：总销量 70.05 万辆, 营业收入 1502.25 亿元
"""
    
    fake_conflicts = "无数据冲突"
    
    agent = GlobalReviewAgent(prompt_manager=pm)
    
    result = await agent.review(ReviewInput(
        framework_config={"name": "行业研究"},
        report_summary=fake_report_summary,
        conflicts_summary=fake_conflicts,
    ))
    
    print(f"overall_score: {result.overall_score}")
    print(f"dimension_scores: {result.dimension_scores}")
    print(f"issues count: {len(result.issues)}")
    print(f"fix_suggestions count: {len(result.fix_suggestions)}")

asyncio.run(test())
