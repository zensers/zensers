"""
Agent 约束检查器

统一的约束检查接口，让 Agent 在执行过程中自动应用约束。
核心原则：每个 Agent 输出都经过约束检查，确保质量。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

from .constraints import SourceWhitelist, FactTracer, FactTrace
from .cross_validator import CrossValidator, ValidationResult
from .quality import ConfidenceGrader

logger = logging.getLogger(__name__)


@dataclass
class AgentOutputConstraint:
    """
    Agent 输出约束
    
    定义 Agent 输出必须满足的约束条件
    """
    
    # 是否要求有来源
    require_sources: bool = True
    
    # 最少来源数量
    min_sources: int = 1
    
    # 关键事实最少来源数量
    min_fact_sources: int = 2
    
    # 最低置信度要求
    min_confidence: str = "medium"  # high, medium, low
    
    # 是否要求交叉验证关键事实
    require_cross_validation: bool = True
    
    # 是否要求置信度标注
    require_confidence_label: bool = True


@dataclass
class ConstraintCheckResult:
    """约束检查结果"""
    
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # 来源验证结果
    source_validation: Optional[Dict[str, Any]] = None
    
    # 交叉验证结果
    cross_validation: Optional[ValidationResult] = None
    
    # 置信度评估
    confidence_assessment: Optional[Dict[str, Any]] = None
    
    # 溯源记录
    fact_traces: List[Dict[str, Any]] = field(default_factory=list)
    
    # 元数据
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AgentConstraintChecker:
    """
    Agent 约束检查器
    
    统一集成所有约束功能：
    1. 数据来源白名单验证
    2. 关键数字溯源
    3. 多源交叉验证
    4. 置信度自动计算
    """
    
    def __init__(
        self,
        whitelist_config_path: Optional[str] = None,
        trace_storage_path: Optional[str] = None
    ):
        """
        初始化约束检查器
        
        Args:
            whitelist_config_path: 白名单配置路径
            trace_storage_path: 溯源存储路径
        """
        self.whitelist = SourceWhitelist(config_path=whitelist_config_path)
        self.tracer = FactTracer(storage_path=trace_storage_path)
        self.validator = CrossValidator()
        self.grader = ConfidenceGrader()
        
        self.default_constraint = AgentOutputConstraint()
    
    def check_output(
        self,
        output: Dict[str, Any],
        constraint: Optional[AgentOutputConstraint] = None
    ) -> ConstraintCheckResult:
        """
        检查 Agent 输出是否符合约束
        
        Args:
            output: Agent 输出，应包含：
                    - content: 内容
                    - sources: 来源列表
                    - facts: 关键事实列表（可选）
            constraint: 约束条件，默认使用 default_constraint
        
        Returns:
            ConstraintCheckResult 检查结果
        """
        constraint = constraint or self.default_constraint
        errors = []
        warnings = []
        
        result = ConstraintCheckResult(passed=True)
        
        # 1. 检查来源
        sources = output.get("sources", [])
        source_validation = self._check_sources(sources, constraint)
        result.source_validation = source_validation
        
        if not source_validation["valid"] and constraint.require_sources:
            errors.extend(source_validation["errors"])
        warnings.extend(source_validation.get("warnings", []))
        
        # 2. 检查关键事实
        facts = output.get("facts", [])
        if facts:
            fact_results = self._check_facts(facts, constraint)
            result.fact_traces = fact_results["traces"]
            
            if fact_results["errors"]:
                errors.extend(fact_results["errors"])
            if fact_results["warnings"]:
                warnings.extend(fact_results["warnings"])
            
            # 交叉验证关键事实
            if constraint.require_cross_validation:
                cross_validation = self._cross_validate_facts(facts, constraint)
                result.cross_validation = cross_validation
                
                if cross_validation and cross_validation.status == "inconsistent":
                    warnings.append(f"存在 {len(cross_validation.conflicts)} 个数据冲突")
        
        # 3. 置信度评估
        confidence_assessment = self._assess_confidence(output, sources)
        result.confidence_assessment = confidence_assessment
        
        if constraint.require_confidence_label:
            if confidence_assessment["level"] == "unverified":
                errors.append("输出置信度过低")
            elif confidence_assessment["level"] == "low" and constraint.min_confidence in ["high", "medium"]:
                warnings.append("输出置信度较低")
        
        # 更新结果
        result.errors = errors
        result.warnings = warnings
        result.passed = len(errors) == 0
        
        return result
    
    def _check_sources(
        self,
        sources: List[Dict[str, Any]],
        constraint: AgentOutputConstraint
    ) -> Dict[str, Any]:
        """检查来源"""
        errors = []
        warnings = []
        
        if not sources:
            if constraint.require_sources:
                errors.append("缺少数据来源")
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings
            }
        
        if len(sources) < constraint.min_sources:
            errors.append(f"来源数量不足，至少需要 {constraint.min_sources} 个")
        
        # 检查每个来源的可信度
        trusted_count = 0
        for source in sources:
            source_name = source.get("name", "")
            source_url = source.get("url", "")
            
            # 检查白名单
            if self.whitelist.is_trusted(source_name):
                trusted_count += 1
            elif source_url and self.whitelist.validate_url(source_url):
                trusted_count += 1
            else:
                warnings.append(f"来源 '{source_name}' 不在可信白名单中")
        
        return {
            "valid": len(errors) == 0,
            "trusted_count": trusted_count,
            "total_count": len(sources),
            "errors": errors,
            "warnings": warnings
        }
    
    def _check_facts(
        self,
        facts: List[Dict[str, Any]],
        constraint: AgentOutputConstraint
    ) -> Dict[str, Any]:
        """检查关键事实"""
        errors = []
        warnings = []
        traces = []
        
        for fact in facts:
            fact_id = fact.get("id", f"fact-{datetime.now().timestamp()}")
            fact_statement = fact.get("statement", fact.get("content", ""))
            fact_sources = fact.get("sources", [])
            
            # 记录溯源
            if fact_sources:
                primary_source = fact_sources[0]
                trace = self.tracer.trace_fact(
                    fact_id=fact_id,
                    fact_statement=fact_statement,
                    source=primary_source.get("name", "未知来源"),
                    source_url=primary_source.get("url"),
                    confidence=fact.get("confidence", "medium")
                )
                traces.append({
                    "fact_id": fact_id,
                    "statement": fact_statement,
                    "source": primary_source.get("name"),
                    "confidence": trace.confidence
                })
            
            # 检查事实来源数量
            if len(fact_sources) < constraint.min_fact_sources:
                warnings.append(f"事实 '{fact_statement[:30]}...' 来源不足")
        
        return {
            "traces": traces,
            "errors": errors,
            "warnings": warnings
        }
    
    def _cross_validate_facts(
        self,
        facts: List[Dict[str, Any]],
        constraint: AgentOutputConstraint
    ) -> Optional[ValidationResult]:
        """交叉验证关键事实"""
        # 只验证有多个来源的事实
        multi_source_facts = [f for f in facts if len(f.get("sources", [])) >= 2]
        
        if not multi_source_facts:
            return None
        
        # 验证第一个有多个来源的事实
        fact = multi_source_facts[0]
        sources = fact.get("sources", [])
        
        return self.validator.validate(
            claim=fact.get("statement", fact.get("content", "")),
            sources=sources
        )
    
    def _assess_confidence(
        self,
        output: Dict[str, Any],
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """评估置信度"""
        # 检查是否有显式置信度
        explicit_confidence = output.get("confidence")
        
        if explicit_confidence is not None:
            return self.grader.grade(explicit_score=int(explicit_confidence * 100))
        
        # 自动计算置信度
        has_source = len(sources) > 0
        
        # 判断来源等级
        source_tier = None
        if sources:
            source_name = sources[0].get("name", "")
            source_tier = self.whitelist.get_source_tier(source_name)
        
        # 判断是否交叉验证
        cross_verified = False
        facts = output.get("facts", [])
        if facts:
            for fact in facts:
                if len(fact.get("sources", [])) >= 2:
                    cross_verified = True
                    break
        
        return self.grader.grade(
            has_source=has_source,
            source_tier=source_tier,
            cross_verified=cross_verified
        )
    
    def trace_fact(
        self,
        fact_id: str,
        fact_statement: str,
        source: str,
        **kwargs
    ) -> FactTrace:
        """
        记录事实溯源（便捷方法）
        
        Args:
            fact_id: 事实ID
            fact_statement: 事实陈述
            source: 来源
            **kwargs: 其他参数
        
        Returns:
            FactTrace 溯源记录
        """
        return self.tracer.trace_fact(
            fact_id=fact_id,
            fact_statement=fact_statement,
            source=source,
            **kwargs
        )
    
    def validate_claim(
        self,
        claim: str,
        sources: List[Dict[str, Any]],
        tolerance: float = 0.1
    ) -> ValidationResult:
        """
        验证声明（便捷方法）
        
        Args:
            claim: 声明
            sources: 来源列表
            tolerance: 容差
        
        Returns:
            ValidationResult 验证结果
        """
        return self.validator.validate(claim, sources, tolerance)
    
    def get_source_tier(self, source_name: str) -> Optional[str]:
        """获取来源等级（便捷方法）"""
        return self.whitelist.get_source_tier(source_name)
    
    def is_source_trusted(self, source_name: str) -> bool:
        """检查来源是否可信（便捷方法）"""
        return self.whitelist.is_trusted(source_name)


# 创建默认实例
default_checker = AgentConstraintChecker()


def check_agent_output(
    output: Dict[str, Any],
    constraint: Optional[AgentOutputConstraint] = None
) -> ConstraintCheckResult:
    """
    检查 Agent 输出（便捷函数）
    
    使用默认检查器实例
    
    Args:
        output: Agent 输出
        constraint: 约束条件
    
    Returns:
        ConstraintCheckResult 检查结果
    """
    return default_checker.check_output(output, constraint)