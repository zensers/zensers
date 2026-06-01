from __future__ import annotations
import logging
from typing import Dict, List, Optional, Set
from copy import deepcopy
from collections import defaultdict
from uuid import uuid4
import re
import hashlib

from .revision_types import (
    Report, ReportTree, SectionNode, Section, StructuralImpact, TOCChange,
    BrokenReference, RevisionPlan, DuplicatePair, SectionRef, RefType,
    RevisionOpType, RevisionAction,
)


logger = logging.getLogger(__name__)


class DuplicateDetector:
    SIMILARITY_THRESHOLD = 0.85
    TITLE_SIMILARITY_THRESHOLD = 0.7

    def find_duplicates(
        self, report: Report, threshold: float = None
    ) -> List[DuplicatePair]:
        if threshold is None:
            threshold = self.SIMILARITY_THRESHOLD
        pairs: List[DuplicatePair] = []
        sections = getattr(report, "sections", [])
        for i in range(len(sections)):
            content_i = getattr(sections[i], "content", "") or ""
            id_i = getattr(sections[i], "id", f"sec_{i}")
            for j in range(i + 1, len(sections)):
                content_j = getattr(sections[j], "content", "") or ""
                id_j = getattr(sections[j], "id", f"sec_{j}")
                sim = self.compute_similarity(content_i, content_j)
                if sim >= threshold:
                    pairs.append(DuplicatePair(
                        source_id=id_i, target_id=id_j, similarity=sim,
                    ))
        return pairs

    def compute_similarity(self, a: str, b: str) -> float:
        tokens_a: Set[str] = set(a.lower().split())
        tokens_b: Set[str] = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)

    def find_similar_titles(
        self, title: str, report_tree: ReportTree, threshold: float = None
    ) -> List[SectionRef]:
        if threshold is None:
            threshold = self.TITLE_SIMILARITY_THRESHOLD
        results: List[SectionRef] = []
        for nid, node in report_tree.node_map.items():
            section_title = getattr(node.section, "title", "") or ""
            sim = self.compute_similarity(title, section_title)
            if sim >= threshold:
                results.append(SectionRef(
                    uuid=nid, ref_type=RefType.UUID,
                    number=getattr(node.section, "number", None),
                    raw_text=section_title,
                ))
        return results


class StructuralAnalyzer:
    MAX_CACHE_SIZE = 20

    def __init__(self):
        self._tree_cache: Dict[str, ReportTree] = {}
        self._session_cache_key: Optional[str] = None

    def begin_session(self, report: Report) -> str:
        key = f"session_{uuid4()}"
        self._session_cache_key = key
        return key

    def end_session(self) -> None:
        if self._session_cache_key and self._session_cache_key in self._tree_cache:
            del self._tree_cache[self._session_cache_key]
        self._session_cache_key = None
        if len(self._tree_cache) > self.MAX_CACHE_SIZE:
            excess = len(self._tree_cache) - self.MAX_CACHE_SIZE
            for _ in range(excess):
                self._tree_cache.pop(next(iter(self._tree_cache)), None)

    def analyze_tree(self, report: Report) -> ReportTree:
        if self._session_cache_key and self._session_cache_key in self._tree_cache:
            return self._tree_cache[self._session_cache_key]
        tree = self._build_tree(report)
        if self._session_cache_key:
            if len(self._tree_cache) >= self.MAX_CACHE_SIZE:
                evict_key = next(
                    (k for k in self._tree_cache if k != self._session_cache_key), None
                )
                if evict_key is None and self._session_cache_key in self._tree_cache:
                    evict_key = min(
                        self._tree_cache,
                        key=lambda k: list(self._tree_cache.keys()).index(k),
                    )
                if evict_key:
                    del self._tree_cache[evict_key]
            self._tree_cache[self._session_cache_key] = tree
        return tree

    def _build_tree(self, report: Report) -> ReportTree:
        tree = ReportTree()
        _root_section_cls = type("_RootSection", (), {"id": "_root", "title": "root", "content": "", "number": None})
        root_sec = _root_section_cls()
        root = SectionNode(id="_root", section=root_sec)
        tree.root = root
        tree.node_map["_root"] = root

        sections = getattr(report, "sections", [])
        section_map: Dict[str, SectionNode] = {}

        for sec in sections:
            sec_id = getattr(sec, "id", "") or str(uuid4())
            node = SectionNode(id=sec_id, section=sec)
            section_map[sec_id] = node
            tree.node_map[sec_id] = node

        for sec in sections:
            sec_id = getattr(sec, "id", "") or ""
            node = section_map.get(sec_id)
            if node is None:
                continue
            parent_id = getattr(sec, "parent_id", None)
            if parent_id and parent_id in section_map:
                parent = section_map[parent_id]
                parent.children.append(node)
                node.parent_id = parent_id
            else:
                root.children.append(node)
                node.parent_id = root.id

        return tree

    def analyze_impact(
        self, operation: RevisionAction, report: Report
    ) -> StructuralImpact:
        affected: List[str] = []
        for ref in operation.target.section_refs:
            if ref.uuid:
                affected.append(ref.uuid)

        toc_changes: List[TOCChange] = []
        structural_ops = {
            RevisionOpType.ADD, RevisionOpType.DELETE, RevisionOpType.MERGE,
            RevisionOpType.SPLIT, RevisionOpType.SWAP, RevisionOpType.REORDER,
            RevisionOpType.DEDUP,
        }
        if operation.action_type in structural_ops:
            for ref in operation.target.section_refs:
                toc_changes.append(TOCChange(
                    section_id=ref.uuid,
                    old_number=ref.number,
                    change_type="modified",
                ))

        return StructuralImpact(
            affected_sections=affected,
            toc_changes=toc_changes,
            cross_refs_broken=[],
            data_refs_affected=[],
            renumbering_required=len(toc_changes) > 0,
        )

    def analyze_plan_impact(
        self, plan: RevisionPlan, report: Report
    ) -> StructuralImpact:
        all_affected: List[str] = []
        all_toc: List[TOCChange] = []
        all_cross_refs: List[BrokenReference] = []
        all_data_refs: List[str] = []

        for action in plan.actions:
            impact = self.analyze_impact(action, report)
            all_affected.extend(impact.affected_sections)
            all_toc.extend(impact.toc_changes)
            all_cross_refs.extend(impact.cross_refs_broken)
            all_data_refs.extend(impact.data_refs_affected)

        return StructuralImpact(
            affected_sections=list(set(all_affected)),
            toc_changes=all_toc,
            cross_refs_broken=all_cross_refs,
            data_refs_affected=list(set(all_data_refs)),
            renumbering_required=len(all_toc) > 0,
        )

    def detect_cross_references(
        self, sections: List[Section]
    ) -> Dict[str, List[str]]:
        refs: Dict[str, List[str]] = defaultdict(list)
        section_numbers: Set[str] = set()

        for sec in sections:
            num = getattr(sec, "number", None)
            if num:
                section_numbers.add(str(num))

        pattern = re.compile(
            r"(?:see|section|Sec\.?|Sect\.?|如|参)?\s*(\d+(?:\.\d+)*)\s*(?:节|章|条|section)?",
            re.IGNORECASE,
        )

        for sec in sections:
            sec_id = getattr(sec, "id", "") or ""
            content = getattr(sec, "content", "") or ""
            for match in pattern.finditer(str(content)):
                num = match.group(1)
                if num in section_numbers:
                    refs[sec_id].append(num)

        return dict(refs)
