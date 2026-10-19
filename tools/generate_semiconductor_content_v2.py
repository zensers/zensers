# -*- coding: utf-8 -*-
"""
半导体行业报告内容生成器（优化版）
分块生成，保存中间结果
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm

init_llm_infrastructure(settings.llm_profiles)

TOPIC = "全球半导体行业深度研究报告"

CHAPTERS = [
    ("行业概览", "全球半导体行业的定义、分类、发展历程、产业链结构、技术演进、全球市场格局"),
    ("市场规模深度分析", "全球及中国半导体市场规模、增长趋势、细分市场结构、区域分布、历史数据与未来预测"),
    ("产业链深度分析", "半导体产业链上游（材料、设备）、中游（设计、制造、封测）、下游（应用领域）深度解析"),
    ("竞争格局分析", "全球半导体企业竞争格局、市场份额、并购整合、中国半导体企业竞争力分析"),
    ("技术趋势分析", "先进制程、新材料、新架构、AI芯片、第三代半导体等技术发展趋势"),
    ("政策环境与监管分析", "全球主要国家半导体政策、中国支持政策、出口管制、产业链安全"),
    ("风险分析", "半导体行业面临的主要风险、周期性风险、地缘政治风险、技术风险"),
    ("投资建议与策略", "半导体行业投资机会、投资策略、重点领域推荐、风险提示"),
]

OUTPUT_FILE = Path("output/full_research/semiconductor_research_result.json")


def build_chapter_prompt(chapter_title: str, chapter_scope: str) -> str:
    return f"""你是一位资深的行业研究分析师，请撰写一份关于"{TOPIC}"的深度研究报告中的"{chapter_title}"章节。

章节要求覆盖内容：{chapter_scope}

要求：
1. 内容必须专业、客观、有深度，符合国际咨询公司的研究报告水平
2. 必须包含具体的数据（用表格呈现关键数据）
3. 每个章节包含3-4个二级标题
4. 使用Markdown格式，二级标题用 ##，三级标题用 ###
5. 数据要具体（如：2024年全球半导体市场规模达到6270亿美元，同比增长19.2%）
6. 总字数不少于2500字

请直接输出章节内容，不要包含任何前言或后语。"""


async def generate_chapter(index: int, chapter_title: str, chapter_scope: str) -> str:
    prompt = build_chapter_prompt(chapter_title, chapter_scope)
    
    print(f"[{index+1}/8] Generating: {chapter_title}...", flush=True)
    
    result = await call_llm(
        prompt,
        model='mimo-v2.5',
        max_tokens=6000,
    )
    
    if result.get('success'):
        content = result.get('content', '')
        print(f"  Done ({len(content)} chars)", flush=True)
        return content
    else:
        print(f"  Failed: {result.get('error', 'unknown')}", flush=True)
        return f"[Generation failed]"


async def main():
    print("=" * 60)
    print("Generating semiconductor industry research report content")
    print("=" * 60, flush=True)
    
    # Load existing results if available
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
        sections = existing.get('sections', [])
    else:
        sections = []
    
    # Generate chapters one by one
    for i, (title, scope) in enumerate(CHAPTERS):
        # Skip if already generated and has sufficient length
        if i < len(sections) and len(sections[i].get('content', '')) > 4000:
            print(f"[{i+1}/8] Skipping: {title} (already exists, {len(sections[i]['content'])} chars)", flush=True)
            continue
        
        content = await generate_chapter(i, title, scope)
        
        if i < len(sections):
            sections[i]['content'] = content
        else:
            sections.append({"title": title, "content": content})
        
        # Save after each chapter
        report = {
            "topic": TOPIC,
            "generated_at": datetime.now().isoformat(),
            "sections": sections,
            "key_findings": [],
            "metadata": {
                "total_chars": sum(len(s['content']) for s in sections),
                "total_sections": len(sections),
            }
        }
        OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  Saved ({report['metadata']['total_chars']} total chars)", flush=True)
    
    print("\n" + "=" * 60)
    print("All chapters generated!")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
