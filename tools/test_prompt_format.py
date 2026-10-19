# -*- coding: utf-8 -*-
"""测试新Prompt配置是否生成专业格式"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure, call_llm

# 初始化LLM
init_llm_infrastructure(settings.llm_profiles)


async def test_prompt_format():
    """测试新的写作风格Prompt"""
    
    # 新的写作风格要求
    system_prompt = """你是一位专业的行业研究分析师，遵循麦肯锡/BCG/德勤等顶级咨询公司的报告标准。

写作风格要求：
1. 使用结构化分析框架（PEST、波特五力、SWOT等）
2. 每个章节包含：概述→详细分析→关键发现→战略启示
3. 数据通过表格和图表呈现，不仅仅是文字
4. 使用专业商业术语，避免学术或口语化表达
5. 禁止使用"核心结论"、"论证与分析"等学术风格术语

输出格式示例：
## 市场规模与竞争格局

### 概述
中国新能源汽车市场在2025年实现了历史性突破...

### 详细分析

#### 1. 市场规模
| 指标 | 2024年 | 2025年 | 同比增长 |
|------|--------|--------|----------|
| 销量（万辆） | 742 | 1,020 | 37.5% |
| 渗透率 | 31.6% | 47.9% | +16.3ppt |

市场规模的增长主要得益于...

#### 2. 竞争格局
| 排名 | 品牌 | 销量（万辆） | 市占率 |
|------|------|-------------|--------|
| 1 | 比亚迪 | 427.2 | 41.9% |
| 2 | 特斯拉 | 65.7 | 6.4% |

比亚迪凭借...

### 关键发现
- 市场渗透率突破47%，标志着从政策驱动转向市场驱动
- 比亚迪市占率超过40%，行业集中度提升
- 插混技术成为新增长引擎，出口增长230%

### 战略启示
- 对整车企业：需要构建"电动化+智能化+全球化"全栈能力
- 对投资者：关注具备核心技术定义权的产业链环节"""

    prompt = """请分析中国新能源汽车行业的"市场规模与竞争格局"，要求：
1. 包含市场规模数据（销量、渗透率、增长率）
2. 包含竞争格局分析（主要玩家、市占率、竞争策略）
3. 使用表格呈现数据
4. 每个部分有清晰的分析和洞察
5. 避免使用"核心结论"、"论证与分析"等格式"""

    response = await call_llm(
        prompt=prompt,
        system_prompt=system_prompt,
        model='mimo-v2.5',
        max_tokens=4000
    )
    
    content = response.get('content', '')
    
    # 保存结果
    with open('output/prompt_test_result.md', 'w', encoding='utf-8') as f:
        f.write('# Prompt格式测试结果\n\n')
        f.write('## 系统Prompt\n\n')
        f.write(system_prompt + '\n\n')
        f.write('## 用户Prompt\n\n')
        f.write(prompt + '\n\n')
        f.write('## 生成结果\n\n')
        f.write(content)
    
    print('测试结果已保存到 output/prompt_test_result.md')
    print()
    print('内容长度:', len(content), '字符')
    print()
    
    # 检查是否还有旧格式
    if '核心结论' in content:
        print('WARNING: 仍然包含"核心结论"格式')
    if '论证与分析' in content:
        print('WARNING: 仍然包含"论证与分析"格式')
    if '数据支撑' in content:
        print('WARNING: 仍然包含"数据支撑"格式')
    
    # 检查是否包含新格式
    if '概述' in content:
        print('OK: 包含"概述"部分')
    if '详细分析' in content:
        print('OK: 包含"详细分析"部分')
    if '关键发现' in content:
        print('OK: 包含"关键发现"部分')
    if '战略启示' in content:
        print('OK: 包含"战略启示"部分')
    
    return content


if __name__ == '__main__':
    asyncio.run(test_prompt_format())
