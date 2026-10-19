# -*- coding: utf-8 -*-
"""
RapidEvolver - 快速进化器

Phase 3.6 核心功能: 导入资料时立即学习用户专业能力
- 秒级完成
- 立即更新 CoreMemory
- 让用户获得"系统懂我"的体验
"""

__all__ = [
    "RapidEvolver",
    "EvolutionResult"
]

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class EvolutionResult:
    """
    进化结果
    
    Attributes:
        domains: 检测到的专业领域
        core_entities: 提取的核心实体
        terminology: 识别的术语
        focus_areas: 分析的关注点
        expertise_level: 专业深度评估
        entity_count: 实体总数
        evolution_time: 进化时间
    """
    domains: List[str] = field(default_factory=list)
    core_entities: List[Dict[str, Any]] = field(default_factory=list)
    terminology: Dict[str, str] = field(default_factory=dict)
    focus_areas: List[str] = field(default_factory=list)
    expertise_level: str = "intermediate"
    entity_count: int = 0
    evolution_time: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "domains": self.domains,
            "core_entities": self.core_entities,
            "terminology": self.terminology,
            "focus_areas": self.focus_areas,
            "expertise_level": self.expertise_level,
            "entity_count": self.entity_count,
            "evolution_time": self.evolution_time
        }


