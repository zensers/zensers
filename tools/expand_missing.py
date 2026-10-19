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

OUTPUT_FILE = Path("output/full_research/semiconductor_revised_report_llm.json")

async def expand_chapter(title, content):
    prompt = f"""你是一位资深的行业研究分析师，请为以下半导体行业研究报告章节添加更详细的内容。

当前章节标题：{title}

当前内容：{content[:500]}...

请在当前内容基础上，添加以下详细内容：
1. 详细数据分析：添加3-5个具体的数据表格
2. 案例分析：添加2-3个具体的公司或技术案例
3. 专家观点：引用2-3个行业专家或权威机构的观点
4. 趋势预测：对未来3-5年的发展趋势进行详细预测
5. 风险提示：分析该领域的主要风险和挑战

要求：
- 总字数增加到5000字以上
- 保持专业、客观、有深度的风格
- 使用Markdown格式
- 包含具体的数据和来源

请直接输出扩展后的内容。"""

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
    
    # Expand missing chapters
    missing = [('风险分析', ''), ('投资建议与策略', '')]
    for title, content in missing:
        # Check if already exists
        existing = [s for s in sections if s['title'] == title]
        if existing and len(existing[0]['content']) > 4000:
            print(f"Skipping {title} (already exists)", flush=True)
            continue
        
        expanded = await expand_chapter(title, content if content else f"半导体行业{title}的详细分析")
        sections.append({'title': title, 'content': expanded})
    
    data['sections'] = sections
    data['metadata']['total_chars'] = sum(len(s['content']) for s in sections)
    data['metadata']['total_sections'] = len(sections)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Total chars: {data['metadata']['total_chars']}", flush=True)

asyncio.run(main())
