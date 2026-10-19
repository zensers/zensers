# -*- coding: utf-8 -*-
"""
zensers 完整流程报告生成脚本

使用 zensers 完整研究流水线生成专业级行业研究报告。
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def generate_comprehensive_report(
    topic: str,
    aspects: list = None,
    output_format: str = "docx",
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    使用 zensers 完整流程生成综合研究报告
    
    Args:
        topic: 研究主题（如"中国智能手机市场"）
        aspects: 研究方面（如["市场规模", "竞争格局", "技术趋势"]）
        output_format: 输出格式（docx/pptx/pdf/html）
        output_dir: 输出目录
    
    Returns:
        生成结果
    """
    from src.core.orchestrator.orchestrator import ResearchOrchestrator
    
    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / f"comprehensive_{topic.replace(' ', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"开始生成综合研究报告: {topic}")
    print(f"研究方面: {aspects or '自动分析'}")
    print(f"输出格式: {output_format}")
    print(f"输出目录: {out_dir}")
    
    try:
        # 创建研究编排器
        orchestrator = ResearchOrchestrator()
        
        # 准备研究请求
        research_request = {
            "topic": topic,
            "aspects": aspects or [
                "市场规模与增长趋势",
                "竞争格局分析",
                "技术发展趋势",
                "政策环境分析",
                "风险分析",
                "投资建议",
            ],
            "output_format": output_format,
            "output_dir": str(out_dir),
        }
        
        # 执行研究（非交互模式）
        print("正在执行研究流水线...")
        result = await orchestrator.research(
            research_request,
            interaction_mode=False,
        )
        
        if result.get("success"):
            print(f"报告生成成功!")
            print(f"  - 任务ID: {result.get('task_id')}")
            print(f"  - 输出目录: {result.get('output_dir')}")
            
            # 列出生成的文件
            output_path = Path(result.get('output_dir', out_dir))
            if output_path.exists():
                print(f"  - 生成的文件:")
                for file in output_path.rglob("*"):
                    if file.is_file():
                        print(f"    - {file.name} ({file.stat().st_size} bytes)")
            
            return result
        else:
            print(f"报告生成失败: {result.get('error')}")
            return result
            
    except Exception as e:
        print(f"报告生成失败: {e}")
        return {"error": str(e)}


async def generate_report_from_cache(
    topic: str,
    cache_path: str,
    output_format: str = "docx",
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    从缓存数据生成报告（用于测试）
    
    Args:
        topic: 研究主题
        cache_path: 缓存数据路径
        output_format: 输出格式
        output_dir: 输出目录
    
    Returns:
        生成结果
    """
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
    from src.converters.html_to_word import HTMLToWordConverter
    from types import SimpleNamespace
    
    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / f"cache_{topic.replace(' ', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_dir = out_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    
    print(f"从缓存生成报告: {topic}")
    print(f"缓存路径: {cache_path}")
    
    # 加载缓存数据
    cache_file = Path(cache_path)
    if not cache_file.exists():
        return {"error": f"缓存文件不存在: {cache_path}"}
    
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    
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
    
    # 构建任务结构（更详细的章节）
    task_structure = {
        "sections": [
            {"section_id": "section_0", "title": "执行摘要", "role": "executive_summary"},
            {"section_id": "section_1", "title": "市场概况", "role": "overview"},
            {"section_id": "section_2", "title": "市场规模与增长趋势", "role": "market_size"},
            {"section_id": "section_3", "title": "竞争格局分析", "role": "competition"},
            {"section_id": "section_4", "title": "技术发展趋势", "role": "technology"},
            {"section_id": "section_5", "title": "政策环境分析", "role": "policy"},
            {"section_id": "section_6", "title": "风险分析", "role": "risk"},
            {"section_id": "section_7", "title": "投资建议", "role": "recommendation"},
        ]
    }
    
    framework_config = {"name": "行业深度研究"}
    
    # 构建聚合结果
    layered_content: Dict[str, Dict[str, Any]] = {"analysis": {}}
    content_provenance: Dict[str, Any] = {}
    all_data_points = []
    
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
    try:
        report = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=aggregated_result,
            topic=topic,
            task_id=f"cache_{topic.replace(' ', '_')}",
        )
        
        # 保存 JSON
        report_file = out_dir / "report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # 生成 HTML
        from tools.generate_professional_report import generate_report_html
        sections = report.get("sections", [])
        key_findings = report.get("key_findings", [])
        
        html_content = generate_report_html(
            topic=topic,
            sections=sections,
            key_findings=key_findings,
        )
        
        # 保存 HTML
        html_file = out_dir / "report.html"
        html_file.write_text(html_content, encoding="utf-8")
        
        # 转换为 Word
        converter = HTMLToWordConverter()
        word_result = converter.convert(
            html=html_content,
            output_path=str(out_dir / f"{topic}.docx"),
        )
        
        print(f"报告生成完成!")
        print(f"  - JSON: {report_file}")
        print(f"  - HTML: {html_file}")
        print(f"  - Word: {out_dir / f'{topic}.docx'}")
        
        return {
            "success": True,
            "topic": topic,
            "output_dir": str(out_dir),
            "json_file": str(report_file),
            "html_file": str(html_file),
            "word_file": str(out_dir / f"{topic}.docx"),
            "word_size": word_result.file_size if word_result.success else 0,
        }
        
    except Exception as e:
        print(f"报告生成失败: {e}")
        return {"error": str(e)}


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="zensers 综合报告生成脚本")
    parser.add_argument("--topic", required=True, help="研究主题")
    parser.add_argument("--aspects", nargs="+", help="研究方面")
    parser.add_argument("--cache", help="缓存数据路径（用于测试）")
    parser.add_argument("--format", default="docx", help="输出格式")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    if args.cache:
        result = asyncio.run(generate_report_from_cache(
            topic=args.topic,
            cache_path=args.cache,
            output_format=args.format,
            output_dir=args.output,
        ))
    else:
        result = asyncio.run(generate_comprehensive_report(
            topic=args.topic,
            aspects=args.aspects,
            output_format=args.format,
            output_dir=args.output,
        ))
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
