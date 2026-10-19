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
    data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))
    titles = [s['title'] for s in data['sections']]
    
    prompt = f"""基于以下半导体行业研究章节标题，生成5-7个关键发现（每个发现不超过50字）：

章节列表：
{chr(10).join(f"- {t}" for t in titles)}

请直接输出，每行一个发现，不要编号。"""
    
    result = await call_llm(prompt, model='mimo-v2.5', max_tokens=2000)
    if result.get('success'):
        findings = [line.strip().lstrip('0123456789.- ') for line in result.get('content', '').split('\n') if line.strip()]
        data['key_findings'] = findings
        with open('output/full_research/semiconductor_revised_report_llm.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'Generated {len(findings)} key findings')
        for f in findings:
            print(f'  - {f}')

asyncio.run(main())
