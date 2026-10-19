# -*- coding: utf-8 -*-
"""
调用zensers修订模块对报告进行细节修订
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure

# 初始化LLM
init_llm_infrastructure(settings.llm_profiles)


async def revise_report():
    """调用修订模块修订报告"""
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    
    print("=" * 60)
    print("开始修订报告")
    print("=" * 60)
    
    # 加载研究结果
    research_file = Path("output/full_research/research_result.json")
    if not research_file.exists():
        print("研究结果文件不存在")
        return
    
    research_data = json.loads(research_file.read_text(encoding="utf-8"))
    
    # 初始化组件
    prompt_manager = PromptManager()
    writer = ChapterWriter(prompt_manager=prompt_manager, use_streaming=False)
    reviewer = ChapterReviewAgent(prompt_manager=prompt_manager)
    global_reviewer = GlobalReviewAgent(prompt_manager=prompt_manager)
    conflict_resolver = ConflictResolver(
        search_skill=None, web_scraper_skill=None,
        prompt_manager=prompt_manager, search_gateway=None,
    )
    
    # 创建orchestrator
    orchestrator = ReportOrchestrator(
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        data_repair_agent=None,
        conflict_resolver=conflict_resolver,
        prompt_manager=prompt_manager,
        skill_registry=None,
        search_gateway=None,
        search_skill=None,
        web_scraper_skill=None,
        chart_planner=None,
        chart_generator=None,
        checkpoint_dir=Path("output/full_research/checkpoints"),
    )
    
    # 设置prompt_manager属性
    orchestrator._prompt_manager = prompt_manager
    
    # 设置orchestrator的状态
    sections = research_data.get("sections", [])
    orchestrator._chapters = []
    for section in sections:
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
        chapter = ChapterWriteOutput(
            chapter_id=section.get("id", ""),
            title=section.get("title", ""),
            content=section.get("content", ""),
            data_points_used=[],
            key_conclusions=[],
        )
        orchestrator._chapters.append(chapter)
    
    orchestrator._framework_config = {"name": "行业研究报告"}
    orchestrator._task_structure = {"topic": "中国新能源汽车行业深度研究"}
    
    # 修订请求
    revision_requests = [
        "请补充更多数据支撑，包括具体的市场规模数字、增长率、市场份额等",
        "请增加数据表格，展示历史数据和预测数据",
        "请改进内容结构，确保每个章节有清晰的概述、详细分析、关键发现和战略启示",
        "请删除重复内容，确保每个章节内容独特",
        "请确保数据一致性，同一指标在不同章节中数值一致",
    ]
    
    for i, request in enumerate(revision_requests, 1):
        print(f"\n[修订 {i}/{len(revision_requests)}] {request}")
        
        try:
            result = await orchestrator.revision(user_request=request)
            
            print(f"  修订结果: {'成功' if result.get('global_review_passed') else '需要进一步修订'}")
            print(f"  全局评分: {result.get('global_review_score', 'N/A')}")
            
            # 保存修订结果
            revision_file = Path(f"output/full_research/revision_{i}.json")
            revision_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            
        except Exception as e:
            print(f"  修订失败: {e}")
    
    # 保存最终修订后的报告
    final_chapters = []
    for chapter in orchestrator._chapters:
        final_chapters.append({
            "id": chapter.chapter_id,
            "title": chapter.title,
            "content": chapter.content,
        })
    
    final_report = {
        "topic": "中国新能源汽车行业深度研究",
        "sections": final_chapters,
        "revision_count": len(revision_requests),
    }
    
    final_file = Path("output/full_research/final_research_result.json")
    final_file.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("修订完成!")
    print(f"最终结果: {final_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(revise_report())
