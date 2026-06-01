# -*- coding: utf-8 -*-
"""
增强版章节定位器

Phase 2.3: 问题定位增强 - 统一入口

职责:
- 整合多种定位策略
- 序数词解析 (OrdinalReferenceParser)
- 对话历史引用追踪 (ConversationReferenceTracker)
- 关键词匹配 (现有 SectionLocator)
- 置信度排序和结果合并

定位策略优先级:
1. 序数词引用 (置信度 0.95)
2. 对话历史引用 (置信度 0.85)
3. 关键词匹配 (置信度 0.7-0.9)
"""

__all__ = [
    "EnhancedSectionLocator",
    "SectionMatch",
]

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .ordinal_parser import OrdinalReferenceParser, SectionMatch
from .conversation_reference_tracker import ConversationReferenceTracker

logger = logging.getLogger(__name__)


class EnhancedSectionLocator:
    """
    增强版章节定位器
    
    整合多种定位策略，提供统一的章节定位接口。
    
    使用方式:
        locator = EnhancedSectionLocator()
        matches = locator.locate(
            user_input="请修改第三部分的数据",
            sections=["市场规模", "竞争格局", "发展趋势", "投资建议"],
            conversation_history=[
                {"role": "user", "content": "竞争格局分析得不错"},
            ]
        )
        # 返回: [SectionMatch(section_title="发展趋势", confidence=0.95)]
    """
    
    def __init__(
        self,
        enable_ordinal: bool = True,
        enable_reference: bool = True,
        min_confidence: float = 0.5,
    ):
        """
        初始化增强版章节定位器
        
        Args:
            enable_ordinal: 是否启用序数词解析
            enable_reference: 是否启用对话历史引用追踪
            min_confidence: 最小置信度阈值
        """
        self.enable_ordinal = enable_ordinal
        self.enable_reference = enable_reference
        self.min_confidence = min_confidence
        
        # 初始化子定位器
        self._ordinal_parser = OrdinalReferenceParser() if enable_ordinal else None
        self._reference_tracker = ConversationReferenceTracker() if enable_reference else None
        
        logger.info(
            f"[EnhancedLocator] Initialized with ordinal={enable_ordinal}, "
            f"reference={enable_reference}, min_confidence={min_confidence}"
        )
    
    def locate(
        self,
        user_input: str,
        sections: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> List[SectionMatch]:
        """
        定位用户输入中引用的章节
        
        Args:
            user_input: 用户输入文本
            sections: 章节标题列表
            conversation_history: 对话历史 (可选)
            
        Returns:
            List[SectionMatch]: 匹配的章节列表 (按置信度排序)
        """
        if not user_input or not sections:
            return []
        
        all_matches = []
        
        # 策略1: 序数词解析
        if self._ordinal_parser:
            ordinal_matches = self._ordinal_parser.parse_and_locate(user_input, sections)
            all_matches.extend(ordinal_matches)
            logger.debug(
                f"[EnhancedLocator] Ordinal matches: {len(ordinal_matches)}"
            )
        
        # 策略2: 对话历史引用追踪
        if self._reference_tracker and conversation_history:
            reference_matches = self._reference_tracker.extract_and_locate(
                user_input, conversation_history, sections
            )
            all_matches.extend(reference_matches)
            logger.debug(
                f"[EnhancedLocator] Reference matches: {len(reference_matches)}"
            )
        
        # 策略3: 关键词匹配 (简单版)
        keyword_matches = self._keyword_match(user_input, sections)
        all_matches.extend(keyword_matches)
        logger.debug(
            f"[EnhancedLocator] Keyword matches: {len(keyword_matches)}"
        )
        
        # 去重并排序
        unique_matches = self._deduplicate_and_sort(all_matches)
        
        # 过滤低置信度结果
        filtered_matches = [
            m for m in unique_matches
            if m.confidence >= self.min_confidence
        ]
        
        logger.info(
            f"[EnhancedLocator] Total matches: {len(filtered_matches)} "
            f"(from {len(all_matches)} raw)"
        )
        
        return filtered_matches
    
    def _keyword_match(
        self,
        user_input: str,
        sections: List[str],
    ) -> List[SectionMatch]:
        """
        关键词匹配 (简单版)
        
        检查用户输入是否包含章节名称
        """
        matches = []
        user_input_lower = user_input.lower()
        
        for idx, section in enumerate(sections):
            if section.lower() in user_input_lower:
                matches.append(SectionMatch(
                    section_id=f"section_{idx + 1}",
                    section_title=section,
                    confidence=0.85,
                    match_type="keyword",
                    reason=f"用户输入包含章节名称: {section}",
                ))
        
        return matches
    
    def _deduplicate_and_sort(
        self,
        matches: List[SectionMatch],
    ) -> List[SectionMatch]:
        """
        去重并按置信度排序
        
        优先级:
        1. 置信度高的优先
        2. 序数词 > 引用 > 关键词
        """
        # 按章节标题分组
        section_map: Dict[str, SectionMatch] = {}
        
        for match in matches:
            key = match.section_title
            if key is None:
                continue
            
            if key not in section_map:
                section_map[key] = match
            else:
                # 保留置信度更高的
                existing = section_map[key]
                
                # 置信度优先
                if match.confidence > existing.confidence:
                    section_map[key] = match
                # 置信度相同时，按匹配类型优先级
                elif match.confidence == existing.confidence:
                    type_priority = {"ordinal": 3, "reference": 2, "keyword": 1}
                    if type_priority.get(match.match_type, 0) > type_priority.get(existing.match_type, 0):
                        section_map[key] = match
        
        # 按置信度降序排序
        result = list(section_map.values())
        result.sort(key=lambda m: m.confidence, reverse=True)
        
        return result
    
    def locate_with_context(
        self,
        user_input: str,
        sections: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        定位章节并返回详细上下文
        
        Args:
            user_input: 用户输入
            sections: 章节列表
            conversation_history: 对话历史
            
        Returns:
            Dict: 包含匹配结果、上下文信息
        """
        matches = self.locate(user_input, sections, conversation_history)
        
        context = {
            "matches": [m.to_dict() for m in matches],
            "total_matches": len(matches),
            "top_match": matches[0].to_dict() if matches else None,
            "strategies_used": {
                "ordinal": self.enable_ordinal,
                "reference": self.enable_reference,
                "keyword": True,
            },
        }
        
        # 添加对话历史上下文
        if self._reference_tracker and conversation_history:
            ref_context = self._reference_tracker.get_reference_context(
                conversation_history, sections
            )
            context["reference_context"] = ref_context
        
        return context
