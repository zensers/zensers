# -*- coding: utf-8 -*-
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

async def main():
    prompt = """请撰写一份关于全球半导体行业的投资建议与策略章节。

要求：
1. 内容必须专业、客观、有深度
2. 必须包含具体的数据（用表格呈现关键数据）
3. 包含投资机会、投资策略、重点领域推荐、风险提示
4. 使用Markdown格式
5. 总字数不少于2500字

请直接输出章节内容，不要包含任何前言或后语。"""
    
    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=6000)
    if result.get('success'):
        content = result.get('content', '')
        print(f'Done: {len(content)} chars')
        
        # Load existing and add the last chapter
        data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))
        data['sections'].append({'title': '投资建议与策略', 'content': content})
        data['metadata']['total_chars'] = sum(len(s['content']) for s in data['sections'])
        data['metadata']['total_sections'] = len(data['sections'])
        
        with open('output/full_research/semiconductor_revised_report_llm.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'Total chars: {data["metadata"]["total_chars"]}')

asyncio.run(main())
