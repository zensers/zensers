# -*- coding: utf-8 -*-
"""
质量元数据提取器
================

从Skill原始输出中提取质量元数据，不修改原始数据。

设计原则：
1. 不修改原始数据 - Skill输出保持原格式
2. 提取而非转换 - 从原始数据提取质量元数据
3. 容错处理 - 缺失字段时使用默认值

使用示例:
    extractor = QualityMetadataExtractor()
    metadata = extractor.extract(raw_output, skill_name="web_search")
    
    # metadata 包含:
    # - quality_score: 质量分数 (0-100)
    # - data_volume: 数据量
    # - sources: 来源列表
    # - extraction_confidence: 提取置信度
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SourceInfo:
    """来源信息"""
    url: str
    title: str = ""
    credibility: str = "unknown"  # tier1, tier2, tier3, unknown
    source_type: str = "unknown"  # official, news, academic, social, unknown
    fetched_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "url": self.url,
            "title": self.title,
            "credibility": self.credibility,
            "source_type": self.source_type,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


@dataclass
class QualityMetadata:
    """质量元数据"""
    quality_score: float = 50.0           # 质量分数 (0-100)
    data_volume: int = 0                  # 数据量
    sources: List[SourceInfo] = field(default_factory=list)
    extraction_confidence: float = 0.0    # 提取置信度 (0-1)
    skill_name: str = ""
    extracted_at: datetime = field(default_factory=datetime.now)
    
    # 扩展字段
    coverage_score: float = 0.0           # 覆盖度分数
    freshness_score: float = 0.0          # 新鲜度分数
    credibility_score: float = 0.0        # 可信度分数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "quality_score": self.quality_score,
            "data_volume": self.data_volume,
            "sources": [s.to_dict() for s in self.sources],
            "extraction_confidence": self.extraction_confidence,
            "skill_name": self.skill_name,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "coverage_score": self.coverage_score,
            "freshness_score": self.freshness_score,
            "credibility_score": self.credibility_score,
        }


class QualityMetadataExtractor:
    """
    质量元数据提取器
    
    从Skill原始输出中提取质量元数据，不修改原始数据。
    
    Attributes:
        QUALITY_FIELDS: 质量分数相关字段名
        SOURCE_FIELDS: 来源URL相关字段名
        RESULT_LIST_FIELDS: 结果列表字段名
    """
    
    # 质量分数相关字段
    QUALITY_FIELDS = [
        "quality_score", "score", "credibility", "confidence",
        "relevance_score", "accuracy_score"
    ]
    
    # 来源URL相关字段
    SOURCE_FIELDS = [
        "url", "link", "href", "source_url", "web_url", "page_url"
    ]
    
    # 结果列表字段
    RESULT_LIST_FIELDS = [
        "results", "items", "data", "records", "documents",
        "articles", "entries", "list"
    ]
    
    # 高可信度来源关键词
    TIER1_KEYWORDS = [
        "gov.cn", "gov", "官方", "统计局", "工信部", "发改委",
        "世界银行", "worldbank", "imf", "oecd", "un.org",
        "nature", "science", "ieee", "acm", "springer",
    ]
    
    # 中等可信度来源关键词
    TIER2_KEYWORDS = [
        "reuters", "bloomberg", "ft.com", "wsj", "economist",
        "caixin", "财新", "36kr", "huxiu", "虎嗅",
        "mckinsey", "bcg", "deloitte", "pwc", "kpmg",
    ]
    
    def __init__(self):
        """初始化提取器"""
        pass
    
    def extract(
        self, 
        raw_output: Dict[str, Any], 
        skill_name: str = ""
    ) -> QualityMetadata:
        """
        从原始输出提取质量元数据
        
        Args:
            raw_output: Skill原始输出
            skill_name: Skill名称
            
        Returns:
            QualityMetadata: 提取的质量元数据
        """
        # **修复**: 确保raw_output是字典类型
        if not isinstance(raw_output, dict):
            logger.warning(f"[MetadataExtractor] raw_output不是字典类型: {type(raw_output)}, 进行包装")
            if isinstance(raw_output, str):
                # 尝试解析JSON
                try:
                    import json
                    parsed = json.loads(raw_output)
                    if isinstance(parsed, dict):
                        raw_output = parsed
                    else:
                        raw_output = {"raw_text": raw_output}
                except (json.JSONDecodeError, ValueError):
                    raw_output = {"raw_text": raw_output}
            elif isinstance(raw_output, list):
                raw_output = {"items": raw_output}
            else:
                raw_output = {}
        
        try:
            # 提取基础信息
            quality_score = self._extract_score(raw_output)
            data_volume = self._calculate_volume(raw_output)
            sources = self._extract_sources(raw_output)
            
            # 计算各项分数
            coverage_score = self._calculate_coverage(raw_output, data_volume)
            freshness_score = self._calculate_freshness(raw_output)
            credibility_score = self._calculate_credibility(sources)
            
            # 计算提取置信度
            extraction_confidence = self._calculate_confidence(raw_output)
            
            # 综合质量分数（如果没有直接提供）
            if quality_score == 50.0:  # 默认值
                quality_score = self._calculate_composite_score(
                    coverage_score, freshness_score, credibility_score
                )
            
            metadata = QualityMetadata(
                quality_score=quality_score,
                data_volume=data_volume,
                sources=sources,
                extraction_confidence=extraction_confidence,
                skill_name=skill_name,
                coverage_score=coverage_score,
                freshness_score=freshness_score,
                credibility_score=credibility_score,
            )
            
            logger.debug(
                f"[MetadataExtractor] 提取完成: "
                f"score={quality_score:.1f}, volume={data_volume}, "
                f"sources={len(sources)}, confidence={extraction_confidence:.2f}"
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"[MetadataExtractor] 提取失败: {e}")
            return QualityMetadata(
                quality_score=50.0,
                skill_name=skill_name,
            )
    
    def _extract_score(self, data: Dict[str, Any]) -> float:
        """
        提取质量分数
        
        优先级：
        1. 直接的质量分数字段
        2. 置信度/可信度字段
        3. 默认值50
        """
        for field in self.QUALITY_FIELDS:
            if field in data:
                value = data[field]
                if isinstance(value, (int, float)):
                    # 如果值在0-1范围，转换为0-100
                    return float(value) if value > 1 else float(value) * 100
        
        # 检查嵌套结构
        if "quality_stats" in data:
            stats = data["quality_stats"]
            if isinstance(stats, dict):
                for field in self.QUALITY_FIELDS:
                    if field in stats:
                        value = stats[field]
                        if isinstance(value, (int, float)):
                            return float(value) if value > 1 else float(value) * 100
        
        return 50.0  # 默认中等质量
    
    def _calculate_volume(self, data: Dict[str, Any]) -> int:
        """
        计算数据量
        
        统计结果列表中的条目数量
        """
        max_volume = 0
        
        for field in self.RESULT_LIST_FIELDS:
            if field in data and isinstance(data[field], list):
                volume = len(data[field])
                max_volume = max(max_volume, volume)
        
        # 检查嵌套结构
        if "data" in data and isinstance(data["data"], dict):
            inner_data = data["data"]
            for field in self.RESULT_LIST_FIELDS:
                if field in inner_data and isinstance(inner_data[field], list):
                    volume = len(inner_data[field])
                    max_volume = max(max_volume, volume)
        
        return max_volume
    
    def _extract_sources(self, data: Dict[str, Any]) -> List[SourceInfo]:
        """
        提取来源信息
        
        从结果列表中提取URL、标题、可信度等信息
        """
        sources = []
        seen_urls = set()
        
        def extract_from_list(items: List[Any]):
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # 提取URL
                url = None
                for field in self.SOURCE_FIELDS:
                    if field in item and item[field]:
                        url = str(item[field])
                        break
                
                if not url or url in seen_urls:
                    continue
                
                seen_urls.add(url)
                
                # 提取标题
                title = item.get("title", "") or item.get("name", "") or ""
                
                # 判断可信度
                credibility = self._judge_credibility(url)
                
                # 判断来源类型
                source_type = self._judge_source_type(url, item)
                
                sources.append(SourceInfo(
                    url=url,
                    title=str(title),
                    credibility=credibility,
                    source_type=source_type,
                ))
        
        # 从各个可能的结果列表中提取
        for field in self.RESULT_LIST_FIELDS:
            if field in data and isinstance(data[field], list):
                extract_from_list(data[field])
        
        return sources
    
    def _judge_credibility(self, url: str) -> str:
        """
        判断来源可信度
        
        Args:
            url: 来源URL
            
        Returns:
            可信度等级: tier1, tier2, tier3, unknown
        """
        url_lower = url.lower()
        
        # 检查高可信度来源
        for keyword in self.TIER1_KEYWORDS:
            if keyword.lower() in url_lower:
                return "tier1"
        
        # 检查中等可信度来源
        for keyword in self.TIER2_KEYWORDS:
            if keyword.lower() in url_lower:
                return "tier2"
        
        # 检查低可信度特征
        low_quality_patterns = [
            "blog", "forum", "bbs", "comment", "review",
            "social", "facebook", "twitter", "weibo",
        ]
        for pattern in low_quality_patterns:
            if pattern in url_lower:
                return "tier3"
        
        return "unknown"
    
    def _judge_source_type(self, url: str, item: Dict[str, Any]) -> str:
        """
        判断来源类型
        
        Args:
            url: 来源URL
            item: 数据项
            
        Returns:
            来源类型: official, news, academic, social, unknown
        """
        url_lower = url.lower()
        
        # 官方来源
        if any(k in url_lower for k in ["gov", "官方", "official"]):
            return "official"
        
        # 学术来源
        if any(k in url_lower for k in ["edu", "academic", "paper", "arxiv", "scholar"]):
            return "academic"
        
        # 新闻来源
        if any(k in url_lower for k in ["news", "新闻", "article", "报道"]):
            return "news"
        
        # 社交媒体
        if any(k in url_lower for k in ["social", "weibo", "twitter", "facebook"]):
            return "social"
        
        return "unknown"
    
    def _calculate_coverage(self, data: Dict[str, Any], data_volume: int) -> float:
        """
        计算覆盖度分数
        
        基于数据量和字段完整性
        """
        score = 0.0
        
        # 数据量评分 (0-40分)
        if data_volume >= 20:
            score += 40
        elif data_volume >= 10:
            score += 30
        elif data_volume >= 5:
            score += 20
        elif data_volume >= 3:
            score += 10
        
        # 字段完整性评分 (0-30分)
        important_fields = ["title", "content", "url", "date", "source"]
        if isinstance(data, dict):
            present_fields = sum(1 for f in important_fields if f in data)
            score += (present_fields / len(important_fields)) * 30
        
        # 结构化程度评分 (0-30分)
        if any(f in data for f in self.RESULT_LIST_FIELDS):
            score += 15
        if "quality_stats" in data or "metadata" in data:
            score += 15
        
        return min(100.0, score)
    
    def _calculate_freshness(self, data: Dict[str, Any]) -> float:
        """
        计算新鲜度分数
        
        基于数据时间戳
        """
        score = 50.0  # 默认中等新鲜度
        
        # 检查时间字段
        time_fields = ["date", "published_at", "created_at", "timestamp", "time"]
        for field in time_fields:
            if field in data:
                try:
                    # 尝试解析时间
                    value = data[field]
                    if isinstance(value, str):
                        # 简单判断是否包含年份
                        if "2024" in value or "2025" in value or "2026" in value:
                            score = 90.0
                        elif "2023" in value:
                            score = 70.0
                        elif "2022" in value:
                            score = 50.0
                        else:
                            score = 60.0
                    break
                except Exception:
                    pass
        
        return score
    
    def _calculate_credibility(self, sources: List[SourceInfo]) -> float:
        """
        计算可信度分数
        
        基于来源可信度分布
        """
        if not sources:
            return 50.0
        
        # 统计各层级来源数量
        tier1_count = sum(1 for s in sources if s.credibility == "tier1")
        tier2_count = sum(1 for s in sources if s.credibility == "tier2")
        tier3_count = sum(1 for s in sources if s.credibility == "tier3")
        total = len(sources)
        
        # 计算加权分数
        score = (
            (tier1_count * 100 + tier2_count * 70 + tier3_count * 30) / total
        )
        
        return min(100.0, score)
    
    def _calculate_confidence(self, data: Dict[str, Any]) -> float:
        """
        计算提取置信度
        
        基于数据结构的完整性
        """
        confidence = 0.0
        
        # 有质量分数字段
        if any(f in data for f in self.QUALITY_FIELDS):
            confidence += 0.3
        
        # 有结果列表
        if any(f in data for f in self.RESULT_LIST_FIELDS):
            confidence += 0.3
        
        # 有质量统计信息
        if data.get("quality_stats"):
            confidence += 0.2
        
        # 有元数据
        if data.get("metadata"):
            confidence += 0.1
        
        # 有来源信息
        if any(f in data for f in self.SOURCE_FIELDS):
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _calculate_composite_score(
        self,
        coverage: float,
        freshness: float,
        credibility: float
    ) -> float:
        """
        计算综合质量分数
        
        权重：
        - 覆盖度: 40%
        - 新鲜度: 20%
        - 可信度: 40%
        """
        return (
            coverage * 0.4 +
            freshness * 0.2 +
            credibility * 0.4
        )
