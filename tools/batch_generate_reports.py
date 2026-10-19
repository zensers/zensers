# -*- coding: utf-8 -*-
"""
zensers 批量报告生成脚本

批量生成行业研究报告。
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# 批量生成任务配置
BATCH_TASKS = [
    {
        "topic": "中国人工智能行业",
        "framework": "行业分析",
        "description": "AI行业深度研究报告",
    },
    {
        "topic": "中国半导体行业",
        "framework": "行业分析",
        "description": "半导体行业深度研究报告",
    },
    {
        "topic": "中国新能源汽车行业",
        "framework": "行业分析",
        "description": "新能源汽车行业深度研究报告",
    },
    {
        "topic": "中国医药健康行业",
        "framework": "行业分析",
        "description": "医药健康行业深度研究报告",
    },
    {
        "topic": "中国金融科技行业",
        "framework": "行业分析",
        "description": "金融科技行业深度研究报告",
    },
]


async def generate_single_report(task: dict, index: int) -> dict:
    """生成单个报告"""
    from tools.generate_commercial_report import generate_report
    
    topic = task["topic"]
    framework = task["framework"]
    output_dir = f"output/batch_reports/{topic.replace(' ', '_')}"
    
    print(f"\n[{index+1}/{len(BATCH_TASKS)}] 开始生成: {topic}")
    print(f"  框架: {framework}")
    print(f"  输出: {output_dir}")
    
    result = await generate_report(
        topic=topic,
        framework_name=framework,
        output_dir=output_dir,
    )
    
    if result.get("success"):
        print(f"  [OK] 成功: {topic}")
    else:
        print(f"  [FAIL] 失败: {topic} - {result.get('error')}")
    
    return {
        "task": task,
        "result": result,
    }


async def batch_generate():
    """批量生成报告"""
    print("=" * 60)
    print("zensers 批量报告生成")
    print("=" * 60)
    print(f"任务数量: {len(BATCH_TASKS)}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = []
    
    for i, task in enumerate(BATCH_TASKS):
        result = await generate_single_report(task, i)
        results.append(result)
        
        # 等待一段时间，避免API限流
        if i < len(BATCH_TASKS) - 1:
            print("  等待5秒避免限流...")
            await asyncio.sleep(5)
    
    # 统计结果
    success_count = sum(1 for r in results if r["result"].get("success"))
    fail_count = len(results) - success_count
    
    print("\n" + "=" * 60)
    print("批量生成完成")
    print("=" * 60)
    print(f"成功: {success_count}/{len(results)}")
    print(f"失败: {fail_count}/{len(results)}")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 保存结果摘要
    summary = {
        "batch_time": datetime.now().isoformat(),
        "total_tasks": len(BATCH_TASKS),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": [
            {
                "topic": r["task"]["topic"],
                "success": r["result"].get("success", False),
                "output_dir": r["result"].get("output_dir"),
                "error": r["result"].get("error"),
            }
            for r in results
        ],
    }
    
    summary_file = ROOT / "output" / "batch_reports" / "batch_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n结果摘要: {summary_file}")
    
    return summary


def main():
    """命令行入口"""
    asyncio.run(batch_generate())


if __name__ == "__main__":
    main()
