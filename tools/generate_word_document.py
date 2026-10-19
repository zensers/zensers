# -*- coding: utf-8 -*-
"""
zensers Word 文档生成脚本

使用 zensers 的正确流程：JSON → HTML → Word
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def generate_word_document(
    report_json_path: str,
    output_path: str = None,
    template_name: str = "word_default",
) -> dict:
    """
    使用 zensers 流程生成 Word 文档
    
    Args:
        report_json_path: report.json 文件路径
        output_path: 输出 Word 文件路径（可选）
        template_name: 模板名称（默认 word_default）
    
    Returns:
        生成结果
    """
    from src.content.content_orchestrator import ContentOrchestrator
    from src.converters.html_to_word import HTMLToWordConverter
    
    # 加载报告数据
    report_file = Path(report_json_path)
    if not report_file.exists():
        return {"error": f"报告文件不存在: {report_json_path}"}
    
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    
    # 设置输出路径
    if output_path:
        out_path = Path(output_path)
    else:
        out_path = report_file.parent / f"{report_file.stem}.docx"
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"开始生成 Word 文档...")
    print(f"  输入: {report_json_path}")
    print(f"  输出: {out_path}")
    print(f"  模板: {template_name}")
    
    try:
        # 1. 使用 ContentOrchestrator 转换为 HTML
        print("  [1/2] 转换为 HTML...")
        orchestrator = ContentOrchestrator()
        
        html_content = orchestrator.transform_to_html(
            research_result=report_data,
            output_format="docx",
            template_name=template_name,
        )
        
        if not html_content:
            return {"error": "HTML 转换失败"}
        
        # 2. 使用 HTMLToWordConverter 转换为 Word
        print("  [2/2] 转换为 Word...")
        converter = HTMLToWordConverter()
        
        result = converter.convert(
            html=html_content,
            output_path=str(out_path),
        )
        
        if result.success:
            print(f"✅ Word 文档生成成功!")
            print(f"  文件: {result.output_path}")
            print(f"  大小: {result.file_size} bytes")
            print(f"  预计页数: {result.pages_estimate}")
            
            return {
                "success": True,
                "input_file": report_json_path,
                "output_file": result.output_path,
                "file_size": result.file_size,
                "pages_estimate": result.pages_estimate,
            }
        else:
            return {"error": f"Word 转换失败: {result.error}"}
            
    except Exception as e:
        return {"error": f"生成失败: {str(e)}"}


async def batch_convert_to_word(
    reports_dir: str = None,
    template_name: str = "word_default",
) -> dict:
    """
    批量将报告转换为 Word 文档
    
    Args:
        reports_dir: 报告目录（默认 output/batch_reports）
        template_name: 模板名称
    
    Returns:
        批量转换结果
    """
    if reports_dir:
        batch_dir = Path(reports_dir)
    else:
        batch_dir = ROOT / "output" / "batch_reports"
    
    if not batch_dir.exists():
        return {"error": f"目录不存在: {batch_dir}"}
    
    results = []
    
    # 遍历所有报告目录
    for report_dir in batch_dir.iterdir():
        if not report_dir.is_dir():
            continue
        
        report_json = report_dir / "report.json"
        if not report_json.exists():
            continue
        
        print(f"\n处理: {report_dir.name}")
        
        result = await generate_word_document(
            report_json_path=str(report_json),
            output_path=str(report_dir / f"{report_dir.name}.docx"),
            template_name=template_name,
        )
        
        results.append({
            "topic": report_dir.name,
            "result": result,
        })
    
    # 统计结果
    success_count = sum(1 for r in results if r["result"].get("success"))
    fail_count = len(results) - success_count
    
    print(f"\n批量转换完成: {success_count}/{len(results)} 成功")
    
    return {
        "total": len(results),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="zensers Word 文档生成脚本")
    parser.add_argument("--report", help="单个报告 JSON 文件路径")
    parser.add_argument("--batch", action="store_true", help="批量转换模式")
    parser.add_argument("--input-dir", help="批量转换输入目录")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--template", default="word_default", help="模板名称")
    
    args = parser.parse_args()
    
    if args.batch:
        result = asyncio.run(batch_convert_to_word(
            reports_dir=args.input_dir,
            template_name=args.template,
        ))
    elif args.report:
        result = asyncio.run(generate_word_document(
            report_json_path=args.report,
            output_path=args.output,
            template_name=args.template,
        ))
    else:
        parser.print_help()
        return
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
