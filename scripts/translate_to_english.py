#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Chinese to English Translation Script for Source Code
======================================================

This script helps convert Chinese comments, docstrings, and log messages
in Python source files to English.

Usage:
    python scripts/translate_to_english.py --dry-run  # Preview changes
    python scripts/translate_to_english.py --apply    # Apply changes

Note: This script performs pattern-based translation. Manual review is
recommended for complex code.
"""

import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Common translation mappings for code comments
TRANSLATIONS: Dict[str, str] = {
    # Docstring patterns
    '"""': '"""',
    
    # Common comment patterns
    "# =====": "# =====",
    "# ---": "# ---",
    
    # Section headers
    "参数": "Args",
    "返回": "Returns",
    "属性": "Attributes",
    "示例": "Example",
    "注意": "Note",
    "警告": "Warning",
    "参见": "See Also",
    "抛出": "Raises",
    
    # Common phrases in comments
    "初始化": "Initialize",
    "配置": "Configure",
    "验证": "Validate",
    "检查": "Check",
    "获取": "Get",
    "设置": "Set",
    "创建": "Create",
    "生成": "Generate",
    "处理": "Process",
    "执行": "Execute",
    "加载": "Load",
    "保存": "Save",
    "更新": "Update",
    "删除": "Delete",
    "添加": "Add",
    "移除": "Remove",
    "计算": "Calculate",
    "分析": "Analyze",
    "整合": "Integrate",
    "组装": "Assemble",
    
    # Error/log messages
    "缺少必需的": "Missing required",
    "字段": "field",
    "必须是": "must be",
    "操作超时": "Operation timeout",
    "执行失败": "Execution failed",
    "执行完成": "Execution completed",
    "开始执行": "Started execution",
    "数据不足": "Insufficient data",
    
    # Report-related
    "报告": "Report",
    "章节": "Chapter",
    "摘要": "Summary",
    "结论": "Conclusion",
    "附录": "Appendix",
    "目录": "Table of Contents",
    "免责声明": "Disclaimer",
}

def find_chinese_text(content: str) -> List[Tuple[int, int, str]]:
    """Find all Chinese text spans in content.
    
    Returns:
        List of (start, end, text) tuples
    """
    # Match Chinese characters (including punctuation)
    pattern = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+')
    matches = []
    for m in pattern.finditer(content):
        matches.append((m.start(), m.end(), m.group()))
    return matches

def is_in_string(content: str, position: int) -> bool:
    """Check if position is inside a string literal."""
    # Simple heuristic: count quotes before position
    before = content[:position]
    single_quotes = before.count("'") - before.count("\\'")
    double_quotes = before.count('"') - before.count('\\"')
    return single_quotes % 2 == 1 or double_quotes % 2 == 1

def is_in_comment(content: str, position: int) -> bool:
    """Check if position is inside a comment."""
    line_start = content.rfind('\n', 0, position) + 1
    line = content[line_start:position]
    return '#' in line

def translate_text(text: str) -> str:
    """Translate Chinese text to English using mappings."""
    result = text
    for zh, en in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
        result = result.replace(zh, en)
    return result

def process_file(file_path: Path, dry_run: bool = True) -> List[str]:
    """Process a single Python file.
    
    Returns:
        List of changes made (or proposed if dry_run)
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return []
    
    changes = []
    chinese_texts = find_chinese_text(content)
    
    if not chinese_texts:
        return []
    
    new_content = content
    offset = 0
    
    for start, end, text in chinese_texts:
        # Check context
        abs_start = start + offset
        abs_end = end + offset
        
        # Skip if in string literal (likely intentional Chinese)
        if is_in_string(content, start):
            continue
        
        # Translate
        translated = translate_text(text)
        if translated != text:
            changes.append(f"  Line ~{content[:start].count(chr(10))+1}: '{text}' -> '{translated}'")
            if not dry_run:
                new_content = new_content[:abs_start] + translated + new_content[abs_end:]
                offset += len(translated) - len(text)
    
    if changes and not dry_run:
        try:
            file_path.write_text(new_content, encoding='utf-8')
            logger.info(f"Updated: {file_path}")
        except Exception as e:
            logger.error(f"Failed to write {file_path}: {e}")
    
    return changes

def main():
    parser = argparse.ArgumentParser(description="Translate Chinese comments to English")
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    parser.add_argument('--path', type=str, default='src', help='Path to process (default: src)')
    args = parser.parse_args()
    
    dry_run = not args.apply
    base_path = Path(args.path)
    
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN - No changes will be made")
        logger.info("=" * 60)
    
    # Find all Python files
    python_files = list(base_path.rglob("*.py"))
    logger.info(f"\nFound {len(python_files)} Python files in {base_path}")
    
    total_changes = 0
    files_with_changes = []
    
    for file_path in python_files:
        # Skip __pycache__
        if '__pycache__' in str(file_path):
            continue
        
        changes = process_file(file_path, dry_run)
        if changes:
            files_with_changes.append((file_path, changes))
            total_changes += len(changes)
    
    # Report
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Summary: {len(files_with_changes)} files with {total_changes} proposed changes")
    logger.info(f"{'=' * 60}")
    
    if dry_run:
        for file_path, changes in files_with_changes[:10]:  # Show first 10
            logger.info(f"\n{file_path}:")
            for change in changes[:5]:  # Show first 5 changes per file
                logger.info(change)
        
        if len(files_with_changes) > 10:
            logger.info(f"\n... and {len(files_with_changes) - 10} more files")
        
        logger.info("\nRun with --apply to make changes")
    else:
        logger.info(f"\nUpdated {len(files_with_changes)} files")

if __name__ == "__main__":
    main()
