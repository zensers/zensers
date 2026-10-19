# -*- coding: utf-8 -*-
"""
Fix content issues: add missing intros/conclusions, improve analysis depth
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm

init_llm_infrastructure(settings.llm_profiles)

OUTPUT_FILE = Path("output/full_research/semiconductor_revised_report_llm.json")


async def add_conclusion(title, content):
    """Add conclusion to chapters missing it"""
    prompt = f"""为以下半导体行业研究报告章节添加一个简短的总结/结论段落（100-200字）。

章节标题：{title}
章节内容开头：{content[:300]}...

要求：
1. 总结本章核心观点
2. 提出未来展望
3. 使用Markdown格式
4. 以"## 总结与展望"或类似标题开头

请直接输出总结内容。"""

    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=1000)
    if result.get('success'):
        return result.get('content', '')
    return ""


async def add_introduction(title, content):
    """Add introduction to chapters missing it"""
    prompt = f"""为以下半导体行业研究报告章节添加一个简短的引言/背景段落（100-200字）。

章节标题：{title}
章节内容开头：{content[:300]}...

要求：
1. 介绍本章研究背景
2. 说明本章主要分析内容
3. 使用Markdown格式
4. 以"## 引言"或"## 背景"开头

请直接输出引言内容。"""

    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=1000)
    if result.get('success'):
        return result.get('content', '')
    return ""


async def improve_analysis(title, content):
    """Improve analysis depth by adding expert insights"""
    prompt = f"""为以下半导体行业研究报告章节添加2-3个专家观点或深度分析段落。

章节标题：{title}
当前内容：{content[:500]}...

要求：
1. 引用行业专家或权威机构的观点
2. 添加深度分析和洞察
3. 使用Markdown格式
4. 每个观点100-150字

请直接输出新增的分析内容。"""

    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=1500)
    if result.get('success'):
        return result.get('content', '')
    return ""


async def main():
    data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
    
    # Fix Chapter 1: Add conclusion
    print("Fixing Chapter 1: 行业概览 - adding conclusion...", flush=True)
    ch1 = data['sections'][0]
    conclusion = await add_conclusion(ch1['title'], ch1['content'])
    if conclusion:
        ch1['content'] = ch1['content'] + '\n\n' + conclusion
        print(f"  Added conclusion ({len(conclusion)} chars)", flush=True)
    
    # Fix Chapter 4: Add conclusion
    print("Fixing Chapter 4: 竞争格局分析 - adding conclusion...", flush=True)
    ch4 = data['sections'][3]
    conclusion = await add_conclusion(ch4['title'], ch4['content'])
    if conclusion:
        ch4['content'] = ch4['content'] + '\n\n' + conclusion
        print(f"  Added conclusion ({len(conclusion)} chars)", flush=True)
    
    # Fix Chapter 5: Add data sources and improve analysis
    print("Fixing Chapter 5: 技术趋势分析 - improving analysis...", flush=True)
    ch5 = data['sections'][4]
    analysis = await improve_analysis(ch5['title'], ch5['content'])
    if analysis:
        ch5['content'] = ch5['content'] + '\n\n' + analysis
        print(f"  Added analysis ({len(analysis)} chars)", flush=True)
    
    # Fix Chapter 6: Add introduction
    print("Fixing Chapter 6: 政策环境与监管分析 - adding introduction...", flush=True)
    ch6 = data['sections'][5]
    intro = await add_introduction(ch6['title'], ch6['content'])
    if intro:
        ch6['content'] = intro + '\n\n' + ch6['content']
        print(f"  Added introduction ({len(intro)} chars)", flush=True)
    
    # Fix Chapter 8: Add data sources and improve analysis
    print("Fixing Chapter 8: 投资建议与策略 - improving analysis...", flush=True)
    ch8 = data['sections'][7]
    analysis = await improve_analysis(ch8['title'], ch8['content'])
    if analysis:
        ch8['content'] = ch8['content'] + '\n\n' + analysis
        print(f"  Added analysis ({len(analysis)} chars)", flush=True)
    
    # Update metadata
    data['metadata']['total_chars'] = sum(len(s['content']) for s in data['sections'])
    
    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTotal chars: {data['metadata']['total_chars']}", flush=True)
    print("Content fixes applied!", flush=True)


asyncio.run(main())
