# -*- coding: utf-8 -*-
"""
SectionRenumberer - 章节重编号器

遍历 ReportTree，按层级重新计算章节编号。
"""

from __future__ import annotations

import logging
from typing import Optional

from .revision_types import ReportTree, SectionNode

logger = logging.getLogger(__name__)


class SectionRenumberer:

    def renumber(self, report_tree: ReportTree) -> None:
        if report_tree.root is None:
            return
        self.renumber_subtree(report_tree.root, "")

    def renumber_subtree(
        self, node: SectionNode, parent_number: str = "",
    ) -> None:
        for idx, child in enumerate(node.children, start=1):
            if parent_number:
                child.section.number = f"{parent_number}.{idx}"
            else:
                child.section.number = str(idx)
            self.renumber_subtree(child, child.section.number)

    def compute_new_number(
        self, old_number: str, report_tree: ReportTree
    ) -> Optional[str]:
        node = report_tree.find_by_number(old_number)
        if node is None:
            return None
        old_tree = self._build_number_tree(report_tree)
        self.renumber(report_tree)
        new_tree = self._build_number_tree(report_tree)
        for nid, number in old_tree.items():
            if number == old_number:
                return new_tree.get(nid)
        return None

    def _build_number_tree(
        self, report_tree: ReportTree,
    ) -> dict:
        mapping = {}
        for nid, node in report_tree.node_map.items():
            if hasattr(node.section, "number") and node.section.number:
                mapping[nid] = node.section.number
        return mapping
