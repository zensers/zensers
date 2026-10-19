"""
读取 PDF 文件并提取文本内容

用法:
    python tools/read_pdf.py "C:\path\to\file.pdf"
    python tools/read_pdf.py "C:\path\to\file.pdf" --output output.txt
    python tools/read_pdf.py "C:\path\to\file.pdf" --pages 1-5
"""

import argparse
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("请先安装 pdfplumber: pip install pdfplumber")
    sys.exit(1)


def extract_text(pdf_path: str, pages: str = None) -> str:
    """提取 PDF 文本"""
    full_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"PDF 共 {total_pages} 页")
        
        # 解析页码范围
        if pages:
            page_range = parse_page_range(pages, total_pages)
        else:
            page_range = range(total_pages)
        
        for i in page_range:
            page = pdf.pages[i]
            text = page.extract_text()
            if text:
                full_text.append(f"=== 第 {i+1} 页 ===\n{text}\n")
    
    return "\n".join(full_text)


def parse_page_range(pages_str: str, total_pages: int) -> range:
    """解析页码范围（如: 1-5, 1,3,5, 1-）"""
    if '-' in pages_str:
        parts = pages_str.split('-')
        start = int(parts[0]) - 1 if parts[0] else 0
        end = int(parts[1]) if parts[1] else total_pages
        return range(start, min(end, total_pages))
    else:
        # 逗号分隔的页码
        page_nums = [int(p) - 1 for p in pages_str.split(',')]
        return [p for p in page_nums if 0 <= p < total_pages]


def main():
    parser = argparse.ArgumentParser(description='读取 PDF 文件并提取文本')
    parser.add_argument('pdf_path', type=str, help='PDF 文件路径')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径（可选）')
    parser.add_argument('--pages', '-p', type=str, help='页码范围（如: 1-5, 1,3,5）')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    if not Path(args.pdf_path).exists():
        print(f"文件不存在: {args.pdf_path}")
        return
    
    # 提取文本
    print(f"正在读取: {args.pdf_path}")
    text = extract_text(args.pdf_path, args.pages)
    
    # 输出
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"已保存到: {args.output}")
    else:
        # 处理编码问题
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        print("\n" + "="*60)
        print(text)


if __name__ == "__main__":
    main()
