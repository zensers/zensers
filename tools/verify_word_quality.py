# -*- coding: utf-8 -*-
"""
Word文档质量验证脚本

验证生成的Word文档是否符合国际咨询公司标准。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def verify_word_document(docx_path: str) -> dict:
    """
    验证Word文档质量
    
    Args:
        docx_path: Word文档路径
    
    Returns:
        验证结果
    """
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        # 加载文档
        doc = Document(docx_path)
        
        # 验证结果
        result = {
            "success": True,
            "file_exists": True,
            "file_size": Path(docx_path).stat().st_size,
            "page_count": len(doc.sections),
            "paragraph_count": len(doc.paragraphs),
            "table_count": len(doc.tables),
            "has_header": False,
            "has_footer": False,
            "has_watermark": False,
            "quality_score": 0,
            "issues": []
        }
        
        # 检查页眉页脚
        for section in doc.sections:
            if section.header and section.header.paragraphs:
                result["has_header"] = True
            if section.footer and section.footer.paragraphs:
                result["has_footer"] = True
        
        # 检查内容质量
        has_title = False
        has_content = False
        has_tables = False
        
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading"):
                has_title = True
            if para.text.strip():
                has_content = True
        
        if len(doc.tables) > 0:
            has_tables = True
        
        # 计算质量分数
        score = 0
        if has_title:
            score += 25
        if has_content:
            score += 25
        if has_tables:
            score += 25
        if result["has_header"]:
            score += 12.5
        if result["has_footer"]:
            score += 12.5
        
        result["quality_score"] = score
        
        # 检查问题
        if not has_title:
            result["issues"].append("缺少标题样式")
        if not has_content:
            result["issues"].append("缺少正文内容")
        if not has_tables:
            result["issues"].append("缺少数据表格")
        if not result["has_header"]:
            result["issues"].append("缺少页眉")
        if not result["has_footer"]:
            result["issues"].append("缺少页脚")
        
        return result
        
    except ImportError:
        return {
            "success": False,
            "error": "python-docx库未安装"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """主函数"""
    # 检查最终版本的研究报告
    docx_path = ROOT / "output" / "real_new_energy_vehicle_report_v3" / "中国新能源汽车行业深度研究.docx"
    
    if not docx_path.exists():
        print(f"文件不存在: {docx_path}")
        return
    
    print(f"验证Word文档: {docx_path}")
    print("-" * 50)
    
    result = verify_word_document(str(docx_path))
    
    if result["success"]:
        print(f"[OK] 文件存在: {result['file_exists']}")
        print(f"[OK] 文件大小: {result['file_size'] / 1024:.2f} KB")
        print(f"[OK] 章节数量: {result['page_count']}")
        print(f"[OK] 段落数量: {result['paragraph_count']}")
        print(f"[OK] 表格数量: {result['table_count']}")
        print(f"[OK] 页眉: {'有' if result['has_header'] else '无'}")
        print(f"[OK] 页脚: {'有' if result['has_footer'] else '无'}")
        print(f"[OK] 质量分数: {result['quality_score']}/100")
        
        if result["issues"]:
            print("\n[WARNING] 问题:")
            for issue in result["issues"]:
                print(f"  - {issue}")
        else:
            print("\n[OK] 无问题，文档质量良好！")
    else:
        print(f"[ERROR] 验证失败: {result.get('error', '未知错误')}")


if __name__ == "__main__":
    main()
