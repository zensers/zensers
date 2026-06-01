# -*- coding: utf-8 -*-
"""
Internationalization Support Module

Provides multi-language support including:
1. Language detection (from user input, system environment, configuration)
2. Text translation (localized strings)
3. Template multi-language support

Usage:
    from src.core.i18n import I18n, get_language, set_language

    # Set language
    set_language("en")

    # Get localized text
    text = I18n.t("section.market_size")  # "Market Size"

    # Detect language from user input
    lang = detect_language("Analyze China's new energy vehicle market")  # "en"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)


class Language(Enum):
    """Supported languages"""
    ZH = "zh"      # Chinese
    EN = "en"      # English
    JA = "ja"      # Japanese
    KO = "ko"      # Korean
    AUTO = "auto"  # Auto detect


@dataclass
class LocaleStrings:
    """Localized string collection"""
    # Section names
    section_summary: Dict[str, str] = field(default_factory=lambda: {
        "zh": "执行摘要",
        "en": "Executive Summary",
        "ja": "エグゼクティブサマリー",
        "ko": "요약",
    })
    section_market_size: Dict[str, str] = field(default_factory=lambda: {
        "zh": "市场规模",
        "en": "Market Size",
        "ja": "市場規模",
        "ko": "시장 규모",
    })
    section_competition: Dict[str, str] = field(default_factory=lambda: {
        "zh": "竞争格局",
        "en": "Competitive Landscape",
        "ja": "競争環境",
        "ko": "경쟁 구도",
    })
    section_trend: Dict[str, str] = field(default_factory=lambda: {
        "zh": "发展趋势",
        "en": "Development Trends",
        "ja": "発展傾向",
        "ko": "발전 추세",
    })
    section_policy: Dict[str, str] = field(default_factory=lambda: {
        "zh": "政策环境",
        "en": "Policy Environment",
        "ja": "政策環境",
        "ko": "정책 환경",
    })
    section_technology: Dict[str, str] = field(default_factory=lambda: {
        "zh": "技术分析",
        "en": "Technology Analysis",
        "ja": "技術分析",
        "ko": "기술 분석",
    })
    section_risk: Dict[str, str] = field(default_factory=lambda: {
        "zh": "风险分析",
        "en": "Risk Analysis",
        "ja": "リスク分析",
        "ko": "위험 분석",
    })
    section_conclusion: Dict[str, str] = field(default_factory=lambda: {
        "zh": "研究结论",
        "en": "Conclusion",
        "ja": "結論",
        "ko": "결론",
    })
    
    # Framework options
    framework_detailed: Dict[str, str] = field(default_factory=lambda: {
        "zh": "详细版",
        "en": "Detailed",
        "ja": "詳細版",
        "ko": "상세",
    })
    framework_standard: Dict[str, str] = field(default_factory=lambda: {
        "zh": "标准版",
        "en": "Standard",
        "ja": "標準版",
        "ko": "표준",
    })
    framework_brief: Dict[str, str] = field(default_factory=lambda: {
        "zh": "精简版",
        "en": "Brief",
        "ja": "簡易版",
        "ko": "간략",
    })
    
    # Agent roles
    role_analyst: Dict[str, str] = field(default_factory=lambda: {
        "zh": "高级分析师",
        "en": "Senior Analyst",
        "ja": "シニアアナリスト",
        "ko": "수석 분석가",
    })
    role_data_collector: Dict[str, str] = field(default_factory=lambda: {
        "zh": "数据收集专家",
        "en": "Data Collection Expert",
        "ja": "データ収集専門家",
        "ko": "데이터 수집 전문가",
    })


# Global language setting
_current_language: Language = Language.ZH
_locale_strings = LocaleStrings()


def get_language() -> Language:
    """Get current language setting"""
    return _current_language


def set_language(lang: Union[str, Language]) -> None:
    """Set current language"""
    global _current_language
    if isinstance(lang, str):
        try:
            _current_language = Language(lang.lower())
        except ValueError:
            _current_language = Language.ZH
    else:
        _current_language = lang
    logger.info(f"Language set to: {_current_language.value}")


def detect_language(text: str) -> Language:
    """
    Detect language from text

    Uses heuristic methods:
    1. Detect Chinese character ratio
    2. Detect Japanese kana
    3. Detect Korean characters
    4. Default to English

    Args:
        text: Input text

    Returns:
        Detected language
    """
    if not text:
        return Language.EN

    # Count character types
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    japanese_hiragana = len(re.findall(r'[\u3040-\u309f]', text))
    japanese_katakana = len(re.findall(r'[\u30a0-\u30ff]', text))
    korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))
    total_chars = len(re.sub(r'\s', '', text))

    if total_chars == 0:
        return Language.EN

    # Calculate ratios
    chinese_ratio = chinese_chars / total_chars
    japanese_ratio = (japanese_hiragana + japanese_katakana) / total_chars
    korean_ratio = korean_chars / total_chars

    # Determine language (threshold 0.1)
    if chinese_ratio > 0.1 and japanese_ratio < 0.05:
        return Language.ZH
    elif japanese_ratio > 0.05:
        return Language.JA
    elif korean_ratio > 0.1:
        return Language.KO
    else:
        return Language.EN


def get_localized_text(
    text_dict: Union[Dict[str, str], str],
    lang: Optional[Language] = None,
    fallback: str = ""
) -> str:
    """
    Get localized text

    Args:
        text_dict: Multi-language dict or single-language string
        lang: Target language (None uses current language)
        fallback: Fallback text when not found

    Returns:
        Localized text
    """
    if isinstance(text_dict, str):
        return text_dict

    target_lang = lang or _current_language

    # Try to get target language
    if target_lang.value in text_dict:
        return text_dict[target_lang.value]

    # Fallback to Chinese
    if "zh" in text_dict:
        return text_dict["zh"]

    # Fallback to English
    if "en" in text_dict:
        return text_dict["en"]

    # Return first available value
    if text_dict:
        return next(iter(text_dict.values()))

    return fallback


class I18n:
    """Internationalization utility class"""

    # Section ID to name multi-language mapping
    SECTION_NAMES = {
        "summary": {"zh": "执行摘要", "en": "Executive Summary", "ja": "エグゼクティブサマリー", "ko": "요약"},
        "market_size": {"zh": "市场规模", "en": "Market Size", "ja": "市場規模", "ko": "시장 규모"},
        "market_segments": {"zh": "细分市场", "en": "Market Segments", "ja": "市場セグメント", "ko": "시장 세그먼트"},
        "competitive_landscape": {"zh": "竞争格局", "en": "Competitive Landscape", "ja": "競争環境", "ko": "경쟁 구도"},
        "competition": {"zh": "竞争格局", "en": "Competition", "ja": "競争", "ko": "경쟁"},
        "industry_chain": {"zh": "产业链", "en": "Industry Chain", "ja": "産業チェーン", "ko": "산업 사슬"},
        "industry_overview": {"zh": "行业概况", "en": "Industry Overview", "ja": "業界概況", "ko": "산업 개요"},
        "trends": {"zh": "发展趋势", "en": "Trends", "ja": "傾向", "ko": "추세"},
        "policy_environment": {"zh": "政策环境", "en": "Policy Environment", "ja": "政策環境", "ko": "정책 환경"},
        "policy": {"zh": "政策环境", "en": "Policy", "ja": "政策", "ko": "정책"},
        "user_insights": {"zh": "用户洞察", "en": "User Insights", "ja": "ユーザーインサイト", "ko": "사용자 인사이트"},
        "tech_trends": {"zh": "技术发展", "en": "Technology Trends", "ja": "技術動向", "ko": "기술 동향"},
        "technology": {"zh": "技术分析", "en": "Technology", "ja": "技術", "ko": "기술"},
        "risks": {"zh": "风险挑战", "en": "Risks", "ja": "リスク", "ko": "위험"},
        "risk": {"zh": "风险分析", "en": "Risk Analysis", "ja": "リスク分析", "ko": "위험 분석"},
        "conclusion": {"zh": "结论建议", "en": "Conclusion", "ja": "結論", "ko": "결론"},
    }
    
    # Keyword multi-language mapping (for data type matching)
    KEYWORDS_MAP = {
        "zh": {
            "摘要": ["行业概况"],
            "概况": ["行业概况"],
            "市场": ["市场规模", "行业概况"],
            "规模": ["市场规模"],
            "竞争": ["竞争格局", "企业分析"],
            "产业": ["产业链", "行业概况"],
            "链": ["产业链"],
            "政策": ["政策法规"],
            "技术": ["技术趋势"],
            "企业": ["企业分析", "竞争格局"],
            "公司": ["企业分析", "竞争格局"],
            "消费": ["消费者洞察"],
            "用户": ["消费者洞察"],
            "趋势": ["技术趋势"],
            "风险": ["政策法规"],
            "结论": ["行业概况"],
        },
        "en": {
            "summary": ["industry_overview"],
            "overview": ["industry_overview"],
            "market": ["market_size", "industry_overview"],
            "size": ["market_size"],
            "competition": ["competitive_landscape", "company_analysis"],
            "competitive": ["competitive_landscape"],
            "industry": ["industry_chain", "industry_overview"],
            "chain": ["industry_chain"],
            "policy": ["policy_regulation"],
            "technology": ["technology_trend"],
            "tech": ["technology_trend"],
            "company": ["company_analysis", "competitive_landscape"],
            "consumer": ["consumer_insight"],
            "user": ["consumer_insight"],
            "trend": ["technology_trend"],
            "risk": ["policy_regulation"],
            "conclusion": ["industry_overview"],
        },
        "ja": {
            "概要": ["業界概況"],
            "市場": ["市場規模", "業界概況"],
            "規模": ["市場規模"],
            "競争": ["競争環境", "企業分析"],
            "産業": ["産業チェーン", "業界概況"],
            "政策": ["政策法規"],
            "技術": ["技術動向"],
            "企業": ["企業分析", "競争環境"],
            "消費": ["消費者インサイト"],
            "ユーザー": ["消費者インサイト"],
            "傾向": ["技術動向"],
            "リスク": ["政策法規"],
            "結論": ["業界概況"],
        },
        "ko": {
            "요약": ["산업 개요"],
            "시장": ["시장 규모", "산업 개요"],
            "규모": ["시장 규모"],
            "경쟁": ["경쟁 구도", "기업 분석"],
            "산업": ["산업 사슬", "산업 개요"],
            "정책": ["정책 규제"],
            "기술": ["기술 동향"],
            "기업": ["기업 분석", "경쟁 구도"],
            "소비": ["소비자 인사이트"],
            "사용자": ["소비자 인사이트"],
            "추세": ["기술 동향"],
            "위험": ["정책 규제"],
            "결론": ["산업 개요"],
        },
    }
    
    @classmethod
    def t(cls, key: str, lang: Optional[Language] = None) -> str:
        """
        Get localized text

        Args:
            key: Text key (e.g. "section.market_size")
            lang: Target language

        Returns:
            Localized text
        """
        target_lang = lang or _current_language
        
        # 解析键
        parts = key.split(".")
        if len(parts) == 2:
            category, item = parts
            if category == "section":
                if item in cls.SECTION_NAMES:
                    return get_localized_text(cls.SECTION_NAMES[item], target_lang)
        
        return key
    
    @classmethod
    def get_section_name(cls, section_id: str, lang: Optional[Language] = None) -> str:
        """Get section name"""
        target_lang = lang or _current_language
        if section_id in cls.SECTION_NAMES:
            return get_localized_text(cls.SECTION_NAMES[section_id], target_lang)
        return section_id
    
    @classmethod
    def get_keywords_map(cls, lang: Optional[Language] = None) -> Dict[str, List[str]]:
        """Get keyword mapping"""
        target_lang = lang or _current_language
        return cls.KEYWORDS_MAP.get(target_lang.value, cls.KEYWORDS_MAP["en"])
    
    @classmethod
    def localize_section(
        cls,
        section: Dict[str, Any],
        lang: Optional[Language] = None
    ) -> Dict[str, Any]:
        """
        Localize section info

        Args:
            section: Section dict (may contain multi-language name/description)
            lang: Target language

        Returns:
            Localized section dict
        """
        target_lang = lang or _current_language
        result = section.copy()

        # Localize name field
        if "name" in result:
            result["name"] = get_localized_text(result["name"], target_lang)

        # Localize description field
        if "description" in result:
            result["description"] = get_localized_text(result["description"], target_lang)

        return result

    @classmethod
    def localize_sections(
        cls,
        sections: List[Dict[str, Any]],
        lang: Optional[Language] = None
    ) -> List[Dict[str, Any]]:
        """Batch localize section list"""
        return [cls.localize_section(s, lang) for s in sections]


# Convenience functions
def t(key: str, lang: Optional[Language] = None) -> str:
    """Convenience function to get localized text"""
    return I18n.t(key, lang)


def get_language_instruction(language: Optional[Language] = None) -> str:
    """
    Get a mandatory language output instruction string to append to LLM prompts.
    
    This is the primary mechanism to enforce language consistency across all agents.
    The instruction is deliberately strict and positioned as highest priority to
    override the LLM's tendency to default to English when it sees English prompts.
    
    Args:
        language: Target language (None uses current global language)
        
    Returns:
        A string to append to any prompt, containing the language rule
    """
    lang = language or _current_language
    
    instructions = {
        Language.ZH: (
            "\n\n## 语言规则（必须严格遵守，优先级最高）\n"
            "你必须使用中文（简体中文）输出。\n"
            "- 所有分析、判断、数据、结论都**必须**用中文呈现\n"
            "- 保留专有名词（公司名、产品名、人名）的原文，如有通用中文译名则使用中文\n"
            "- 数据中的数字、百分比、日期保持原始格式\n"
            "- 禁止输出任何英文段落或混合语言\n"
            "- 翻译所有搜索结果、引文和参考材料到中文\n"
            "- 这条规则**优先级高于**本 prompt 中所有其他指令"
        ),
        Language.EN: (
            "\n\n## Language Rule (STRICT, HIGHEST PRIORITY)\n"
            "You MUST output in English only.\n"
            "- All analysis, judgments, data, and conclusions MUST be in English\n"
            "- Keep proper nouns (company names, product names, people) in their original form\n"
            "- Numbers, percentages, dates keep their original format\n"
            "- Do NOT mix languages in your output\n"
            "- Translate all search results, quotes, and references into English\n"
            "- This rule **OVERRIDES** all other instructions in this prompt"
        ),
        Language.JA: (
            "\n\n## 言語ルール（厳守、最優先）\n"
            "日本語でのみ出力してください。\n"
            "- すべての分析、判断、データ、結論は日本語で記述すること\n"
            "- 固有名詞（企業名、製品名、人名）は原文を保持するか、一般的な日本語訳を使用\n"
            "- 数字、パーセンテージ、日付は元の形式を保持\n"
            "- 言語を混在させないこと\n"
            "- すべての検索結果、引用、参考資料を日本語に翻訳すること\n"
            "- このルールは本プロンプトの他のすべての指示に**優先する**"
        ),
        Language.KO: (
            "\n\n## 언어 규칙(엄수, 최우선)\n"
            "한국어로만 출력해야 합니다.\n"
            "- 모든 분석, 판단, 데이터, 결론은 한국어로 작성\n"
            "- 고유명사(회사명, 제품명, 인명)는 원문 유지 또는 일반적인 한국어 번역 사용\n"
            "- 숫자, 백분율, 날짜는 원래 형식 유지\n"
            "- 언어를 혼용하지 않음\n"
            "- 모든 검색 결과, 인용문, 참고 자료를 한국어로 번역\n"
            "- 이 규칙은 이 프롬프트의 다른 모든 지침보다 **우선함**"
        ),
    }
    
    return instructions.get(lang, "")


__all__ = [
    "Language",
    "LocaleStrings",
    "I18n",
    "get_language",
    "set_language",
    "detect_language",
    "get_localized_text",
    "get_language_instruction",
    "t",
]
