# -*- coding: utf-8 -*-
"""
CrossReferenceFixer - 交叉引用修复器

识别报告中如 "如3.2节所述"、"see section X.X" 等引用格式，
在章节重编号后自动修复引用目标。
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from .revision_types import (
    BrokenReference,
    FixReport,
    ReferenceMatch,
    ReportTree,
    SectionReference,
)

logger = logging.getLogger(__name__)


class CrossReferenceFixer:
    CHINESE_REF_PATTERN = re.compile(r"[如参]?\d+(?:\.\d+)*[节章条]")
    ENGLISH_REF_PATTERN = re.compile(
        r"(?:see|section|chapter|Sec\.?|Sect\.?)\s*\d+(?:\.\d+)*",
        re.IGNORECASE,
    )
    PAREN_REF_PATTERN = re.compile(r"\((?:\u7b2c)?\d+(?:\.\d+)*\u8282?(?:\u6240\u8ff0)?\)")

    def find_references(self, text: str) -> List[ReferenceMatch]:
        refs: List[ReferenceMatch] = []
        for pattern, rtype in [
            (self.CHINESE_REF_PATTERN, "chinese"),
            (self.ENGLISH_REF_PATTERN, "english"),
            (self.PAREN_REF_PATTERN, "paren"),
        ]:
            for match in pattern.finditer(text):
                refs.append(ReferenceMatch(
                    original_text=match.group(),
                    target_number=self._extract_number(match.group()),
                    start=match.start(),
                    end=match.end(),
                    ref_type=rtype,
                ))
        return refs

    def analyze_impact(
        self, report_tree: ReportTree,
        renumbering_map: Dict[str, str],
    ) -> List[BrokenReference]:
        broken: List[BrokenReference] = []
        for nid, node in report_tree.node_map.items():
            refs = self.find_references(node.section.content)
            for ref in refs:
                old_num = ref.target_number
                if old_num is None:
                    continue
                new_num = renumbering_map.get(old_num)
                if new_num is not None and new_num != old_num:
                    broken.append(BrokenReference(
                        original_text=ref.original_text,
                        target_section_id=nid,
                        new_target_number=new_num,
                        is_fixable=True,
                    ))
                elif new_num is None:
                    broken.append(BrokenReference(
                        original_text=ref.original_text,
                        target_section_id=nid,
                        new_target_number=None,
                        is_fixable=False,
                    ))
        return broken

    def fix_references(
        self, report_tree: ReportTree,
        renumbering_map: Dict[str, str],
    ) -> FixReport:
        report = FixReport()
        for nid, node in report_tree.node_map.items():
            content = node.section.content
            refs = self.find_references(content)
            replacements: List[tuple] = []
            for ref in refs:
                old_num = ref.target_number
                if old_num is None:
                    continue
                new_num = renumbering_map.get(old_num)
                if new_num is None or new_num == old_num:
                    if new_num is None:
                        report.unfixable += 1
                        report.details.append(
                            f"[{nid}] Cannot resolve: {ref.original_text}"
                        )
                    continue
                new_text = ref.original_text.replace(old_num, new_num, 1)
                replacements.append((ref, new_text))
            # Process from right to left to preserve offsets
            replacements.sort(key=lambda x: x[0].end, reverse=True)
            for ref, new_text in replacements:
                content = content[: ref.start] + new_text + content[ref.end :]
                report.fixed += 1
                report.details.append(
                    f"[{nid}] {ref.original_text} -> {new_text}"
                )
            node.section.content = content
        return report

    def _extract_number(self, ref_text: str) -> Optional[str]:
        nums = re.findall(r"\d+(?:\.\d+)*", ref_text)
        return nums[0] if nums else None
