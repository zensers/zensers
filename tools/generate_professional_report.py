# -*- coding: utf-8 -*-
"""
zensers 专业报告生成脚本

使用专业级模板生成行业研究报告。
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def generate_toc_html(sections: List[Dict[str, Any]]) -> str:
    """生成目录 HTML"""
    # 章节标题映射
    section_titles = {
        "section_0": "市场概况",
        "section_1": "竞争格局",
        "section_2": "技术趋势",
        "section_3": "风险分析",
        "section_4": "投资建议",
    }
    
    toc_items = []
    for i, section in enumerate(sections, 1):
        section_id = section.get("id", f"section_{i-1}")
        title = section.get("title", "") or section_titles.get(section_id, f"Section {i}")
        toc_items.append(f'''
            <li class="toc-item">
                <span class="chapter-num">{i:02d}</span>
                <span class="chapter-title">{title}</span>
                <span class="chapter-page">{i + 2}</span>
            </li>
        ''')
    return "\n".join(toc_items)


def generate_content_html(sections: List[Dict[str, Any]]) -> str:
    """生成正文 HTML"""
    content_parts = []
    
    # 章节标题映射
    section_titles = {
        "section_0": "市场概况",
        "section_1": "竞争格局",
        "section_2": "技术趋势",
        "section_3": "风险分析",
        "section_4": "投资建议",
    }
    
    for i, section in enumerate(sections, 1):
        section_id = section.get("id", f"section_{i-1}")
        title = section.get("title", "") or section_titles.get(section_id, f"Section {i}")
        content = section.get("content", "")
        
        # 章节标题
        content_parts.append(f'<h1 class="chapter-title">{i:02d} {title}</h1>')
        
        # 章节内容（转换 Markdown 到 HTML）
        html_content = markdown_to_html(content)
        content_parts.append(f'<div class="section-content">{html_content}</div>')
    
    return "\n".join(content_parts)


def markdown_to_html(text: str) -> str:
    """简单的 Markdown 到 HTML 转换"""
    import re
    
    if not text:
        return ""
    
    lines = text.split('\n')
    html_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            html_lines.append('')
            continue
        
        # 标题
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            title_text = stripped[level:].strip()
            if level == 1:
                html_lines.append(f'<h2 class="section-title">{title_text}</h2>')
            elif level == 2:
                html_lines.append(f'<h3 class="subsection-title">{title_text}</h3>')
            elif level == 3:
                html_lines.append(f'<h4 class="sub-subsection-title">{title_text}</h4>')
            continue
        
        # 粗体
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        
        # 斜体
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)
        
        # 列表
        if stripped.startswith('- ') or stripped.startswith('* '):
            html_lines.append(f'<li>{stripped[2:]}</li>')
            continue
        
        # 数字列表
        num_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_match:
            html_lines.append(f'<li>{num_match.group(2)}</li>')
            continue
        
        # 普通段落
        html_lines.append(f'<p>{stripped}</p>')
    
    return '\n'.join(html_lines)


def generate_report_html(
    topic: str,
    sections: List[Dict[str, Any]],
    exec_summary: str = "",
    key_findings: List[str] = None,
) -> str:
    """生成完整报告 HTML"""
    
    # 读取模板
    template_path = ROOT / "templates" / "professional_report.html"
    template = template_path.read_text(encoding="utf-8")
    
    # 生成目录
    toc_html = generate_toc_html(sections)
    
    # 生成正文
    content_html = generate_content_html(sections)
    
    # 添加关键发现
    if key_findings:
        findings_html = '<div class="key-findings"><h2>关键发现</h2><ul>'
        for finding in key_findings:
            findings_html += f'<li>{finding}</li>'
        findings_html += '</ul></div>'
        content_html = findings_html + content_html
    
    # 替换模板变量
    html = template.replace("{{title}}", topic)
    html = html.replace("{{subtitle}}", f"{topic}深度研究报告")
    html = html.replace("{{date}}", datetime.now().strftime("%Y年%m月"))
    html = html.replace("{{report_type}}", "行业深度研究")
    html = html.replace("{{toc_items}}", toc_html)
    html = html.replace("{{content}}", content_html)
    html = html.replace("{{page_num}}", "1")
    
    return html


async def generate_professional_report(
    topic: str,
    cache_path: str = None,
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    生成专业级行业研究报告
    
    Args:
        topic: 研究主题
        cache_path: 数据缓存路径
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
    
    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / f"professional_{topic.replace(' ', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_dir = out_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    
    print(f"开始生成专业级报告: {topic}")
    print(f"输出目录: {out_dir}")
    
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
    
    framework_config = {"name": "行业深度研究"}
    
    # 构建聚合结果
    from types import SimpleNamespace
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
    try:
        report = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config=framework_config,
            aggregated_result=aggregated_result,
            topic=topic,
            task_id=f"professional_{topic.replace(' ', '_')}",
        )
        
        # 保存 JSON
        report_file = out_dir / "report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # 生成专业级 HTML
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
    
    parser = argparse.ArgumentParser(description="zensers 专业报告生成脚本")
    parser.add_argument("--topic", required=True, help="研究主题")
    parser.add_argument("--cache", help="数据缓存路径")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    result = asyncio.run(generate_professional_report(
        topic=args.topic,
        cache_path=args.cache,
        output_dir=args.output,
    ))
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
