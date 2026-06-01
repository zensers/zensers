"""
多源交叉验证器

确保关键结论至少有2个独立来源验证。
核心原则：宁可标注不确定，也不传播错误信息。
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    status: str  # verified, inconsistent, insufficient_sources
    message: str
    confidence: str = "medium"  # high, medium, low, unverified
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class CrossValidator:
    """
    多源交叉验证器
    
    核心功能：
    1. 数值一致性检查
    2. 时间一致性检查
    3. 冲突检测与标记
    4. 置信度计算
    """
    
    # 最少来源数量
    MIN_SOURCES = 2
    
    # 默认容差（10%）
    DEFAULT_TOLERANCE = 0.1
    
    def __init__(self, min_sources: int = 2):
        """
        初始化验证器
        
        Args:
            min_sources: 最少来源数量，默认2
        """
        self.min_sources = min_sources if min_sources is not None else self.MIN_SOURCES
    
    def validate(
        self,
        claim: str,
        sources: List[Dict[str, Any]],
        tolerance: float = 0.1
    ) -> ValidationResult:
        """
        验证声明
        
        Args:
            claim: 待验证的声明
            sources: 来源列表，每个来源应包含：
                     - name: 来源名称
                     - value: 数值
                     - url: 来源URL（可选）
                     - time: 时间（可选）
            tolerance: 数值误差容忍度，默认10%
        
        Returns:
            ValidationResult 验证结果
        """
        tolerance = tolerance or self.DEFAULT_TOLERANCE
        
        # 1. 检查来源数量
        valid_sources = [s for s in sources if s.get("value")]
        
        if len(valid_sources) < self.min_sources:
            return ValidationResult(
                status="insufficient_sources",
                message=f"来源不足，至少需要{self.min_sources}个来源，当前只有{len(valid_sources)}个有效来源",
                confidence="unverified"
            )
        
        # 2. 数值一致性检查
        values = [s.get("value") for s in valid_sources]
        numerical_consistent = self.check_numerical_consistency(values, tolerance)
        
        # 3. 时间一致性检查
        time_consistent = self.check_time_consistency(valid_sources)
        
        # 4. 检测冲突
        conflicts = []
        if not numerical_consistent:
            conflicts = self._detect_value_conflicts(valid_sources, tolerance)
        
        # 5. 计算置信度
        if conflicts:
            return ValidationResult(
                status="inconsistent",
                message=f"数据存在冲突，请人工核实",
                confidence="low",
                conflicts=conflicts,
                details={
                    "numerical_consistency": numerical_consistent,
                    "time_consistency": time_consistent
                }
            )
        
        # 6. 一致通过
        source_tiers = [s.get("tier", "tier3") for s in valid_sources]
        confidence = self.calculate_confidence(
            source_count=len(valid_sources),
            consistency_score=1.0 if numerical_consistent and time_consistent else 0.8,
            source_tiers=source_tiers
        )
        
        return ValidationResult(
            status="verified",
            message=f"验证通过，{len(valid_sources)}个来源一致",
            confidence=confidence,
            details={
                "numerical_consistency": numerical_consistent,
                "time_consistency": time_consistent,
                "source_count": len(valid_sources)
            }
        )
    
    def check_numerical_consistency(
        self,
        values: List[Any],
        tolerance: float = 0.1
    ) -> bool:
        """
        检查数值一致性
        
        Args:
            values: 数值列表（可能包含单位）
            tolerance: 容差，默认10%
        
        Returns:
            True 如果所有数值在容差范围内一致
        """
        tolerance = tolerance or self.DEFAULT_TOLERANCE
        
        # 提取数值
        numeric_values = []
        for v in values:
            if v is None:
                continue
            num = self.extract_numeric_value(str(v))
            if num is not None:
                numeric_values.append(num)
        
        if len(numeric_values) < 2:
            return True  # 单个值无法比较，默认一致
        
        # 计算平均值
        avg = sum(numeric_values) / len(numeric_values)
        
        # 检查每个值是否在容差范围内
        for num in numeric_values:
            if avg == 0:
                if num != 0:
                    return False
            elif abs(num - avg) / avg > tolerance:
                return False
        
        return True
    
    def extract_numeric_value(self, value_str: str) -> Optional[float]:
        """
        从字符串中提取数值
        
        Args:
            value_str: 包含单位的字符串，如 "1.2万亿"、"5000亿"、"35%"
        
        Returns:
            提取的数值（单位统一为亿）
        """
        if not value_str:
            return None
        
        value_str = str(value_str).strip()
        
        # 提取数字部分
        match = re.search(r'[\d.]+', value_str)
        if not match:
            return None
        
        try:
            num = float(match.group())
        except ValueError:
            return None
        
        # 单位转换
        if '万亿' in value_str:
            num *= 10000  # 万亿 -> 亿
        elif '亿' in value_str:
            pass  # 已经是亿
        elif '万' in value_str:
            num /= 10000  # 万 -> 亿
        elif '%' in value_str:
            pass  # 百分比不转换
        
        return num
    
    def check_time_consistency(self, sources: List[Dict[str, Any]]) -> bool:
        """
        检查时间一致性
        
        Args:
            sources: 来源列表
        
        Returns:
            True 如果时间范围一致
        """
        times = []
        for s in sources:
            time_str = s.get("time")
            if time_str:
                # 提取年份
                year_match = re.search(r'(\d{4})', str(time_str))
                if year_match:
                    times.append(year_match.group(1))
        
        if len(times) < 2:
            return True  # 单个时间无法比较
        
        # 检查年份是否一致
        return len(set(times)) == 1
    
    def _detect_value_conflicts(
        self,
        sources: List[Dict[str, Any]],
        tolerance: float
    ) -> List[Dict[str, Any]]:
        """检测数值冲突"""
        conflicts = []
        values = [(s.get("name"), s.get("value")) for s in sources if s.get("value")]
        
        for i, (name1, val1) in enumerate(values):
            for name2, val2 in values[i+1:]:
                num1 = self.extract_numeric_value(str(val1))
                num2 = self.extract_numeric_value(str(val2))
                
                if num1 is None or num2 is None:
                    continue
                
                avg = (num1 + num2) / 2
                if avg > 0 and abs(num1 - num2) / avg > tolerance:
                    conflicts.append({
                        "source1": name1,
                        "value1": val1,
                        "source2": name2,
                        "value2": val2,
                        "difference": f"{abs(num1 - num2):.2f}亿"
                    })
        
        return conflicts
    
    def calculate_confidence(
        self,
        source_count: int,
        consistency_score: float,
        source_tiers: List[str]
    ) -> str:
        """
        计算置信度
        
        Args:
            source_count: 来源数量
            consistency_score: 一致性分数 (0-1)
            source_tiers: 来源等级列表
        
        Returns:
            置信度等级：high, medium, low, unverified
        """
        # 基础分
        score = 0
        
        # 来源数量分 (0-40)
        if source_count >= 3:
            score += 40
        elif source_count >= 2:
            score += 30
        else:
            score += 10
        
        # 一致性分 (0-30)
        score += int(consistency_score * 30)
        
        # 来源等级分 (0-30)
        tier_scores = {"tier1": 15, "tier2": 10, "tier3": 5}
        for tier in source_tiers:
            score += tier_scores.get(tier, 5)
        score = min(score, 30)  # 上限30
        
        # 分数到置信度
        if score >= 70:
            return "high"
        elif score >= 50:
            return "medium"
        elif score >= 30:
            return "low"
        else:
            return "unverified"
    
    def generate_report(
        self,
        claim: str,
        sources: List[Dict[str, Any]],
        tolerance: float = 0.1
    ) -> Dict[str, Any]:
        """
        生成验证报告
        
        Args:
            claim: 声明
            sources: 来源列表
            tolerance: 容差
        
        Returns:
            验证报告字典
        """
        result = self.validate(claim, sources, tolerance)
        
        return {
            "claim": claim,
            "status": result.status,
            "confidence": result.confidence,
            "message": result.message,
            "source_count": len(sources),
            "conflicts": result.conflicts,
            "checks": {
                "numerical_consistency": result.details.get("numerical_consistency", False),
                "time_consistency": result.details.get("time_consistency", False)
            },
            "validated_at": datetime.now().isoformat()
        }