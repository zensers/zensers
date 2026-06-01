# -*- coding: utf-8 -*-
"""
对话历史引用追踪器

Phase 2.2: 问题定位增强

职责:
- 追踪对话历史中的章节引用
- 解析指代词 (这部分/那个章节/前面提到的)
- 回溯对话历史找到最近引用的章节
- 支持中英文指代词

示例:
- 之前对话: "竞争格局分析得不错"
- 当前输入: "这部分数据需要更新"
- 结果: 返回 "竞争格局" 章节
"""

__all__ = [
    "ConversationReferenceTracker",
]

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .ordinal_parser import SectionMatch

logger = logging.getLogger(__name__)


class ConversationReferenceTracker:
    """
    对话历史引用追踪器
    
    追踪对话历史中提到的章节，解析指代词引用。
    
    支持指代词:
    - 中文: 这部分、那个章节、前面提到、刚才说的、上述、之前分析
    - 英文: that section, the previous, mentioned above, as discussed
    
    使用方式:
        tracker = ConversationReferenceTracker()
        matches = tracker.extract_and_locate(
            current_feedback="这部分数据需要更新",
            conversation_history=[
                {"role": "user", "content": "竞争格局分析得不错"},
                {"role": "assistant", "content": "好的，我会继续完善..."},
            ],
            sections=["市场规模", "竞争格局", "发展趋势", "投资建议"]
        )
        # 返回: [SectionMatch(section_title="竞争格局", confidence=0.81)]
    """
    
    # 指代词模式
    REFERENCE_PATTERNS = [
        # 中文指代词
        r'这部[分章节]',
        r'那个章节',
        r'那个部分',
        r'前面提到',
        r'前面说的',
        r'刚才说的',
        r'刚才提到',
        r'上述',
        r'上[述面]分析',
        r'之前分析',
        r'之前提到',
        r'刚才[的那个]',
        r'这[一块块儿]',
        r'那一块',
        # 英文指代词
        r'that section',
        r'that part',
        r'the previous',
        r'the above',
        r'mentioned above',
        r'as discussed',
        r'as mentioned',
        r'referenced earlier',
        r'this section',
        r'this part',
    ]
    
    # 章节名称正则 (用于提取历史消息中的章节名)
    SECTION_NAME_PATTERNS = [
        # 章节名称通常在引号中
        r'[""「」『』]([^""「」『』]+)[""「」『』]',
        # "XX部分" / "XX章节" / "XX分析"
        r'([^\s，。！？]{2,10})(?:部分|章节|分析|研究|报告)',
        # "关于XX"
        r'关于([^\s，。！？]{2,10})',
    ]
    
    def extract_and_locate(
        self,
        current_feedback: str,
        conversation_history: List[Dict[str, str]],
        sections: List[str],
    ) -> List[SectionMatch]:
        """
        从对话历史中提取引用的章节
        
        Args:
            current_feedback: 当前用户输入
            conversation_history: 对话历史 [{"role": "user/assistant", "content": "..."}]
            sections: 章节标题列表
            
        Returns:
            List[SectionMatch]: 匹配的章节列表
        """
        if not current_feedback or not sections:
            return []
        
        matches = []
        
        # 检测是否包含指代词
        has_reference = self._detect_reference(current_feedback)
        
        if not has_reference:
            logger.debug(f"[ReferenceTracker] No reference pattern found in: '{current_feedback}'")
            return matches
        
        logger.debug(f"[ReferenceTracker] Reference detected in: '{current_feedback}'")
        
        # 回溯对话历史，找到最近提到的章节
        # 只检查最近10条消息
        for msg in reversed(conversation_history[-10:]):
            content = msg.get('content', '')
            role = msg.get('role', '')
            
            # 优先检查用户消息 (用户更可能提到具体章节)
            if role != 'user':
                continue
            
            # 提取消息中提到的章节名称
            mentioned_sections = self._extract_section_mentions(content, sections)
            
            if mentioned_sections:
                for section_name, confidence in mentioned_sections:
                    # 引用追踪置信度略低 (0.85 衰减)
                    matches.append(SectionMatch(
                        section_id=self._get_section_id(section_name, sections),
                        section_title=section_name,
                        confidence=confidence * 0.85,
                        match_type="reference",
                        reason=f"对话历史中提到: {section_name}",
                    ))
                break  # 只取最近的引用
        
        return matches
    
    def _detect_reference(self, text: str) -> bool:
        """检测文本是否包含指代词"""
        for pattern in self.REFERENCE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _extract_section_mentions(
        self,
        text: str,
        sections: List[str],
    ) -> List[Tuple[str, float]]:
        """
        从文本中提取提到的章节名称
        
        Args:
            text: 对话文本
            sections: 章节标题列表
            
        Returns:
            List[Tuple[str, float]]: (章节名, 置信度) 列表
        """
        mentions = []
        text_lower = text.lower()
        
        # 方法1: 直接匹配章节名称
        for section in sections:
            if section.lower() in text_lower:
                # 章节名称直接出现在文本中
                mentions.append((section, 0.95))
        
        # 方法2: 模糊匹配 (章节名称在引号中或被标注)
        for pattern in self.SECTION_NAME_PATTERNS:
            for match in re.finditer(pattern, text):
                candidate = match.group(1).strip()
                
                # 检查候选是否匹配章节名
                for section in sections:
                    # 相似度匹配
                    similarity = self._calculate_similarity(candidate, section)
                    if similarity >= 0.6:
                        # 避免重复添加
                        if not any(m[0] == section for m in mentions):
                            mentions.append((section, similarity * 0.9))
        
        # 按置信度排序
        mentions.sort(key=lambda x: x[1], reverse=True)
        
        return mentions[:3]  # 最多返回3个
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度 (简单版)
        
        使用字符重叠率计算
        """
        if not text1 or not text2:
            return 0.0
        
        # 清理文本
        t1 = set(text1.lower().replace(" ", ""))
        t2 = set(text2.lower().replace(" ", ""))
        
        # 计算交集
        intersection = t1 & t2
        union = t1 | t2
        
        if not union:
            return 0.0
        
        # Jaccard 相似度
        jaccard = len(intersection) / len(union)
        
        # 如果一个字符串包含另一个，额外加分
        if text1.lower() in text2.lower() or text2.lower() in text1.lower():
            jaccard = max(jaccard, 0.8)
        
        return jaccard
    
    def _get_section_id(self, section_name: str, sections: List[str]) -> str:
        """获取章节ID"""
        try:
            idx = sections.index(section_name)
            return f"section_{idx + 1}"
        except ValueError:
            return f"section_{section_name}"
    
    def get_reference_context(
        self,
        conversation_history: List[Dict[str, str]],
        sections: List[str],
        max_messages: int = 5,
    ) -> Dict[str, Any]:
        """
        获取对话历史中的章节引用上下文
        
        Args:
            conversation_history: 对话历史
            sections: 章节标题列表
            max_messages: 最多检查的消息数
            
        Returns:
            Dict: 包含章节引用统计和最近引用
        """
        section_mentions = {}
        
        for msg in conversation_history[-max_messages:]:
            content = msg.get('content', '')
            mentions = self._extract_section_mentions(content, sections)
            
            for section, confidence in mentions:
                if section not in section_mentions:
                    section_mentions[section] = {
                        "count": 0,
                        "total_confidence": 0.0,
                        "last_message": content[:100],
                    }
                section_mentions[section]["count"] += 1
                section_mentions[section]["total_confidence"] += confidence
        
        # 计算平均置信度
        for section, data in section_mentions.items():
            data["avg_confidence"] = data["total_confidence"] / data["count"]
        
        return {
            "section_mentions": section_mentions,
            "most_mentioned": max(section_mentions.keys(), 
                                  key=lambda s: section_mentions[s]["count"]) if section_mentions else None,
        }
