# -*- coding: utf-8 -*-
"""
AI行业报告内容生成器
使用LLM生成真实、专业的行业研究内容
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

TOPIC = "全球人工智能行业深度研究报告"

CHAPTERS = [
    ("行业概览", "人工智能的定义、分类（机器学习、深度学习、NLP、计算机视觉等）、发展历程、技术演进、全球市场格局"),
    ("市场规模深度分析", "全球及中国AI市场规模、增长趋势、细分市场结构（软件、硬件、服务）、区域分布、历史数据与未来预测"),
    ("产业链深度分析", "AI产业链上游（算力、数据）、中游（算法、模型）、下游（应用场景）深度解析"),
    ("竞争格局分析", "全球AI企业竞争格局（OpenAI、Google、Microsoft、百度、阿里等）、市场份额、并购整合"),
    ("技术趋势分析", "大语言模型、多模态AI、具身智能、AI Agent、边缘AI等技术发展趋势"),
    ("政策环境与监管分析", "全球主要国家AI政策、中国AI发展战略、AI伦理与监管、数据安全"),
    ("风险分析", "AI行业面临的主要风险（技术风险、伦理风险、监管风险、市场风险）"),
    ("投资建议与策略", "AI行业投资机会、投资策略、重点领域推荐、风险提示"),
]

OUTPUT_FILE = Path("output/full_research/ai_revised_report_llm.json")


def build_chapter_prompt(chapter_title: str, chapter_scope: str) -> str:
    return f"""你是一位资深的行业研究分析师，请撰写一份关于"{TOPIC}"的深度研究报告中的"{chapter_title}"章节。

章节要求覆盖内容：{chapter_scope}

要求：
1. 内容必须专业、客观、有深度，符合国际咨询公司（麦肯锡、波士顿咨询）的研究报告水平
2. 必须包含具体的数据（用表格呈现关键数据）
3. 每个章节包含3-4个二级标题
4. 使用Markdown格式，二级标题用 ##，三级标题用 ###
5. 数据要具体（如：2024年全球AI市场规模达到xxxx亿美元，同比增长xx%）
6. 包含表格来展示关键数据
7. 总字数不少于3000字

请直接输出章节内容，不要包含任何前言或后语。"""


async def generate_chapter(index: int, chapter_title: str, chapter_scope: str) -> str:
    prompt = build_chapter_prompt(chapter_title, chapter_scope)
    
    print(f"[{index+1}/8] Generating: {chapter_title}...", flush=True)
    
    result = await call_llm(
        prompt,
        model='mimo-v2.5',
        max_tokens=8192,
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
    print("Generating AI Industry Research Report Content")
    print(f"Topic: {TOPIC}")
    print("=" * 60, flush=True)
    
    sections = []
    for i, (title, scope) in enumerate(CHAPTERS):
        content = await generate_chapter(i, title, scope)
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
    print(f"Total chars: {report['metadata']['total_chars']}")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
