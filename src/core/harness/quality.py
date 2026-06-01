"""
质量闸门核心组件

提供置信度分级和质量检查功能，确保最终输出质量。
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class GradingResult:
    """分级结果"""
    level: str  # high, medium, low, unverified
    score: int  # 0-100
    reasons: List[str]


class ConfidenceGrader:
    """
    置信度分级器
    
    根据数据来源和验证情况自动分级置信度。
    """
    
    def __init__(self):
        """初始化分级器"""
        # 等级阈值
        self.thresholds = {
            "high": 80,
            "medium": 40,
            "low": 20,
            "unverified": 0
        }
        
        # 来源权重
        self.source_weights = {
            "tier1": 40,  # 政府官网、上市公司财报
            "tier2": 25,  # 知名媒体、行业协会
            "tier3": 15,  # 一般媒体
            None: 0
        }
    
    def grade(
        self,
        has_source: bool = False,
        source_tier: Optional[str] = None,
        cross_verified: bool = False,
        data_fresh_days: int = 30,
        explicit_score: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        分级置信度
        
        Args:
            has_source: 是否有来源
            source_tier: 来源等级
            cross_verified: 是否交叉验证
            data_fresh_days: 数据新鲜度（天）
            explicit_score: 显式分数（如果提供则直接使用）
            
        Returns:
            分级结果字典
        """
        if explicit_score is not None:
            return self._score_to_result(explicit_score)
        
        score = 0
        reasons = []
        
        # 基础分：是否有来源
        if has_source:
            score += 20
            reasons.append("有明确数据来源")
        else:
            reasons.append("缺少数据来源")
        
        # 来源等级分
        source_score = self.source_weights.get(source_tier, 0)
        score += source_score
        if source_tier:
            reasons.append(f"来源等级: {source_tier} (+{source_score}分)")
        elif has_source:
            reasons.append("来源等级未知")
        
        # 交叉验证分
        if cross_verified:
            score += 20
            reasons.append("已通过交叉验证 (+20分)")
        else:
            reasons.append("未进行交叉验证")
        
        # 新鲜度分
        if data_fresh_days <= 7:
            score += 20
            reasons.append("数据非常新鲜 (+20分)")
        elif data_fresh_days <= 30:
            score += 15
            reasons.append("数据较新鲜 (+15分)")
        elif data_fresh_days <= 90:
            score += 10
            reasons.append("数据新鲜度一般 (+10分)")
        else:
            reasons.append("数据较旧")
        
        # 确保分数在0-100范围内
        score = max(0, min(100, score))
        
        return self._score_to_result(score, reasons)
    
    def _score_to_result(self, score: int, reasons: Optional[List[str]] = None) -> Dict[str, Any]:
        """将分数转换为分级结果"""
        if score >= self.thresholds["high"]:
            level = "high"
        elif score >= self.thresholds["medium"]:
            level = "medium"
        elif score >= self.thresholds["low"]:
            level = "low"
        else:
            level = "unverified"
        
        return {
            "level": level,
            "score": score,
            "reasons": reasons or []
        }


class QualityGate:
    """
    质量闸门
    
    最终输出前的质量检查，确保报告符合标准。
    """
    
    def __init__(self):
        """初始化质量闸门"""
        self.grader = ConfidenceGrader()
        
        # 可信来源白名单（简化版，实际应从SourceWhitelist获取）
        self.trusted_sources = {
            "政府官网", "国家统计局", "上市公司财报",
            "知名媒体", "行业协会", "学术期刊"
        }
        
        # 不可信来源
        self.untrusted_sources = {
            "匿名论坛", "未经验证的自媒体", "个人博客",
            "社交媒体未经证实消息"
        }
    
    def check(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查报告质量
        
        Args:
            report: 报告字典
            
        Returns:
            检查结果字典
        """
        errors = []
        warnings = []
        
        # 检查标题
        title = report.get("title", "")
        if not title or not title.strip():
            errors.append("报告标题不能为空")
        elif len(title) < 5:
            warnings.append("报告标题过短")
        
        # 检查章节
        sections = report.get("sections", [])
        if not sections:
            errors.append("报告必须包含至少一个章节")
        else:
            for i, section in enumerate(sections):
                if not section.get("title"):
                    errors.append(f"第{i+1}节缺少标题")
                if not section.get("content"):
                    warnings.append(f"第{i+1}节内容为空")
        
        # 检查事实置信度
        facts = report.get("facts", [])
        unverified_count = 0
        low_confidence_count = 0
        
        for fact in facts:
            confidence = fact.get("confidence", "unverified")
            if confidence == "unverified":
                unverified_count += 1
            elif confidence == "low":
                low_confidence_count += 1
        
        if unverified_count > 0:
            errors.append(f"存在{unverified_count}个未验证的事实")
        
        if low_confidence_count > len(facts) * 0.5:
            warnings.append("超过50%的事实置信度较低")
        
        # 检查来源
        sources = report.get("sources", [])
        if not sources:
            warnings.append("报告没有列出数据来源")
        else:
            for source in sources:
                if source in self.untrusted_sources:
                    errors.append(f"使用了不可信来源: {source}")
                elif source not in self.trusted_sources:
                    warnings.append(f"来源未在白名单中: {source}")
        
        # 计算质量分数
        quality_score = self.get_quality_score(report)
        
        # 根据质量分数判断
        if quality_score < 30:
            errors.append(f"报告质量分数过低 ({quality_score}/100)")
        elif quality_score < 60:
            warnings.append(f"报告质量分数偏低 ({quality_score}/100)")
        
        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "quality_score": quality_score,
            "checked_at": datetime.now().isoformat()
        }
    
    def get_quality_score(self, report: Dict[str, Any]) -> int:
        """
        计算报告质量分数
        
        Args:
            report: 报告字典
            
        Returns:
            质量分数 (0-100)
        """
        score = 50  # 基础分
        
        # 标题质量
        title = report.get("title", "")
        if title and len(title) >= 10:
            score += 10
        
        # 章节数量
        sections = report.get("sections", [])
        if len(sections) >= 3:
            score += 15
        elif len(sections) >= 1:
            score += 10
        
        # 事实质量
        facts = report.get("facts", [])
        if facts:
            high_confidence = sum(1 for f in facts if f.get("confidence") == "high")
            medium_confidence = sum(1 for f in facts if f.get("confidence") == "medium")
            
            confidence_ratio = (high_confidence * 2 + medium_confidence) / (len(facts) * 2)
            score += int(confidence_ratio * 20)
        
        # 来源质量
        sources = report.get("sources", [])
        if sources:
            trusted_count = sum(1 for s in sources if s in self.trusted_sources)
            source_ratio = trusted_count / len(sources)
            score += int(source_ratio * 15)
        
        return max(0, min(100, score))
