# -*- coding: utf-8 -*-
"""
SectionLocatorV2 - 章节定位器 V2

基于 RevisionTarget 和 ReportTree 的多策略章节定位。

定位策略优先级（由 locate_with_fallback 编排）:
1. ORDINAL - 序数词定位
2. REFERENCE - 引用定位
3. KEYWORD - 关键词定位
4. SEMANTIC - 语义定位（兜底）
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from difflib import SequenceMatcher

from .revision_types import (
    LocationResult,
    LocationStrategy,
    ReportTree,
    RevisionTarget,
    SectionRef,
    RefType,
)

logger = logging.getLogger(__name__)

# 中文数字 → 整数映射
_CHINESE_NUM = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100,
}

# 英文序数 → 整数映射
_ENGLISH_ORD = {
    'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
    'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
}

# 序数匹配模式
_ORDINAL_PATTERNS = [
    (re.compile(r'第([一二三四五六七八九十百]+)[部章节篇段]'), 'chinese'),
    (re.compile(r'第(\d+)[部章节篇段]'), 'digit'),
    (re.compile(r'(?:the\s+)?(\d+)(?:st|nd|rd|th)\s+(?:section|part|chapter)'), 'int'),
    (re.compile(r'(?:section|part|chapter)\s+(\d+)'), 'int'),
    (re.compile(r'(?:section|part|chapter)\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)'), 'eng'),
    (re.compile(r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:section|part|chapter)'), 'eng'),
]


def _chinese_to_int(s: str) -> int:
    """中文数字 → 整数, 支持 '三' → 3, '十二' → 12"""
    total = 0
    for ch in s:
        total = total * 10 + _CHINESE_NUM.get(ch, 1)
    return total


def _parse_ordinal(text: str) -> Optional[int]:
    """从文本中提取序数, 返回 1-based index 或 None"""
    if not text:
        return None
    for pattern, kind in _ORDINAL_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1)
            if kind == 'chinese':
                return _chinese_to_int(raw)
            elif kind == 'digit':
                return int(raw)
            elif kind == 'int':
                return int(raw)
            elif kind == 'eng':
                return _ENGLISH_ORD.get(raw)
    return None


def _fuzzy_match(query: str, title: str) -> float:
    """标题模糊匹配相似度 0~1"""
    if not query or not title:
        return 0.0
    q = query.lower().strip()
    t = title.lower().strip()
    if q == t:
        return 1.0
    if q in t or t in q:
        return 0.8
    return SequenceMatcher(None, q, t).ratio()


class SectionLocatorV2:
    CONFIDENCE_THRESHOLD = 0.3

    async def locate(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        strategy_map: Dict[LocationStrategy, LocationResult] = {
            LocationStrategy.ORDINAL: await self._locate_by_ordinal(target, report_tree),
            LocationStrategy.REFERENCE: await self._locate_by_reference(target, report_tree),
            LocationStrategy.KEYWORD: await self._locate_by_keyword(target, report_tree),
            LocationStrategy.SEMANTIC: await self._locate_by_semantic(target, report_tree),
        }
        result = strategy_map.get(target.location_strategy)
        if result is None:
            return LocationResult(
                matches=[], is_ambiguous=False,
                strategy_used=target.location_strategy,
                confidence=0.0, fallback_chain=[],
            )
        return result

    async def locate_with_fallback(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        strategies = [
            LocationStrategy.ORDINAL,
            LocationStrategy.REFERENCE,
            LocationStrategy.KEYWORD,
            LocationStrategy.SEMANTIC,
        ]
        fallback_chain: List[LocationStrategy] = []
        for strategy in strategies:
            if strategy == target.location_strategy:
                result = await self.locate(target, report_tree)
            else:
                fallback_target = RevisionTarget(
                    raw_text=target.raw_text,
                    section_refs=target.section_refs,
                    location_strategy=strategy,
                    is_ambiguous=target.is_ambiguous,
                )
                result = await self.locate(fallback_target, report_tree)
            fallback_chain.append(strategy)
            if result.confidence >= self.CONFIDENCE_THRESHOLD:
                result.fallback_chain = fallback_chain
                return result
        result.fallback_chain = fallback_chain
        return result

    async def resolve_to_ids(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> List[str]:
        # 优先使用 target.section_refs 中已有的 UUID 引用
        uuid_refs = [ref.uuid for ref in target.section_refs
                     if ref.ref_type == RefType.UUID and ref.uuid]
        if uuid_refs:
            return uuid_refs

        result = await self.locate_with_fallback(target, report_tree)
        ids = [ref.uuid for ref in result.matches if ref.uuid]
        if result.confidence < self.CONFIDENCE_THRESHOLD:
            return []
        return ids

    async def _locate_by_ordinal(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        text = target.raw_text
        idx = _parse_ordinal(text)
        if idx is None:
            return LocationResult(
                matches=[], is_ambiguous=False,
                strategy_used=LocationStrategy.ORDINAL,
                confidence=0.0, fallback_chain=[],
            )
        # 获取有序节点列表: 优先用 root.children 遍历, 否则用 node_map
        if report_tree.root and report_tree.root.children:
            ordered = []
            def _walk(n):
                ordered.append(n)
                for c in n.children:
                    _walk(c)
            for c in report_tree.root.children:
                _walk(c)
        else:
            ordered = list(report_tree.node_map.values())
        if not ordered:
            return LocationResult(
                matches=[], is_ambiguous=False,
                strategy_used=LocationStrategy.ORDINAL,
                confidence=0.0, fallback_chain=[],
            )
        if idx < 1 or idx > len(ordered):
            return LocationResult(
                matches=[], is_ambiguous=False,
                strategy_used=LocationStrategy.ORDINAL,
                confidence=0.0, fallback_chain=[],
            )
        node = ordered[idx - 1]
        ref = SectionRef(uuid=node.id, ref_type=RefType.INDEX,
                         index=idx - 1, raw_text=text)
        return LocationResult(
            matches=[ref], is_ambiguous=False,
            strategy_used=LocationStrategy.ORDINAL,
            confidence=0.9, fallback_chain=[],
        )

    async def _locate_by_reference(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        """引用定位: 匹配 "如3.2节所述" / "see section 2.1" 等编号引用"""
        nums = re.findall(r'(\d+(?:\.\d+)+)', target.raw_text)
        if nums:
            for nid, node in report_tree.node_map.items():
                sec_num = getattr(node.section, 'number', None)
                if sec_num and str(sec_num) in nums:
                    ref = SectionRef(uuid=nid, ref_type=RefType.NUMBER,
                                     number=str(sec_num), raw_text=target.raw_text)
                    return LocationResult(
                        matches=[ref], is_ambiguous=False,
                        strategy_used=LocationStrategy.REFERENCE,
                        confidence=0.8, fallback_chain=[])
        return LocationResult(
            matches=[], is_ambiguous=False,
            strategy_used=LocationStrategy.REFERENCE,
            confidence=0.0, fallback_chain=[],
        )

    async def _locate_by_keyword(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        text = target.raw_text
        candidates = []
        for nid, node in report_tree.node_map.items():
            title = getattr(node.section, 'title', '') or ''
            score = _fuzzy_match(text, title)
            if score >= 0.5:
                candidates.append((score, node))
        if not candidates:
            keywords = self._extract_keywords(text)
            if keywords:
                for nid, node in report_tree.node_map.items():
                    title = getattr(node.section, 'title', '') or ''
                    content = getattr(node.section, 'content', '') or ''
                    match_count = sum(1 for kw in keywords if kw in title or kw in content[:500])
                    if match_count > 0:
                        score = min(0.3 + 0.2 * match_count, 0.7)
                        candidates.append((score, node))
        if not candidates:
            return LocationResult(
                matches=[], is_ambiguous=False,
                strategy_used=LocationStrategy.KEYWORD,
                confidence=0.0, fallback_chain=[],
            )
        candidates.sort(key=lambda x: -x[0])
        best_score, best_node = candidates[0]
        ref = SectionRef(uuid=best_node.id, ref_type=RefType.UUID,
                         raw_text=text)
        return LocationResult(
            matches=[ref], is_ambiguous=False,
            strategy_used=LocationStrategy.KEYWORD,
            confidence=best_score, fallback_chain=[],
        )

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        _STOPWORDS = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
            '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
            '你', '会', '着', '没有', '看', '好', '自己', '这', '那',
            '为', '与', '或', '等', '及', '对', '把', '被', '让', '给',
            '向', '从', '按', '比', '但', '而', '且', '如果', '因为',
            '所以', '虽然', '但是', '可以', '需要', '应该', '可能',
            '已经', '还', '更', '最', '非常', '比较', '稍微', '一点',
            '一些', '什么', '怎么', '如何', '为什么', '哪', '哪个',
            '哪里', '多少', '几', '补充', '修改', '更新', '调整', '新增',
            '删除', '添加', '替换', '修正', '章节', '部分', '内容', '数据',
            '报告', '里面', '中', '后', '前',
        }
        words = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', text)
        return [w for w in words if w not in _STOPWORDS and len(w) >= 2]

    async def _locate_by_semantic(
        self, target: RevisionTarget, report_tree: ReportTree
    ) -> LocationResult:
        """语义定位: 按标题/内容模糊匹配"""
        text = target.raw_text
        candidates = []
        for nid, node in report_tree.node_map.items():
            title = getattr(node.section, 'title', '') or ''
            content = getattr(node.section, 'content', '') or ''
            score = max(_fuzzy_match(text, title), _fuzzy_match(text, content[:500]))
            if score >= 0.3:
                candidates.append((score, nid))
        if candidates:
            candidates.sort(key=lambda x: -x[0])
            ref = SectionRef(uuid=candidates[0][1], ref_type=RefType.UUID,
                             raw_text=text)
            return LocationResult(
                matches=[ref], is_ambiguous=len(candidates) > 1,
                strategy_used=LocationStrategy.SEMANTIC,
                confidence=candidates[0][0], fallback_chain=[])
        return LocationResult(
            matches=[], is_ambiguous=False,
            strategy_used=LocationStrategy.SEMANTIC,
            confidence=0.0, fallback_chain=[],
        )
