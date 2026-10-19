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

OUTPUT_FILE = Path("output/full_research/ai_revised_report_llm.json")

CHAPTERS = [
    ("技术趋势分析", "大语言模型、多模态AI、具身智能、AI Agent、边缘AI等技术发展趋势"),
    ("政策环境与监管分析", "全球主要国家AI政策、中国AI发展战略、AI伦理与监管、数据安全"),
    ("风险分析", "AI行业面临的主要风险（技术风险、伦理风险、监管风险、市场风险）"),
    ("投资建议与策略", "AI行业投资机会、投资策略、重点领域推荐、风险提示"),
]

async def generate_chapter(title, scope):
    prompt = f"""你是一位资深的行业研究分析师，请撰写一份关于"全球人工智能行业深度研究报告"的"{title}"章节。

章节要求覆盖内容：{scope}

要求：
1. 内容必须专业、客观、有深度
2. 必须包含具体的数据（用表格呈现关键数据）
3. 每个章节包含3-4个二级标题
4. 使用Markdown格式，二级标题用 ##，三级标题用 ###
5. 数据要具体
6. 总字数不少于3000字

请直接输出章节内容。"""

    print(f"Generating: {title}...", flush=True)
    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=8192)
    if result.get('success'):
        content = result.get('content', '')
        print(f"  Done ({len(content)} chars)", flush=True)
        return content
    else:
        print(f"  Failed: {result.get('error')}", flush=True)
        return ""

async def main():
    data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
    existing_titles = {s['title'] for s in data.get('sections', [])}
    
    for title, scope in CHAPTERS:
        if title in existing_titles:
            print(f"Skipping {title} (already exists)", flush=True)
            continue
        
        content = await generate_chapter(title, scope)
        if content:
            data['sections'].append({'title': title, 'content': content})
            data['metadata']['total_chars'] = sum(len(s['content']) for s in data['sections'])
            data['metadata']['total_sections'] = len(data['sections'])
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTotal chars: {data['metadata']['total_chars']}", flush=True)

asyncio.run(main())
