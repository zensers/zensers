# -*- coding: utf-8 -*-
"""
直接使用LLM修订报告，增加内容量
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

# 初始化LLM
init_llm_infrastructure(settings.llm_profiles)


async def revise_chapter_with_llm(chapter_title, chapter_content):
    """使用LLM修订单个章节"""
    
    prompt = f"""你是一位专业的行业研究分析师，请对以下章节进行修订，使其更加详细和专业。

## 当前章节标题
{chapter_title}

## 当前章节内容
{chapter_content}

## 修订要求
1. 增加更多数据支撑，包括具体的市场规模数字、增长率、市场份额等
2. 增加数据表格，展示历史数据和预测数据
3. 改进内容结构，确保有清晰的概述、详细分析、关键发现和战略启示
4. 删除重复内容
5. 确保数据一致性
6. 增加专业术语和分析框架
7. 每个章节至少3000字符

## 输出格式
请直接输出修订后的完整章节内容，不要包含"修订后的章节"等前缀。"""

    response = await call_llm(
        prompt=prompt,
        model='mimo-v2.5',
        max_tokens=4000
    )
    
    return response.get('content', '')


async def revise_report():
    """修订整个报告"""
    print("=" * 60)
    print("开始使用LLM修订报告")
    print("=" * 60)
    
    # 加载研究结果
    research_file = Path("output/full_research/semiconductor_research_result.json")
    if not research_file.exists():
        print("研究结果文件不存在")
        return
    
    research_data = json.loads(research_file.read_text(encoding="utf-8"))
    
    sections = research_data.get("sections", [])
    revised_sections = []
    
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
        content = section.get("content", "")
        
        print(f"\n[{i}/{len(sections)}] 修订章节: {title}")
        print(f"  当前内容长度: {len(content)} 字符")
        
        try:
            revised_content = await revise_chapter_with_llm(title, content)
            print(f"  修订后内容长度: {len(revised_content)} 字符")
            
            revised_sections.append({
                "id": section.get("id", ""),
                "title": title,
                "content": revised_content,
            })
            
        except Exception as e:
            print(f"  修订失败: {e}")
            revised_sections.append(section)
    
    # 保存修订后的报告
    revised_report = {
        "topic": "中国新能源汽车行业深度研究",
        "sections": revised_sections,
    }
    
    revised_file = Path("output/full_research/revised_report_llm.json")
    revised_file.write_text(json.dumps(revised_report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("修订完成!")
    print(f"修订后报告: {revised_file}")
    print("=" * 60)
    
    return revised_report


if __name__ == "__main__":
    asyncio.run(revise_report())
