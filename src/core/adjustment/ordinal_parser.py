# -*- coding: utf-8 -*-
"""
序数词引用解析器

Phase 2.1: 问题定位增强

职责:
- 解析用户输入中的序数词引用
- 支持中文数字 (第一/第二/第三)
- 支持阿拉伯数字 (第1个/第2个)
- 支持英文序数词 (first/second/third)
- 定位对应的章节

示例:
- "第三部分" → 第3个章节
- "前两个" → 第1、2个章节
- "第二章" → 第2个章节
"""

__all__ = [
    "OrdinalReferenceParser",
    "SectionMatch",
]

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SectionMatch:
    """
    章节匹配结果
    
    Attributes:
        section_id: 章节ID
        section_title: 章节标题
        confidence: 匹配置信度 (0-1)
        match_type: 匹配类型 (ordinal/reference/keyword)
        reason: 匹配原因说明
    """
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "unknown"
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "confidence": self.confidence,
            "match_type": self.match_type,
            "reason": self.reason,
        }


class OrdinalReferenceParser:
    """
    序数词引用解析器
    
    解析用户输入中的序数词并定位对应章节。
    
    支持格式:
    - 中文: 第一部分、第二章、第三节、前两个、后三个
    - 阿拉伯数字: 第1个、第2章、第3节
    - 英文: first section, 2nd chapter, 3rd part
    
    使用方式:
        parser = OrdinalReferenceParser()
        matches = parser.parse_and_locate(
            text="请修改第三部分的数据",
            sections=["市场规模", "竞争格局", "发展趋势", "投资建议"]
        )
        # 返回: [SectionMatch(section_title="发展趋势", confidence=0.95)]
    """
    
    # 序数词正则模式
    ORDINAL_PATTERNS = {
        'zh': [
            # "第三部分" / "第三章" / "第三节"
            (r'第([一二三四五六七八九十百]+)[部章节篇]', 'chinese_num'),
            # "一、" / "二、" / "1." / "2."
            (r'(?:^|[^\d])([一二三四五六七八九十]+)[、．.]', 'chinese_num'),
            # "第一个" / "第二个"
            (r'第([一二三四五六七八九十\d]+)个', 'mixed_num'),
            # "前两个" / "后三个" / "前三章"
            (r'前([一二三四五六七八九十\d]+)[个章节]', 'chinese_num'),
            (r'后([一二三四五六七八九十\d]+)[个章节]', 'chinese_num'),
            # "最后两个" / "最后三章"
            (r'最后([一二三四五六七八九十\d]+)[个章节]', 'chinese_num'),
        ],
        'en': [
            # "the 1st section" / "the 2nd chapter"
            (r'(?:the\s+)?(\d+)(?:st|nd|rd|th)\s+(?:section|part|chapter)', 'int'),
            # "first section" / "second chapter" / "third part"
            (r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:section|part|chapter)', 'english_ordinal'),
            # "the first" / "the second" (隐含章节)
            (r'the\s+(first|second|third|fourth|fifth)', 'english_ordinal'),
        ],
    }
    
    # 中文数字映射
    CHINESE_NUM_MAP = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100,
    }
    
    # 英文序数词映射
    ENGLISH_ORDINAL_MAP = {
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
    }
    
    def parse_and_locate(
        self,
        text: str,
        sections: List[str],
    ) -> List[SectionMatch]:
        """
        提取序数词并定位对应章节
        
        Args:
            text: 用户输入文本
            sections: 章节标题列表 (按顺序)
            
        Returns:
            List[SectionMatch]: 匹配的章节列表
        """
        if not text or not sections:
            return []
        
        matches = []
        
        # 检测语言
        lang = self._detect_language(text)
        
        logger.debug(f"[OrdinalParser] Parsing text: '{text}', lang={lang}, sections={len(sections)}")
        
        for pattern, converter in self.ORDINAL_PATTERNS.get(lang, []):
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    # 转换序数词为数字
                    idx = self._convert_match(match, converter)
                    
                    if idx is None:
                        continue
                    
                    # 处理 "前N个" / "后N个" / "最后N个"
                    if '前' in text and match.group(0) in text:
                        # 前N个 → 第1到第N个
                        for i in range(1, idx + 1):
                            section_match = self._create_section_match(
                                sections, i - 1, "ordinal_prefix"
                            )
                            if section_match:
                                matches.append(section_match)
                        continue
                    
                    if '后' in text and '最后' not in text and match.group(0) in text:
                        # 后N个 → 倒数第N个到最后
                        for i in range(len(sections) - idx + 1, len(sections) + 1):
                            section_match = self._create_section_match(
                                sections, i - 1, "ordinal_suffix"
                            )
                            if section_match:
                                matches.append(section_match)
                        continue
                    
                    if '最后' in text and match.group(0) in text:
                        # 最后N个 → 倒数第N个到最后
                        for i in range(len(sections) - idx + 1, len(sections) + 1):
                            section_match = self._create_section_match(
                                sections, i - 1, "ordinal_last"
                            )
                            if section_match:
                                matches.append(section_match)
                        continue
                    
                    # 普通序数词 → 定位章节 (索引从1开始)
                    section_match = self._create_section_match(
                        sections, idx - 1, "ordinal"
                    )
                    if section_match:
                        matches.append(section_match)
                    
                except Exception as e:
                    logger.warning(f"[OrdinalParser] Failed to parse match '{match.group(0)}': {e}")
                    continue
        
        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = m.section_title
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)
        
        return unique_matches
    
    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        # 如果包含中文字符，返回中文
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            return 'zh'
        return 'en'
    
    def _convert_match(self, match: re.Match, converter: str) -> Optional[int]:
        """转换匹配结果为数字"""
        try:
            if converter == 'chinese_num':
                return self._chinese_to_int(match.group(1))
            elif converter == 'int':
                return int(match.group(1))
            elif converter == 'mixed_num':
                # 可能是中文或阿拉伯数字
                val = match.group(1)
                if val.isdigit():
                    return int(val)
                else:
                    return self._chinese_to_int(val)
            elif converter == 'english_ordinal':
                return self._english_ordinal_to_int(match.group(1))
            return None
        except Exception:
            return None
    
    def _chinese_to_int(self, chinese_num: str) -> int:
        """
        中文数字转整数
        
        支持:
        - 单字: 一、二、三...十
        - 组合: 十一、十二...二十、二十一...
        """
        if not chinese_num:
            return 1
        
        # 单字符直接查表
        if len(chinese_num) == 1:
            return self.CHINESE_NUM_MAP.get(chinese_num, 1)
        
        # 处理 "十一" "十二" 等 (10 + N)
        if chinese_num.startswith('十'):
            if len(chinese_num) == 1:
                return 10
            remainder = self.CHINESE_NUM_MAP.get(chinese_num[1], 0)
            return 10 + remainder
        
        # 处理 "二十" "二十一" 等 (N * 10 + M)
        if '十' in chinese_num:
            parts = chinese_num.split('十')
            tens = self.CHINESE_NUM_MAP.get(parts[0], 1) if parts[0] else 1
            ones = self.CHINESE_NUM_MAP.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
            return tens * 10 + ones
        
        # 简单累加 (不完美，但覆盖常见情况)
        result = 0
        for char in chinese_num:
            if char in self.CHINESE_NUM_MAP:
                val = self.CHINESE_NUM_MAP[char]
                if val >= 10:
                    result = result * val if result > 0 else val
                else:
                    result += val
        
        return result if result > 0 else 1
    
    def _english_ordinal_to_int(self, ordinal: str) -> int:
        """英文序数词转整数"""
        return self.ENGLISH_ORDINAL_MAP.get(ordinal.lower(), 1)
    
    def _create_section_match(
        self,
        sections: List[str],
        idx: int,
        match_type: str,
    ) -> Optional[SectionMatch]:
        """创建章节匹配结果"""
        if 0 <= idx < len(sections):
            return SectionMatch(
                section_id=f"section_{idx + 1}",
                section_title=sections[idx],
                confidence=0.95,  # 序数词引用置信度高
                match_type=match_type,
                reason=f"用户提到第{idx + 1}个章节",
            )
        return None
