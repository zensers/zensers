"""Markdown 表格和图片解析器 — P1 表格/图表操作的基础设施"""

from __future__ import annotations
import re
from typing import Any


class MarkdownTableParser:
    """解析和修改 Markdown 表格"""

    TABLE_BLOCK = re.compile(
        r'^\|.+\|[ \t]*$'           # 表头行（[ \t] 不匹配 \n，避免跨空行）
        r'(?:\n\|[-:| ]+\|[ \t]*$)' # 分隔行
        r'(?:\n\|.+\|[ \t]*$)+',    # 数据行
        re.MULTILINE
    )

    @classmethod
    def find_tables(cls, content: str) -> list[dict[str, Any]]:
        """在 section.content 中查找所有 Markdown 表格
        返回：[{table_text, start, end, header, rows}]
        """
        tables = []
        for match in cls.TABLE_BLOCK.finditer(content):
            lines = match.group(0).split('\n')
            if len(lines) < 3:
                continue

            def _cells(line: str) -> list[str]:
                return [c.strip() for c in line.strip().strip('|').split('|')]

            header = _cells(lines[0])
            rows = []
            for line in lines[2:]:
                line = line.strip()
                if line.startswith('|'):
                    rows.append({"cells": _cells(line), "raw": line})
            tables.append({
                "table_text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "header": header,
                "rows": rows,
            })
        return tables

    @classmethod
    def set_cell(cls, content: str, table_index: int, row: int, col: int, value: str) -> str:
        """修改第 N 个表格的 (row, col) 单元格为 value"""
        tables = cls.find_tables(content)
        if table_index < 0 or table_index >= len(tables):
            return content
        t = tables[table_index]
        if row < 0 or row >= len(t["rows"]):
            return content
        if col < 0 or col >= len(t["rows"][row]["cells"]):
            return content
        old_row_text = t["rows"][row]["raw"]
        cells = t["rows"][row]["cells"][:]
        cells[col] = value
        new_row_text = "|" + "|".join(cells) + "|"
        content = content.replace(old_row_text, new_row_text, 1)
        return content


class ImageParser:
    """解析 Markdown 图片引用"""

    IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    @classmethod
    def find_images(cls, content: str) -> list[dict[str, Any]]:
        """返回 [{alt, src, img_text, start, end}]"""
        images = []
        for match in cls.IMG_PATTERN.finditer(content):
            images.append({
                "alt": match.group(1),
                "src": match.group(2),
                "img_text": match.group(0),
                "start": match.start(),
                "end": match.end(),
            })
        return images
