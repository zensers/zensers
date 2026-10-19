# -*- coding: utf-8 -*-
"""
半导体行业报告内容生成器
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


def build_chapter_prompt(chapter_title: str, chapter_scope: str) -> str:
    return f"""你是一位资深的行业研究分析师，请撰写一份关于"{TOPIC}"的深度研究报告中的"{chapter_title}"章节。

章节要求覆盖内容：{chapter_scope}

要求：
1. 内容必须专业、客观、有深度，符合国际咨询公司（麦肯锡、波士顿咨询）的研究报告水平
2. 必须包含具体的数据、图表信息（用表格呈现）
3. 每个章节至少包含3-4个二级标题
4. 使用Markdown格式，二级标题用 ##，三级标题用 ###
5. 数据要具体（如：2024年全球半导体市场规模达到6270亿美元，同比增长19.2%）
6. 包含表格来展示关键数据
7. 总字数不少于3000字

请直接输出章节内容，不要包含任何前言或后语。"""


async def generate_chapter(index: int, chapter_title: str, chapter_scope: str) -> str:
    prompt = build_chapter_prompt(chapter_title, chapter_scope)
    
    print(f"  [{index+1}/8] Generating: {chapter_title}...")
    
    result = await call_llm(
        prompt,
        model='mimo-v2.5',
        max_tokens=8192,
    )
    
    if result.get('success'):
        content = result.get('content', '')
        print(f"    Done ({len(content)} chars)")
        return content
    else:
        print(f"    Failed: {result.get('error', 'unknown')}")
        return f"[Generation failed: {result.get('error', 'unknown')}]"


async def main():
    print("=" * 60)
    print("Generating semiconductor industry research report content")
    print(f"Topic: {TOPIC}")
    print("=" * 60)
    
    sections = []
    for i, (title, scope) in enumerate(CHAPTERS):
        content = await generate_chapter(i, title, scope)
        sections.append({
            "title": title,
            "content": content,
        })
    
    # Generate key findings
    print("\n  Generating key findings...")
    findings_prompt = f"""Based on the following semiconductor industry research chapter titles, generate 5-7 key findings (each finding no more than 50 words):

Chapter list:
{chr(10).join(f"- {s['title']}" for s in sections)}

Please output directly, one finding per line, no numbering."""
    
    findings_result = await call_llm(findings_prompt, model='mimo-v2.5', max_tokens=2000)
    key_findings = []
    if findings_result.get('success'):
        for line in findings_result.get('content', '').split('\n'):
            line = line.strip().lstrip('0123456789.- ')
            if line:
                key_findings.append(line)
    
    report = {
        "topic": TOPIC,
        "generated_at": datetime.now().isoformat(),
        "sections": sections,
        "key_findings": key_findings,
        "metadata": {
            "total_chars": sum(len(s['content']) for s in sections),
            "total_sections": len(sections),
        }
    }
    
    output_file = Path("output/full_research/semiconductor_research_result.json")
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    
    print("\n" + "=" * 60)
    print(f"Research result saved: {output_file}")
    print(f"Total characters: {report['metadata']['total_chars']}")
    print(f"Total sections: {len(sections)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
