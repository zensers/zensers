# -*- coding: utf-8 -*-
"""
Expand semiconductor report chapters to reach 30-40 pages
Adds detailed analysis, data tables, and expert insights to each chapter
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm

init_llm_infrastructure(settings.llm_profiles)

OUTPUT_FILE = Path("output/full_research/semiconductor_revised_report_llm.json")


def build_expansion_prompt(chapter_title: str, current_content: str) -> str:
    return f"""你是一位资深的行业研究分析师，请为以下半导体行业研究报告章节添加更详细的内容。

当前章节标题：{chapter_title}

当前内容（需要扩展）：
{current_content[:500]}...

请在当前内容基础上，添加以下详细内容：

1. **详细数据分析**：添加3-5个具体的数据表格，包含历史数据、预测数据、区域对比数据
2. **案例分析**：添加2-3个具体的公司或技术案例分析
3. **专家观点**：引用2-3个行业专家或权威机构的观点
4. **趋势预测**：对未来3-5年的发展趋势进行详细预测
5. **风险提示**：分析该领域的主要风险和挑战

要求：
- 总字数增加到5000字以上
- 保持专业、客观、有深度的风格
- 使用Markdown格式
- 包含具体的数据和来源

请直接输出扩展后的内容，不要包含前言或后语。"""


async def expand_chapter(title: str, content: str) -> str:
    prompt = build_expansion_prompt(title, content)
    
    print(f"Expanding: {title}...", flush=True)
    
    result = await call_llm(
        prompt,
        model='mimo-v2.5',
        max_tokens=8192,
    )
    
    if result.get('success'):
        expanded = result.get('content', '')
        print(f"  Done ({len(content)} -> {len(expanded)} chars)", flush=True)
        return expanded
    else:
        print(f"  Failed: {result.get('error', 'unknown')}", flush=True)
        return content


async def main():
    print("=" * 60)
    print("Expanding semiconductor report chapters")
    print("=" * 60, flush=True)
    
    data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
    sections = data.get('sections', [])
    
    expanded_sections = []
    for i, section in enumerate(sections):
        title = section['title']
        content = section['content']
        
        if len(content) < 5000:
            expanded_content = await expand_chapter(title, content)
            expanded_sections.append({'title': title, 'content': expanded_content})
            
            # Save after each chapter
            data['sections'] = expanded_sections
            data['metadata']['total_chars'] = sum(len(s['content']) for s in expanded_sections)
            OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            expanded_sections.append(section)
            print(f"Skipping {title} (already {len(content)} chars)", flush=True)
    
    data['sections'] = expanded_sections
    data['metadata']['total_chars'] = sum(len(s['content']) for s in expanded_sections)
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    print("\n" + "=" * 60)
    print(f"Total chars: {data['metadata']['total_chars']}")
    print(f"Estimated pages: {data['metadata']['total_chars'] // 1500}")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
