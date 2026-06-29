"""
报告质量评估脚本：使用真实LLM生成章节，评估输出质量。

使用方式：python -m scripts.evaluate_report_quality
需要：环境变量中有可用的LLM API key
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def evaluate():
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

    from src.skills.llm_skill import LLMSkill
    from src.skills.search_skill import MultiSearchSkill
    from src.skills.web_scraper_skill import WebScraperSkill

    print("=== 报告质量评估 ===\n")

    llm = LLMSkill()
    search = MultiSearchSkill()
    scraper = WebScraperSkill()

    pm = PromptManager()
    writer = ChapterWriter(llm_skill=llm, prompt_manager=pm)
    reviewer = ChapterReviewAgent(llm_skill=llm, prompt_manager=pm)
    global_reviewer = GlobalReviewAgent(llm_skill=llm, prompt_manager=pm)
    data_repair = DataRepairAgent(search_skill=search, web_scraper_skill=scraper, llm_skill=llm, prompt_manager=pm)
    conflict_resolver = ConflictResolver(llm_skill=llm, search_skill=search, web_scraper_skill=scraper, prompt_manager=pm)

    orchestrator = ReportOrchestrator(
        llm_skill=llm,
        chapter_writer=writer,
        chapter_reviewer=reviewer,
        global_reviewer=global_reviewer,
        data_repair_agent=data_repair,
        conflict_resolver=conflict_resolver,
        prompt_manager=pm,
    )

    class SimpleAggResult:
        def __init__(self):
            self.data = {}
            self.conflicts = []
            self.stats = {}
            self.sources = [{"title": "测试来源", "url": "https://example.com", "type": "web"}]
            self.layered_content = {
                "analysis": {
                    "agent_market": {
                        "content": "中国新能源汽车市场2025年销量达到约1200万辆，渗透率超过50%。比亚迪、特斯拉、蔚来等品牌竞争激烈。",
                    }
                }
            }
            self.content_provenance = {
                "agent_market": type('P', (), {
                    'source_key': 'agent_market',
                    'stage': 'analysis',
                    'agent_type': 'analysis',
                    'section_target': 'market_size',
                })(),
            }

    task_structure = {
        "topic": "中国新能源汽车市场分析",
        "sections": [
            {"section_id": "market_size", "section_name": "市场规模与渗透率", "section_role": "analysis", "content_dependency": []},
        ],
    }
    framework_config = {"name": "行业研究", "description": "行业研究报告", "agent_config": {}, "section_weights": {}}

    try:
        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=SimpleAggResult(),
            topic="中国新能源汽车市场分析",
        )

        print(f"生成章节数: {len(result['sections'])}")
        for sec in result['sections']:
            print(f"\n--- {sec['title']} ---")
            content = sec['content']
            print(f"字数: {len(content)}")
            print(f"数据点: {len(sec['data_points'])}")
            print(f"前500字:\n{content[:500]}")
            print(f"\n关键发现: {result['key_findings'][:3]}")

        output_path = Path("data") / "report_quality_eval.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n完整报告已保存到: {output_path}")

    except Exception as e:
        print(f"评估失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(evaluate())