class RapidEvolver:
    """
    快速进化器
    
    从导入的资料中快速学习用户专业能力，秒级更新 CoreMemory。
    
    核心功能:
    1. 专业领域识别: 基于关键词和实体分布
    2. 核心实体提取: 高频、高重要性实体
    3. 术语词典构建: 专业术语自动识别
    4. 用户关注点分析: 数据指标偏好
    5. 专业深度评估: 基于词汇深度和多样性
    """
    
    # 领域关键词映射
    DOMAIN_KEYWORDS = {
        "新能源汽车": [
            "新能源", "电动", "电池", "充电", "续航", "动力电池", "电动汽车",
            "BEV", "PHEV", "混动", "特斯拉", "比亚迪", "宁德时代", "蔚来", "小鹏", "理想"
        ],
        "动力电池": [
            "锂电池", "磷酸铁锂", "三元锂", "刀片电池", "麒麟电池", "LFP", "NCM",
            "电芯", "模组", "PACK", "CTP", "CTC", "能量密度", "充放电"
        ],
        "储能": [
            "储能", "储能系统", "ESS", "电池储能", "电网储能", "户储", "工商业储能",
            "调峰", "调频"
        ],
        "光伏": [
            "光伏", "太阳能", "硅片", "电池片", "组件", "逆变器", "PERC", "TOPCon", "HJT"
        ],
        "上游材料": [
            "锂矿", "锂盐", "碳酸锂", "氢氧化锂", "负极", "正极", "隔膜", "电解液",
            "六氟磷酸锂"
        ],
        "半导体": [
            "芯片", "半导体", "晶圆", "制程", "光刻", "EDA", "IP核", "封装", "测试"
        ],
        "人工智能": [
            "AI", "人工智能", "机器学习", "深度学习", "神经网络", "GPT", "LLM", "大模型"
        ],
        "金融投资": [
            "市值", "估值", "PE", "PB", "ROI", "融资", "IPO", "投资", "基金"
        ],
        "汽车": [
            "汽车", "车企", "整车", "乘用车", "商用车", "轿车", "SUV", "MPV"
        ],
        "医药": [
            "医药", "创新药", "仿制药", "临床试验", "CDE", "FDA", "生物药", "抗体"
        ]
    }
    
    # 数据指标关键词
    METRIC_KEYWORDS = [
        "市场份额", "营收", "净利润", "增长率", "销量", "产量", "产能",
        "毛利率", "净利率", "ROE", "ROA", "估值", "市值"
    ]
    
    # 技术术语模式
    TECH_TERM_PATTERNS = [
        r'([A-Z]{2,})',  # 大写缩写如 LFP, NCM, CTP
        r'([\u4e00-\u9fa5]{2,6}(?:技术|工艺|材料|系统))',  # 中文术语
    ]
    
    def __init__(self):
        """初始化快速进化器"""
        logger.info("RapidEvolver initialized")
    
    def evolve_from_content(
        self,
        content: str,
        existing_entities: Optional[List[str]] = None,
        existing_domains: Optional[List[str]] = None
    ) -> EvolutionResult:
        """
        从内容快速进化
        
        Args:
            content: 文本内容
            existing_entities: 已有实体（用于合并）
            existing_domains: 已有领域（用于合并）
        
        Returns:
            EvolutionResult: 进化结果
        """
        # 1. 检测专业领域
        domains = self.detect_domains(content)
        
        # 2. 提取核心实体
        core_entities = self.extract_core_entities(content, top_n=10)
        
        # 3. 构建术语词典
        terminology = self.extract_terminology(content)
        
        # 4. 分析关注点
        focus_areas = self.analyze_focus_areas(content)
        
        # 5. 评估专业深度
        expertise_level = self.assess_expertise_level(content, core_entities)
        
        result = EvolutionResult(
            domains=domains,
            core_entities=core_entities,
            terminology=terminology,
            focus_areas=focus_areas,
            expertise_level=expertise_level,
            entity_count=len(core_entities)
        )
        
        logger.info(f"Rapid evolution complete: {len(domains)} domains, {len(core_entities)} entities")
        return result
    
    def detect_domains(self, content: str) -> List[str]:
        """
        检测专业领域
        
        Args:
            content: 文本内容
        
        Returns:
            检测到的领域列表
        """
        domain_scores: Dict[str, int] = {}
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                count = content.count(keyword)
                if count > 0:
                    score += count
            if score > 0:
                domain_scores[domain] = score
        
        # 按分数排序，返回前 3 个领域
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        return [d[0] for d in sorted_domains[:3]]
    
    def extract_core_entities(
        self,
        content: str,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        提取核心实体
        
        Args:
            content: 文本内容
            top_n: 返回数量
        
        Returns:
            核心实体列表 [{name, importance, mention_count}]
        """
        # 实体识别模式
        entity_patterns = {
            "company": [
                r'([\u4e00-\u9fa5]{2,8})(?:公司|集团|有限|股份)',
                r'(宁德时代|比亚迪|特斯拉|蔚来|小鹏|理想|长城|吉利|华为|小米|百度|阿里|腾讯)',
            ],
            "product": [
                r'(Model\s*[3YXS])',
                r'(刀片电池|麒麟电池|神行电池|金砖电池)',
                r'([\u4e00-\u9fa5]{2,6})(?:系列|车型|产品)',
            ],
            "person": [
                r'(马斯克|王传福|李斌|何小鹏|李想|雷军|任正非)',
            ],
            "technology": [
                r'(LFP|NCM|NCA|CTP|CTC|CTB|4680|固态电池)',
            ]
        }
        
        # 统计实体出现次数
        entity_counts: Counter = Counter()
        
        for entity_type, patterns in entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if match and len(match) >= 2:
                        entity_counts[match] += 1
        
        # 计算重要性并排序
        entities = []
        total_mentions = sum(entity_counts.values()) or 1
        
        for name, count in entity_counts.most_common(top_n):
            importance = min(1.0, count / total_mentions * 5 + 0.3)
            entities.append({
                "name": name,
                "importance": round(importance, 2),
                "mention_count": count
            })
        
        return entities
    
    def extract_terminology(self, content: str) -> Dict[str, str]:
        """
        提取术语
        
        Args:
            content: 文本内容
        
        Returns:
            术语词典 {术语: 定义}
        """
        terminology: Dict[str, str] = {}
        
        # 技术术语定义模式
        term_definitions = {
            "LFP": "磷酸铁锂电池正极材料",
            "NCM": "三元锂电池正极材料（镍钴锰）",
            "CTP": "Cell to Pack，无模组电池包技术",
            "CTC": "Cell to Chassis，电池底盘一体化技术",
            "CTB": "Cell to Body，电池车身一体化技术",
            "刀片电池": "比亚迪LFP电池产品",
            "麒麟电池": "宁德时代第三代CTP电池产品",
            "固态电池": "使用固态电解质的锂电池",
        }
        
        # 检查术语出现
        for term, definition in term_definitions.items():
            if term in content:
                terminology[term] = definition
        
        # 提取其他技术术语
        for pattern in self.TECH_TERM_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and len(match) >= 2 and match not in terminology:
                    # 查找上下文作为简单定义
                    pos = content.find(match)
                    if pos != -1:
                        context = content[max(0, pos-20):min(len(content), pos+len(match)+50)]
                        terminology[match] = context.strip()
        
        return terminology
    
    def analyze_focus_areas(self, content: str) -> List[str]:
        """
        分析用户关注点
        
        Args:
            content: 文本内容
        
        Returns:
            关注点列表
        """
        focus_areas: List[str] = []
        
        for metric in self.METRIC_KEYWORDS:
            if metric in content:
                focus_areas.append(metric)
        
        return focus_areas[:5]
    
    def assess_expertise_level(
        self,
        content: str,
        entities: List[Dict[str, Any]]
    ) -> str:
        """
        评估专业深度
        
        Args:
            content: 文本内容
            entities: 已提取的实体
        
        Returns:
            expert/intermediate/novice
        """
        # 基于多个因素评估
        score = 0
        
        # 1. 实体多样性
        if len(entities) >= 10:
            score += 2
        elif len(entities) >= 5:
            score += 1
        
        # 2. 技术术语密度
        tech_term_count = 0
        for pattern in self.TECH_TERM_PATTERNS:
            tech_term_count += len(re.findall(pattern, content))
        
        if tech_term_count >= 10:
            score += 2
        elif tech_term_count >= 5:
            score += 1
        
        # 3. 内容深度（是否有数据对比、分析）
        if any(word in content for word in ["对比", "分析", "趋势", "预测", "增长"]):
            score += 1
        
        # 4. 数据密度
        number_count = len(re.findall(r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:万亿|亿|万)', content))
        if number_count >= 10:
            score += 1
        
        # 映射到级别
        if score >= 5:
            return "expert"
        elif score >= 3:
            return "intermediate"
        else:
            return "novice"
    
    def merge_with_existing(
        self,
        new_result: EvolutionResult,
        existing_profile: Dict[str, Any]
    ) -> EvolutionResult:
        """
        合并新结果与已有画像
        
        Args:
            new_result: 新的进化结果
            existing_profile: 已有的专业画像
        
        Returns:
            合并后的结果
        """
        # 合并领域
        merged_domains = list(set(
            new_result.domains + existing_profile.get("primary_domains", [])
        ))
        
        # 合并实体
        existing_entities = {e["name"]: e for e in existing_profile.get("core_entities", [])}
        for entity in new_result.core_entities:
            name = entity["name"]
            if name in existing_entities:
                # 合并：增加提及次数
                existing_entities[name]["mention_count"] += entity["mention_count"]
                existing_entities[name]["importance"] = max(
                    existing_entities[name]["importance"],
                    entity["importance"]
                )
            else:
                existing_entities[name] = entity
        
        merged_entities = sorted(
            existing_entities.values(),
            key=lambda e: e["importance"],
            reverse=True
        )[:20]
        
        # 合并术语
        merged_terminology = {**existing_profile.get("terminology", {}), **new_result.terminology}
        
        # 合并关注点
        merged_focus = list(set(
            new_result.focus_areas + existing_profile.get("focus_areas", [])
        ))
        
        return EvolutionResult(
            domains=merged_domains,
            core_entities=merged_entities,
            terminology=merged_terminology,
            focus_areas=merged_focus,
            expertise_level=new_result.expertise_level
        )