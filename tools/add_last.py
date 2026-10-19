# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm
init_llm_infrastructure(settings.llm_profiles)
OUTPUT_FILE = Path("output/full_research/semiconductor_revised_report_llm.json")

async def main():
    prompt = """你是一位资深的行业研究分析师，请撰写"全球半导体行业深度研究报告"中的"投资建议与策略"章节。

要求：
1. 内容专业、客观、有深度
2. 包含具体数据（用表格呈现）
3. 包含投资机会、投资策略、重点领域推荐、风险提示
4. 使用Markdown格式
5. 总字数不少于6000字

请直接输出章节内容。"""
    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=8192)
    if result.get('success'):
        content = result.get('content', '')
        print(f"Done: {len(content)} chars", flush=True)
        data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))
        data['sections'].append({'title': '投资建议与策略', 'content': content})
        data['metadata']['total_chars'] = sum(len(s['content']) for s in data['sections'])
        data['metadata']['total_sections'] = len(data['sections'])
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Total: {data['metadata']['total_chars']}", flush=True)

asyncio.run(main())
