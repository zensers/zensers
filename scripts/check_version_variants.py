#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多版本文件检查脚本

检查项目中是否存在违反版本管理规范的文件：
- *_v2.py, *_v3.py 等版本后缀
- *_enhanced.py 增强版后缀
- *_new.py 新版后缀

用法:
    python scripts/check_version_variants.py
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 禁止的文件模式
FORBIDDEN_PATTERNS = [
    "*_v[0-9].py",      # _v2.py, _v3.py
    "*_v[0-9][0-9].py", # _v10.py, etc.
    "*_enhanced.py",    # 增强版
    "*_new.py",         # 新版
    "*_old.py",         # 旧版
]


def find_version_variants(root_dir: Path) -> List[Tuple[str, str]]:
    """
    查找版本变体文件
    
    Args:
        root_dir: 项目根目录
        
    Returns:
        [(文件路径, 匹配模式), ...]
    """
    variants = []
    
    for py_file in root_dir.rglob("*.py"):
        # 跳过 __pycache__
        if "__pycache__" in str(py_file):
            continue
        
        # 跳过虚拟环境
        if "venv" in str(py_file) or ".venv" in str(py_file):
            continue
        
        file_name = py_file.name
        
        # 检查 _v2, _v3 等
        if file_name.endswith("_v2.py") or file_name.endswith("_v3.py"):
            variants.append((str(py_file.relative_to(root_dir)), "version suffix (_v2, _v3)"))
        
        # 检查 _enhanced
        if "_enhanced" in file_name:
            variants.append((str(py_file.relative_to(root_dir)), "enhanced suffix"))
        
        # 检查 _new
        if file_name.endswith("_new.py"):
            variants.append((str(py_file.relative_to(root_dir)), "new suffix"))
        
        # 检查 _old
        if file_name.endswith("_old.py"):
            variants.append((str(py_file.relative_to(root_dir)), "old suffix"))
    
    return variants


def check_for_original(variant_path: str, root_dir: Path) -> bool:
    """
    检查是否存在对应的原版文件
    
    Args:
        variant_path: 变体文件路径
        root_dir: 项目根目录
        
    Returns:
        是否存在原版
    """
    # 提取基础名
    file_name = Path(variant_path).name
    
    # 移除版本后缀
    base_name = file_name
    for suffix in ["_v2.py", "_v3.py", "_enhanced.py", "_new.py", "_old.py"]:
        if file_name.endswith(suffix):
            base_name = file_name.replace(suffix, ".py")
            break
    
    # 检查原版是否存在
    original_path = Path(variant_path).parent / base_name
    return (root_dir / original_path).exists()


def main():
    """主函数"""
    print("=" * 60)
    print("多版本文件检查")
    print("=" * 60)
    
    # 查找变体文件
    variants = find_version_variants(PROJECT_ROOT)
    
    if not variants:
        print("\n✅ 未发现多版本问题")
        return 0
    
    print(f"\n⚠️  发现 {len(variants)} 个多版本文件:\n")
    
    has_issues = False
    
    for file_path, pattern in variants:
        has_original = check_for_original(file_path, PROJECT_ROOT)
        
        if has_original:
            status = "🔴 存在原版，应合并"
            has_issues = True
        else:
            status = "🟡 无原版，需确认主版本"
        
        print(f"  {status}")
        print(f"    文件: {file_path}")
        print(f"    模式: {pattern}")
        print()
    
    if has_issues:
        print("\n📋 建议操作:")
        print("  1. 分析各版本差异")
        print("  2. 确定主版本")
        print("  3. 删除其他版本")
        print("  4. 更新导入路径")
        print("  5. 运行测试验证")
        print("\n详细规范请参考: docs/CODE_VERSION_GUIDELINES.md")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())