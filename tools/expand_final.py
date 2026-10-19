# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm

init_llm_infrastructure(settings.llm_profiles)

OUTPUT_FILE = Path("output/full_research/semiconductor_revised_report_llm.json")

async def expand_chapter(title, content):
    prompt = f"""你是一位资深的行业研究分析师，请为以下半导体行业研究报告章节添加更详细的内容。

当前章节标题：{title}

当前内容（请在此基础上扩展）：
{content}

请在当前内容基础上，添加以下详细内容：
1. 详细数据分析：添加3-5个具体的数据表格，包含历史数据、预测数据、区域对比
2. 案例分析：添加2-3个具体的公司案例（如台积电、英伟达、三星、中芯国际等）
3. 专家观点：引用2-3个行业专家或权威机构的观点
4. 趋势预测：对未来3-5年的发展趋势进行详细预测
5. 风险提示：分析该领域的主要风险和挑战

要求：
- 总字数增加到7000字以上
- 保持专业、客观、有深度的风格
- 使用Markdown格式
- 包含具体的数据和来源

请直接输出扩展后的完整内容。"""

    print(f"Expanding: {title}...", flush=True)
    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=8192)
    if result.get('success'):
        expanded = result.get('content', '')
        print(f"  Done ({len(content)} -> {len(expanded)} chars)", flush=True)
        return expanded
    else:
        print(f"  Failed: {result.get('error')}", flush=True)
        return content

async def main():
    data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
    sections = data.get('sections', [])
    
    expanded_sections = []
    for section in sections:
        title = section['title']
        content = section['content']
        
        if len(content) < 7000:
            expanded = await expand_chapter(title, content)
            expanded_sections.append({'title': title, 'content': expanded})
            
            # Save after each chapter
            data['sections'] = expanded_sections
            data['metadata']['total_chars'] = sum(len(s['content']) for s in expanded_sections)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            expanded_sections.append(section)
            print(f"Skipping {title} (already {len(content)} chars)", flush=True)
    
    data['sections'] = expanded_sections
    data['metadata']['total_chars'] = sum(len(s['content']) for s in expanded_sections)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTotal chars: {data['metadata']['total_chars']}", flush=True)

asyncio.run(main())
