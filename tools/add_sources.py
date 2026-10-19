# -*- coding: utf-8 -*-
"""
Add data source citations to chapters missing them
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


async def add_data_sources(title, content):
    """Add data source citations"""
    prompt = f"""为以下半导体行业研究报告章节添加数据来源引用。

章节标题：{title}
当前内容：{content[:500]}...

要求：
1. 在适当位置添加3-5个数据来源引用
2. 来源包括：WSTS、SIA、Gartner、IDC、IC Insights、SEMI等权威机构
3. 使用"数据来源：XXX"或"（来源：XXX）"格式
4. 每个来源引用50-100字

请直接输出需要添加的来源引用内容。"""

    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=1000)
    if result.get('success'):
        return result.get('content', '')
    return ""


async def main():
    data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
    
    # Fix Chapter 5
    print("Fixing Chapter 5: 技术趋势分析 - adding data sources...", flush=True)
    ch5 = data['sections'][4]
    sources = await add_data_sources(ch5['title'], ch5['content'])
    if sources:
        ch5['content'] = ch5['content'] + '\n\n' + sources
        print(f"  Added sources ({len(sources)} chars)", flush=True)
    
    # Fix Chapter 8
    print("Fixing Chapter 8: 投资建议与策略 - adding data sources...", flush=True)
    ch8 = data['sections'][7]
    sources = await add_data_sources(ch8['title'], ch8['content'])
    if sources:
        ch8['content'] = ch8['content'] + '\n\n' + sources
        print(f"  Added sources ({len(sources)} chars)", flush=True)
    
    # Update metadata
    data['metadata']['total_chars'] = sum(len(s['content']) for s in data['sections'])
    
    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTotal chars: {data['metadata']['total_chars']}", flush=True)


asyncio.run(main())
