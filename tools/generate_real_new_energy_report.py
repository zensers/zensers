# -*- coding: utf-8 -*-
"""
新能源汽车行业真实研究报告生成脚本

使用zensers核心功能模块生成完整的研究报告。
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _has_llm_configuration() -> bool:
    """检查是否有LLM配置"""
    return bool(
        os.environ.get("LLM_API_KEY")
        or os.environ.get("LLM_MODEL")
        or os.environ.get("OPENAI_API_KEY")
    )


def generate_toc_html(sections: List[Dict[str, Any]]) -> str:
    """生成目录 HTML"""
    toc_items = []
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
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
    
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
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
    in_table = False
    table_rows = []
    
    def flush_table():
        """输出表格"""
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        
        # 检查表格是否有效（至少有表头和分隔行）
        if len(table_rows) < 2:
            # 表格无效，作为普通文本处理
            for row in table_rows:
                html_lines.append(f'<p>{"|".join(row)}</p>')
            in_table = False
            table_rows = []
            return
        
        # 找到表头
        header_row = table_rows[0]
        num_cols = len(header_row)
        
        # 过滤掉分隔行（全是-和空格的行）
        data_rows = []
        for row in table_rows[1:]:
            # 检查是否是分隔行
            if all(set(cell.strip()) <= set('- :') for cell in row if cell.strip()):
                continue
            # 确保每行列数一致
            while len(row) < num_cols:
                row.append('')
            data_rows.append(row[:num_cols])
        
        if not data_rows:
            # 没有数据行，作为普通文本处理
            html_lines.append(f'<p>{"|".join(header_row)}</p>')
            in_table = False
            table_rows = []
            return
        
        # 输出表格
        html_lines.append('<table>')
        html_lines.append('<thead><tr>')
        for cell in header_row:
            cell_text = cell.strip()
            # 移除Markdown格式
            cell_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cell_text)
            html_lines.append(f'<th>{cell_text}</th>')
        html_lines.append('</tr></thead>')
        html_lines.append('<tbody>')
        for row in data_rows:
            html_lines.append('<tr>')
            for cell in row:
                cell_text = cell.strip()
                # 移除Markdown格式
                cell_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cell_text)
                html_lines.append(f'<td>{cell_text}</td>')
            html_lines.append('</tr>')
        html_lines.append('</tbody>')
        html_lines.append('</table>')
        
        in_table = False
        table_rows = []
    
    for line in lines:
        stripped = line.strip()
        
        # 空行处理
        if not stripped:
            if in_table:
                flush_table()
            html_lines.append('')
            continue
        
        # 检查是否是表格行
        if stripped.startswith('|') and stripped.endswith('|'):
            if not in_table:
                in_table = True
            # 解析表格行
            cells = [cell.strip() for cell in stripped.split('|')[1:-1]]
            table_rows.append(cells)
            continue
        
        # 如果正在处理表格但当前行不是表格行，结束表格
        if in_table:
            flush_table()
        
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
        
        # 列表项
        if stripped.startswith('- ') or stripped.startswith('* '):
            content = stripped[2:]
            # 处理粗体
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # 数字列表
        num_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_match:
            content = num_match.group(2)
            # 处理粗体
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # 处理粗体和斜体
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)
        
        # 普通段落
        html_lines.append(f'<p>{stripped}</p>')
    
    # 处理文件末尾的表格
    if in_table:
        flush_table()
    
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
    html = html.replace("{{subtitle}}", f"{topic}研究报告")
    html = html.replace("{{date}}", datetime.now().strftime("%Y年%m月"))
    html = html.replace("{{report_type}}", "行业深度研究")
    html = html.replace("{{toc_items}}", toc_html)
    html = html.replace("{{content}}", content_html)
    html = html.replace("{{page_num}}", "1")
    
    return html


async def generate_real_new_energy_report(
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    生成新能源汽车行业真实研究报告
    
    Args:
        output_dir: 输出目录
    
    Returns:
        生成结果
    """
    from src.config.settings import settings
    from src.core.llm_client import init_llm_infrastructure
    from src.core.orchestrator.orchestrator import ResearchOrchestrator
    from src.converters.html_to_word import HTMLToWordConverter
    
    # 检查LLM配置
    if not _has_llm_configuration():
        print("错误: 未配置LLM API密钥。请设置 LLM_API_KEY 或 OPENAI_API_KEY 环境变量。")
        return {"error": "LLM未配置"}
    
    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / "real_new_energy_vehicle_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"开始生成新能源汽车行业真实研究报告")
    print(f"输出目录: {out_dir}")
    print("这可能需要1-2小时，请耐心等待...")
    
    # 初始化LLM基础设施
    init_llm_infrastructure(settings.llm_profiles)
    
    # 创建研究ID
    task_id = f"new_energy_vehicle_{uuid.uuid4().hex[:8]}"
    
    # 创建研究编排器
    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    
    # 定义研究主题和章节
    TOPIC = "中国新能源汽车行业深度研究"
    CHAPTERS = [
        "市场规模与增长趋势",
        "产业链分析",
        "竞争格局分析",
        "技术发展趋势",
        "政策环境分析",
        "风险分析",
        "投资建议与展望",
        "结论与建议",
    ]
    
    print(f"研究主题: {TOPIC}")
    print(f"章节结构: {len(CHAPTERS)}个章节")
    print("正在执行完整研究流程...")
    
    try:
        # 执行研究
        result = await orchestrator.research(
            user_input={
                "session_id": task_id,
                "topic": TOPIC,
                "aspects": CHAPTERS,
                "output_type": "industry_report",
                "output_format": "html",
            },
            user_id="commercial_demo",
            interaction_mode=False,
            output_type="industry_report",
            custom_aspects=CHAPTERS,
            framework="standard",
            output_format="html",
        )
        
        print(f"研究完成! 状态: {result.status}")
        
        # 检查结果
        if result.status not in ("completed", "completed_with_warnings"):
            print(f"研究未完成: {result.summary}")
            return {"error": f"研究未完成: {result.status}"}
        
        # 获取报告内容
        report = result.report
        if not report or not isinstance(report.get("sections"), list):
            print("报告内容无效")
            return {"error": "报告内容无效"}
        
        print(f"报告包含 {len(report['sections'])} 个章节")
        
        # 保存JSON结果
        json_file = out_dir / "research_result.json"
        json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # 生成HTML报告
        sections = report.get("sections", [])
        key_findings = report.get("key_findings", [])
        
        html_content = generate_report_html(
            topic=TOPIC,
            sections=sections,
            key_findings=key_findings,
        )
        
        # 保存HTML
        html_file = out_dir / "report.html"
        html_file.write_text(html_content, encoding="utf-8")
        
        # 转换为Word
        converter = HTMLToWordConverter()
        word_result = converter.convert(
            html=html_content,
            output_path=str(out_dir / f"{TOPIC}.docx"),
        )
        
        print(f"报告生成完成!")
        print(f"  - JSON: {json_file}")
        print(f"  - HTML: {html_file}")
        print(f"  - Word: {out_dir / f'{TOPIC}.docx'}")
        
        return {
            "success": True,
            "topic": TOPIC,
            "task_id": task_id,
            "output_dir": str(out_dir),
            "json_file": str(json_file),
            "html_file": str(html_file),
            "word_file": str(out_dir / f"{TOPIC}.docx"),
            "word_size": word_result.file_size if word_result.success else 0,
            "section_count": len(sections),
            "status": result.status,
        }
        
    except Exception as e:
        print(f"报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="新能源汽车行业真实研究报告生成脚本")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    result = asyncio.run(generate_real_new_energy_report(
        output_dir=args.output,
    ))
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
