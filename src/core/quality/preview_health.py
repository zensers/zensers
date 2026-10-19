# -*- coding: utf-8 -*-
"""
预览排版自检

设计文档: docs/2026-06-01-quality-feedback-revision-design.md
"""

from pathlib import Path
from typing import Dict, List


def check_preview_health(html_path: str, old_html_length: int = 0) -> Dict[str, object]:
    issues: List[Dict[str, str]] = []
    p = Path(html_path)
    if not p.exists():
        return {"healthy": False, "issues": [{"type": "layout", "message": "预览文件不存在"}]}

    content = p.read_text(encoding="utf-8")

    if content.count("<table") != content.count("</table"):
        issues.append({"type": "layout", "message": "表格标签未闭合"})

    if len(content.strip()) < 500:
        issues.append({"type": "layout", "message": "预览内容异常稀疏"})

    if old_html_length > 0 and len(content) > old_html_length * 3:
        issues.append({"type": "layout", "message": "预览内容异常膨胀"})

    return {"healthy": len(issues) == 0, "issues": issues}
