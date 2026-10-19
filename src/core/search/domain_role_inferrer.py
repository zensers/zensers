# -*- coding: utf-8 -*-
"""
领域角色推断器

根据研究类型推断领域角色，提供中英文双语支持。
用于 LLM prompt 的角色上下文构建。
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class DomainRoleInferrer:
    """
    根据研究类型推断领域角色
    
    支持中英文双语，所有模板同时包含 zh 和 en 版本。
    
    使用示例：
        inferrer = DomainRoleInferrer()
        role_info = inferrer.infer("market_research", "新能源汽车", language="zh")
        # 返回: {"role": "资深市场研究分析师", "expertise": [...], "data_focus": [...]}
    """

    ROLE_TEMPLATES = {
        "market_research": {
            "role": {
                "zh": "资深市场研究分析师",
                "en": "Senior Market Research Analyst",
            },
            "expertise": {
                "zh": ["市场定量分析", "规模测算", "竞争格局分析", "消费者洞察"],
                "en": ["Quantitative Market Analysis", "Market Sizing", "Competitive Landscape", "Consumer Insights"],
            },
            "data_focus": {
                "zh": ["市场规模", "增长率", "市场份额", "消费者数据"],
                "en": ["market size", "growth rate", "market share", "consumer data"],
            },
        },
        "investment": {
            "role": {
                "zh": "资深投资分析师",
                "en": "Senior Investment Analyst",
            },
            "expertise": {
                "zh": ["财务分析", "估值建模", "风险评估", "投资回报分析"],
                "en": ["Financial Analysis", "Valuation Modeling", "Risk Assessment", "ROI Analysis"],
            },
            "data_focus": {
                "zh": ["财务数据", "估值指标", "融资动态", "投资案例"],
                "en": ["financial data", "valuation metrics", "funding news", "investment cases"],
            },
        },
        "policy": {
            "role": {
                "zh": "资深政策分析师",
                "en": "Senior Policy Analyst",
            },
            "expertise": {
                "zh": ["政策解读", "影响评估", "合规分析", "监管趋势"],
                "en": ["Policy Interpretation", "Impact Assessment", "Compliance Analysis", "Regulatory Trends"],
            },
            "data_focus": {
                "zh": ["政策文件", "法规条文", "官方公告", "监管动态"],
                "en": ["policy documents", "regulations", "official announcements", "regulatory updates"],
            },
        },
        "competitor": {
            "role": {
                "zh": "资深竞争情报分析师",
                "en": "Senior Competitive Intelligence Analyst",
            },
            "expertise": {
                "zh": ["竞争格局分析", "企业调研", "产品对比", "战略分析"],
                "en": ["Competitive Landscape Analysis", "Company Research", "Product Comparison", "Strategic Analysis"],
            },
            "data_focus": {
                "zh": ["企业数据", "产品信息", "市场份额", "战略动态"],
                "en": ["company data", "product information", "market share", "strategic updates"],
            },
        },
        "technology": {
            "role": {
                "zh": "资深技术分析师",
                "en": "Senior Technology Analyst",
            },
            "expertise": {
                "zh": ["技术趋势分析", "专利分析", "研发动态", "技术路线图"],
                "en": ["Technology Trend Analysis", "Patent Analysis", "R&D Updates", "Technology Roadmap"],
            },
            "data_focus": {
                "zh": ["技术文献", "专利数据", "研发投入", "技术突破"],
                "en": ["technical literature", "patent data", "R&D investment", "technology breakthroughs"],
            },
        },
        "industry": {
            "role": {
                "zh": "资深行业分析师",
                "en": "Senior Industry Analyst",
            },
            "expertise": {
                "zh": ["行业全景分析", "产业链研究", "发展趋势研判"],
                "en": ["Industry Overview Analysis", "Supply Chain Research", "Trend Forecasting"],
            },
            "data_focus": {
                "zh": ["行业数据", "产业链信息", "发展动态"],
                "en": ["industry data", "supply chain information", "development updates"],
            },
        },
    }

    RESEARCH_TYPE_MAPPING = {
        "industry_research": "industry",
        "competitive_analysis": "competitor",
        "policy_analysis": "policy",
        "technology_research": "technology",
        "brand_research": "market_research",
        "company_research": "competitor",
        "consumer_research": "market_research",
        "market_sizing": "market_research",
        "survey": "market_research",
        "interview": "market_research",
        "observation": "market_research",
        "data_analysis": "market_research",
        "swot_analysis": "market_research",
        "pestel_analysis": "market_research",
        "porter_analysis": "competitor",
    }

    # 默认模板（当研究类型未匹配时使用）
    DEFAULT_TEMPLATE = {
        "role": {
            "zh": "资深研究分析师",
            "en": "Senior Research Analyst",
        },
        "expertise": {
            "zh": ["数据分析", "信息收集", "趋势研判"],
            "en": ["Data Analysis", "Information Collection", "Trend Forecasting"],
        },
        "data_focus": {
            "zh": ["核心数据", "关键指标", "最新动态"],
            "en": ["core data", "key metrics", "latest updates"],
        },
    }

    @classmethod
    def map_research_type(cls, research_type_str: str) -> str:
        """将 ResearchType 枚举值映射为 ROLE_TEMPLATES key。

        Args:
            research_type_str: ResearchType 枚举的 .value（如 "industry_research"）

        Returns:
            ROLE_TEMPLATES key（如 "market_research"），未匹配时返回 "market_research"
        """
        return cls.RESEARCH_TYPE_MAPPING.get(research_type_str, "market_research")

    def infer(
        self,
        research_type: str,
        topic: str,
        language: str = "zh"
    ) -> Dict[str, Any]:
        """
        推断领域角色
        
        Args:
            research_type: 研究类型（market_research, investment, policy, competitor, technology, industry）
            topic: 研究主题（用于日志记录）
            language: 语言（"zh" 或 "en"）
            
        Returns:
            根据语言返回对应的角色信息：
            {
                "role": "资深市场研究分析师",
                "expertise": ["市场定量分析", "规模测算", ...],
                "data_focus": ["市场规模", "增长率", ...],
            }
        """
        # 获取模板
        template = self.ROLE_TEMPLATES.get(research_type, self.DEFAULT_TEMPLATE)
        
        # 验证语言参数
        if language not in ("zh", "en"):
            logger.warning(f"DomainRoleInferrer: 不支持的语言 '{language}'，使用默认中文")
            language = "zh"
        
        # 构建返回结果
        result = {
            "role": template["role"].get(language, template["role"]["zh"]),
            "expertise": template["expertise"].get(language, template["expertise"]["zh"]),
            "data_focus": template["data_focus"].get(language, template["data_focus"]["zh"]),
            "research_type": research_type,
            "language": language,
        }
        
        logger.debug(f"DomainRoleInferrer: 推断角色 '{result['role']}' (type={research_type}, lang={language})")
        
        return result

    def get_supported_types(self) -> List[str]:
        """获取支持的研究类型列表"""
        return list(self.ROLE_TEMPLATES.keys())

    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        return ["zh", "en"]

    def detect_language(self, text: str) -> str:
        """
        检测文本语言（简单启发式）
        
        Args:
            text: 待检测文本
            
        Returns:
            "zh" 或 "en"
        """
        # 统计中文字符比例
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text.replace(" ", "").replace("\n", ""))
        
        if total_chars == 0:
            return "zh"
        
        chinese_ratio = chinese_chars / total_chars
        
        # 如果中文字符超过 30%，判定为中文
        return "zh" if chinese_ratio > 0.3 else "en"
