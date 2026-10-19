# -*- coding: utf-8 -*-
"""
ContentManipulator - 内容操纵器

对 ReportTree 进行增删改查等结构化操作，每种操作返回 ManipulationResult。
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Optional

from .revision_types import (
    InsertPosition,
    ManipulationResult,
    ReportTree,
    SectionNode,
)

logger = logging.getLogger(__name__)


class ContentManipulator:

    def replace_content(
        self, section_id: str, new_content: str, report_tree: ReportTree
    ) -> ManipulationResult:
        node = report_tree.find(section_id)
        if node is None:
            return ManipulationResult(
                success=False, error=f"Section not found: {section_id}",
            )
        sec = node.section
        if isinstance(sec, str):
            from types import SimpleNamespace
            sec = SimpleNamespace(id=section_id, content=sec, title="")
            node.section = sec
        sec.content = new_content
        return ManipulationResult(success=True, affected_ids=[section_id])

    def delete_section(
        self, section_id: str, report_tree: ReportTree
    ) -> ManipulationResult:
        node = report_tree.find(section_id)
        if node is None:
            return ManipulationResult(
                success=False, error=f"Section not found: {section_id}",
            )
        parent = report_tree.find(node.parent_id) if node and node.parent_id else None
        if parent is not None:
            parent.children = [c for c in parent.children if c.id != section_id]
        report_tree.node_map.pop(section_id, None)
        affected = [section_id]
        self._collect_descendant_ids(node, affected)
        for nid in affected[1:]:
            report_tree.node_map.pop(nid, None)
        return ManipulationResult(success=True, affected_ids=affected)

    def insert_section(
        self, parent_id: str, section: SectionNode,
        position: InsertPosition, report_tree: ReportTree,
    ) -> ManipulationResult:
        parent = report_tree.find(parent_id)
        if parent is None:
            return ManipulationResult(
                success=False, error=f"Parent section not found: {parent_id}",
            )
        section.parent_id = parent_id
        if position == "first":
            parent.children.insert(0, section)
        elif position == "last":
            parent.children.append(section)
        else:
            try:
                idx = int(position)
                parent.children.insert(idx, section)
            except (ValueError, IndexError):
                return ManipulationResult(
                    success=False, error=f"Invalid position: {position}",
                )
        report_tree.node_map[section.id] = section
        return ManipulationResult(success=True, affected_ids=[section.id])

    def merge_sections(
        self, target_id: str, source_id: str,
        strategy: str, report_tree: ReportTree,
    ) -> ManipulationResult:
        target = report_tree.find(target_id)
        source = report_tree.find(source_id)
        if target is None or source is None:
            missing = target_id if target is None else source_id
            return ManipulationResult(
                success=False, error=f"Section not found: {missing}",
            )
        if strategy in ("append", "prepend", "replace"):
            t_sec = target.section
            s_sec = source.section
            # 确保 section 是对象而非字符串（与 replace_content 一致）
            from types import SimpleNamespace
            if isinstance(t_sec, str):
                t_sec = SimpleNamespace(id=target_id, content=t_sec, title="")
                target.section = t_sec
            if isinstance(s_sec, str):
                s_sec = SimpleNamespace(id=source_id, content=s_sec, title="")
                source.section = s_sec
            if strategy == "append":
                t_sec.content += "\n" + s_sec.content
            elif strategy == "prepend":
                t_sec.content = s_sec.content + "\n" + t_sec.content
            elif strategy == "replace":
                t_sec.content = s_sec.content
        else:
            return ManipulationResult(
                success=False, error=f"Unknown merge strategy: {strategy}",
            )
        target.children.extend(source.children)
        for child in source.children:
            child.parent_id = target_id
        report_tree.node_map.pop(source_id, None)
        return ManipulationResult(
            success=True, affected_ids=[target_id, source_id],
        )

    def move_section(
        self, section_id: str, new_parent_id: str,
        position: InsertPosition, report_tree: ReportTree,
    ) -> ManipulationResult:
        node = report_tree.find(section_id)
        new_parent = report_tree.find(new_parent_id)
        if node is None or new_parent is None:
            missing = section_id if node is None else new_parent_id
            return ManipulationResult(
                success=False, error=f"Section not found: {missing}",
            )
        old_parent = report_tree.find(node.parent_id) if node.parent_id else None
        if old_parent is not None:
            old_parent.children = [c for c in old_parent.children if c.id != section_id]
        node.parent_id = new_parent_id
        if position == "first":
            new_parent.children.insert(0, node)
        elif position == "last":
            new_parent.children.append(node)
        else:
            try:
                idx = int(position)
                new_parent.children.insert(idx, node)
            except (ValueError, IndexError):
                return ManipulationResult(
                    success=False, error=f"Invalid position: {position}",
                )
        return ManipulationResult(success=True, affected_ids=[section_id])

    def copy_section(
        self, source_id: str, target_parent_id: str,
        position: InsertPosition, deep_copy: bool,
        report_tree: ReportTree,
    ) -> ManipulationResult:
        source = report_tree.find(source_id)
        parent = report_tree.find(target_parent_id)
        if source is None or parent is None:
            missing = source_id if source is None else target_parent_id
            return ManipulationResult(
                success=False, error=f"Section not found: {missing}",
            )
        if deep_copy:
            new_node = deepcopy(source)
            new_node.id = f"{source.id}_copy"
        else:
            new_node = SectionNode(
                id=f"{source.id}_ref",
                section=source.section,
                children=source.children,
                parent_id=target_parent_id,
            )
        new_node.parent_id = target_parent_id
        if position == "first":
            parent.children.insert(0, new_node)
        elif position == "last":
            parent.children.append(new_node)
        else:
            try:
                idx = int(position)
                parent.children.insert(idx, new_node)
            except (ValueError, IndexError):
                return ManipulationResult(
                    success=False, error=f"Invalid position: {position}",
                )
        report_tree.node_map[new_node.id] = new_node
        return ManipulationResult(success=True, affected_ids=[new_node.id])

    def _collect_descendant_ids(
        self, node: SectionNode, acc: list,
    ) -> None:
        for child in node.children:
            acc.append(child.id)
            self._collect_descendant_ids(child, acc)
