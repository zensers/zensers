"""
从咨询公司报告中提取分析模板的独立脚本

用法:
    python tools/extract_analysis_templates.py --industry "农产品" --output templates/agriculture.json
    python tools/extract_analysis_templates.py --industry "消费电子" --output templates/consumer_electronics.json
    python tools/extract_analysis_templates.py --all --output templates/all.json

功能:
    1. 搜索指定行业的咨询公司报告
    2. 提取分析框架、数据需求、输出格式
    3. 生成模板文件供 Agent 使用
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# 配置
# ============================================================

# 咨询公司报告搜索关键词模板
SEARCH_QUERIES = {
    "农产品": [
        "McKinsey agriculture industry report 2024 2025",
        "BCG agricultural commodity analysis framework",
        "Goldman Sachs agricultural market research",
        "McKinsey food supply chain analysis",
        "BCG farming industry outlook",
    ],
    "消费电子": [
        "McKinsey consumer electronics report 2024 2025",
        "BCG smartphone market analysis framework",
        "Goldman Sachs technology hardware research",
        "McKinsey consumer technology trends",
        "BCG electronics industry outlook",
    ],
    "金融": [
        "McKinsey financial services report 2024 2025",
        "BCG banking industry analysis framework",
        "Goldman Sachs financial market research",
        "McKinsey fintech outlook",
        "BCG insurance industry trends",
    ],
    "医药": [
        "McKinsey pharmaceutical report 2024 2025",
        "BCG healthcare industry analysis",
        "Goldman Sachs biotech research",
        "McKinsey life sciences outlook",
        "BCG medical device trends",
    ],
    "新能源": [
        "McKinsey renewable energy report 2024 2025",
        "BCG clean energy analysis framework",
        "Goldman Sachs energy transition research",
        "McKinsey electric vehicle outlook",
        "BCG battery industry trends",
    ],
    "汽车": [
        "McKinsey automotive report 2024 2025",
        "BCG car industry analysis framework",
        "Goldman Sachs auto market research",
        "McKinsey autonomous driving outlook",
        "BCG electric vehicle trends",
    ],
    "房地产": [
        "McKinsey real estate report 2024 2025",
        "BCG property market analysis framework",
        "Goldman Sachs real estate research",
        "McKinsey housing market outlook",
        "BCG commercial real estate trends",
    ],
    "通用": [
        "McKinsey industry analysis methodology",
        "BCG strategy framework template",
        "Goldman Sachs sector research approach",
        "McKinsey market sizing methodology",
        "BCG competitive analysis framework",
    ],
}


# ============================================================
# 模板提取 Prompt
# ============================================================

TEMPLATE_EXTRACTION_PROMPT = """你是一位资深行业分析师。请从以下咨询公司报告内容中提取分析框架，生成标准化模板。

## 报告内容
{report_content}

## 提取要求

请提取以下信息并输出为 JSON 格式：

```json
{{
  "industry": "行业名称",
  "framework_name": "框架名称（如：供需平衡分析、价值链分析等）",
  "source": "报告来源（公司名+报告标题）",
  "dimensions": [
    {{
      "name": "维度名称",
      "description": "维度说明",
      "key_metrics": ["关键指标1", "关键指标2"],
      "data_sources": ["数据来源1", "数据来源2"]
    }}
  ],
  "analysis_steps": [
    "步骤1: ...",
    "步骤2: ..."
  ],
  "key_assumptions": [
    "假设1: ...",
    "假设2: ..."
  ],
  "output_format": {{
    "sections": ["章节1", "章节2"],
    "charts": ["图表类型1", "图表类型2"],
    "tables": ["表格类型1", "表格类型2"]
  }},
  "validation_methods": [
    "验证方法1: ...",
    "验证方法2: ..."
  ],
  "common_pitfalls": [
    "常见陷阱1: ...",
    "常见陷阱2: ..."
  ]
}}
```

