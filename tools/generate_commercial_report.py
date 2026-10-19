# -*- coding: utf-8 -*-
"""
zensers 报告生成脚本

供子agent调用，生成行业研究报告。
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def generate_report(
    topic: str,
    framework_name: str = "行业分析",
    cache_path: str = None,
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    生成行业研究报告
    
    Args:
        topic: 研究主题（如"中国智能手机市场"）
        framework_name: 框架名称（如"市场进入策略"）
        cache_path: 数据缓存路径（可选）
        output_dir: 输出目录（可选）
    
    Returns:
        报告生成结果
    """
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / f"report_{topic.replace(' ', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_dir = out_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)

    # 初始化组件
    prompt_manager = PromptManager()
    writer = ChapterWriter(prompt_manager=prompt_manager, use_streaming=False)
    reviewer = ChapterReviewAgent(prompt_manager=prompt_manager)
    global_reviewer = GlobalReviewAgent(prompt_manager=prompt_manager)
    conflict_resolver = ConflictResolver(
        search_skill=None, web_scraper_skill=None,
        prompt_manager=prompt_manager, search_gateway=None,
    )

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
        checkpoint_dir=checkpoint_dir,
    )

    # 加载数据缓存
    if cache_path:
        cache_file = Path(cache_path)
    else:
        # 使用默认的测试数据
        cache_file = ROOT / "data" / "e2e_smartphone6_56e991bf" / "real_report_e2e" / "research_result_cache.json"
    
    if not cache_file.exists():
        return {"error": f"数据缓存文件不存在: {cache_file}"}
    
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    
    # 构建任务结构
    task_structure = {
        "sections": [
            {"section_id": "section_0", "title": "市场概况", "role": "overview"},
            {"section_id": "section_1", "title": "竞争格局", "role": "competition"},
            {"section_id": "section_2", "title": "技术趋势", "role": "technology"},
            {"section_id": "section_3", "title": "风险分析", "role": "risk"},
            {"section_id": "section_4", "title": "投资建议", "role": "recommendation"},
        ]
    }
    
    framework_config = {"name": framework_name}
    
    # 构建聚合结果
    layered_content: Dict[str, Dict[str, Any]] = {"analysis": {}}
    content_provenance: Dict[str, Any] = {}
    all_data_points: List[Dict[str, Any]] = []

    for sec in cache.get("sections") or []:
        sid = sec.get("section_id", "")
        layered_content["analysis"][sid] = {
            "content": sec.get("content", ""),
            "data_points": sec.get("data_points") or [],
        }
        content_provenance[sid] = SimpleNamespace(section_target=sid)
        for dp in sec.get("data_points") or []:
            if isinstance(dp, dict):
                all_data_points.append(dp)

    sources = cache.get("sources") or []

    aggregated_result = SimpleNamespace(
        layered_content=layered_content,
        content_provenance=content_provenance,
        raw_search_results=sources,
        sources=sources,
        data={"data_points": all_data_points},
        evidence_registry={},
        conflicts=[],
        stats={"section_count": len(task_structure["sections"])},
    )

    # 生成报告
    print(f"开始生成报告: {topic}")
    print(f"框架: {framework_name}")
    print(f"输出目录: {out_dir}")
    
    try:
        report = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=aggregated_result,
            topic=topic,
            task_id=f"commercial_{topic.replace(' ', '_')}",
        )
        
        # 保存报告
        report_file = out_dir / "report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # 保存执行摘要
        exec_summary = report.get("exec_summary", "")
        exec_summary_file = out_dir / "exec_summary.md"
        exec_summary_file.write_text(exec_summary, encoding="utf-8")
        
        # 保存各章节
        sections_dir = out_dir / "sections"
        sections_dir.mkdir(exist_ok=True)
        
        for section in report.get("sections", []):
            section_id = section.get("section_id", "unknown")
            section_content = section.get("content", "")
            section_file = sections_dir / f"{section_id}.md"
            section_file.write_text(section_content, encoding="utf-8")
        
        print(f"报告生成完成!")
        print(f"  - 执行摘要: {exec_summary_file}")
        print(f"  - 章节目录: {sections_dir}")
        print(f"  - 完整报告: {report_file}")
        
        return {
            "success": True,
            "topic": topic,
            "framework": framework_name,
            "output_dir": str(out_dir),
            "exec_summary_file": str(exec_summary_file),
            "sections_dir": str(sections_dir),
            "report_file": str(report_file),
        }
        
    except Exception as e:
        print(f"报告生成失败: {e}")
        return {"error": str(e)}


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="zensers 报告生成脚本")
    parser.add_argument("--topic", required=True, help="研究主题")
    parser.add_argument("--framework", default="行业分析", help="框架名称")
    parser.add_argument("--cache", help="数据缓存路径")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    result = asyncio.run(generate_report(
        topic=args.topic,
        framework_name=args.framework,
        cache_path=args.cache,
        output_dir=args.output,
    ))
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