## 注意事项
1. 只提取报告中明确提到的分析框架，不要编造
2. 如果报告中没有完整框架，只提取可用部分
3. 保持框架的原始逻辑顺序
4. 标注数据来源的权威性（官方/第三方/媒体）
"""

# ============================================================
# 模板合并 Prompt
# ============================================================

TEMPLATE_MERGE_PROMPT = """你是一位资深行业分析师。请将多个来源的分析模板合并为一个综合模板。

## 待合并模板
{templates}

## 合并要求

请生成一个综合模板，包含：
1. 各来源的共同维度（优先保留）
2. 各来源的独特维度（补充保留）
3. 去重后的分析步骤
4. 综合的数据需求
5. 综合的验证方法

输出格式与单个模板相同。

## 注意事项
1. 保留最权威来源的内容
2. 去除重复或矛盾的内容
3. 保持逻辑一致性
4. 综合各来源的优势
"""


# ============================================================
# 工具函数
# ============================================================

def search_reports(industry: str, max_results: int = 5) -> list:
    """搜索咨询公司报告（模拟）"""
    queries = SEARCH_QUERIES.get(industry, SEARCH_QUERIES["通用"])
    results = []
    
    # 这里应该调用搜索 API，现在返回示例数据
    print(f"  搜索 {industry} 行业的咨询报告...")
    for query in queries[:max_results]:
        print(f"    查询: {query}")
        # 实际实现中，这里应该调用搜索 API
        # results.extend(web_search(query))
    
    return results


def extract_template_from_content(content: str, source: str) -> dict:
    """从报告内容中提取模板"""
    # 这里应该调用 LLM API，现在返回示例模板
    template = {
        "industry": "待填充",
        "framework_name": "待填充",
        "source": source,
        "dimensions": [],
        "analysis_steps": [],
        "key_assumptions": [],
        "output_format": {},
        "validation_methods": [],
        "common_pitfalls": []
    }
    return template


def merge_templates(templates: list) -> dict:
    """合并多个模板"""
    if not templates:
        return {}
    
    # 简单合并逻辑（实际应该用 LLM）
    merged = templates[0].copy()
    for t in templates[1:]:
        # 合并 dimensions
        for dim in t.get("dimensions", []):
            if dim["name"] not in [d["name"] for d in merged["dimensions"]]:
                merged["dimensions"].append(dim)
        # 合并 analysis_steps
        for step in t.get("analysis_steps", []):
            if step not in merged["analysis_steps"]:
                merged["analysis_steps"].append(step)
    
    return merged


def save_template(template: dict, output_path: str):
    """保存模板到文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"  模板已保存到: {output_path}")


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='从咨询公司报告中提取分析模板')
    parser.add_argument('--industry', type=str, help='行业名称（如：农产品、消费电子）')
    parser.add_argument('--all', action='store_true', help='提取所有行业的模板')
    parser.add_argument('--output', type=str, default='templates/industry_templates.json',
                       help='输出文件路径')
    parser.add_argument('--max-reports', type=int, default=5,
                       help='每个行业最大报告数量')
    
    args = parser.parse_args()
    
    if not args.industry and not args.all:
        parser.print_help()
        return
    
    industries = list(SEARCH_QUERIES.keys()) if args.all else [args.industry]
    all_templates = {}
    
    for industry in industries:
        print(f"\n{'='*60}")
        print(f"处理行业: {industry}")
        print(f"{'='*60}")
        
        # 搜索报告
        reports = search_reports(industry, args.max_reports)
        
        # 提取模板
        templates = []
        for report in reports:
            print(f"  提取模板: {report.get('title', '未知')}")
            template = extract_template_from_content(
                report.get('content', ''),
                report.get('source', '未知')
            )
            templates.append(template)
        
        # 合并模板
        if templates:
            merged = merge_templates(templates)
            merged["industry"] = industry
            all_templates[industry] = merged
            print(f"  ✓ 生成综合模板: {len(merged.get('dimensions', []))} 个维度")
        else:
            print(f"  ✗ 未找到报告，跳过")
    
    # 保存模板
    save_template(all_templates, args.output)
    
    print(f"\n{'='*60}")
    print(f"完成！共生成 {len(all_templates)} 个行业模板")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
