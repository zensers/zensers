# -*- coding: utf-8 -*-
"""
级联更新分析器

Phase 3.1: 数据一致性保障

职责:
- 分析章节间的数据依赖关系
- 识别修订操作的级联影响
- 生成数据一致性检查建议
- 提供级联更新建议

示例:
- 修订"市场规模" → 影响"竞争格局"、"投资机会"
- 修订"政策环境" → 影响"发展趋势"、"投资机会"
"""

__all__ = [
    "CascadeUpdateAnalyzer",
    "CascadeImpact",
    "ConsistencyCheck",
]

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyCheck:
    """
    数据一致性检查项
    
    Attributes:
        source: 源章节 (被修订的章节)
        target: 目标章节 (需要检查的章节)
        data_points: 相关数据点
        check_type: 检查类型 (value_match/trend_consistent/ratio_valid)
        description: 检查描述
    """
    source: str
    target: str
    data_points: List[str] = field(default_factory=list)
    check_type: str = "value_match"
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "source": self.source,
            "target": self.target,
            "data_points": self.data_points,
            "check_type": self.check_type,
            "description": self.description,
        }


@dataclass
class CascadeImpact:
    """
    级联影响分析结果
    
    Attributes:
        affected_sections: 受影响的章节列表
        data_consistency_checks: 数据一致性检查项
        suggested_updates: 建议的级联更新
        cascade_depth: 级联深度
        risk_level: 风险等级 (low/medium/high)
    """
    affected_sections: List[str] = field(default_factory=list)
    data_consistency_checks: List[ConsistencyCheck] = field(default_factory=list)
    suggested_updates: List[Dict[str, Any]] = field(default_factory=list)
    cascade_depth: int = 0
    risk_level: str = "low"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "affected_sections": self.affected_sections,
            "data_consistency_checks": [c.to_dict() for c in self.data_consistency_checks],
            "suggested_updates": self.suggested_updates,
            "cascade_depth": self.cascade_depth,
            "risk_level": self.risk_level,
        }


class CascadeUpdateAnalyzer:
    """
    级联更新分析器
    
    分析章节间的数据依赖关系，识别修订操作的级联影响。
    
    使用方式:
        analyzer = CascadeUpdateAnalyzer()
        impact = analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=["市场规模", "竞争格局", "发展趋势", "投资建议"]
        )
        # 返回: CascadeImpact(affected_sections=["竞争格局", "投资建议"], ...)
    """
    
    # 章节间数据依赖关系 (配置驱动)
    SECTION_DEPENDENCIES: Dict[str, Dict[str, Any]] = {
        # 市场规模 → 影响竞争格局和投资机会
        "市场规模": {
            "affects": ["竞争格局", "投资机会", "发展趋势"],
            "data_points": ["市场规模", "增长率", "市场份额", "市场容量"],
            "check_type": "value_match",
        },
        # 竞争格局 → 影响投资机会
        "竞争格局": {
            "affects": ["投资机会", "发展趋势"],
            "data_points": ["市场份额", "竞争策略", "主要竞争者", "竞争强度"],
            "check_type": "ratio_valid",
        },
        # 政策环境 → 影响发展趋势和投资机会
        "政策环境": {
            "affects": ["发展趋势", "投资机会", "市场规模"],
            "data_points": ["政策法规", "监管要求", "政策支持力度"],
            "check_type": "trend_consistent",
        },
        # 技术趋势 → 影响发展趋势和竞争格局
        "技术趋势": {
            "affects": ["发展趋势", "竞争格局", "投资机会"],
            "data_points": ["关键技术", "研发投入", "技术成熟度"],
            "check_type": "trend_consistent",
        },
        # 发展趋势 → 影响投资机会
        "发展趋势": {
            "affects": ["投资机会"],
            "data_points": ["增长预测", "市场前景", "风险因素"],
            "check_type": "value_match",
        },
        # 消费者行为 → 影响市场规模和竞争格局
        "消费者行为": {
            "affects": ["市场规模", "竞争格局", "发展趋势"],
            "data_points": ["消费偏好", "购买行为", "用户画像"],
            "check_type": "trend_consistent",
        },
        # 供应链分析 → 影响市场规模和竞争格局
        "供应链分析": {
            "affects": ["市场规模", "竞争格局"],
            "data_points": ["供应链结构", "供应商分布", "成本结构"],
            "check_type": "value_match",
        },
    }
    
    # 反向依赖 (自动计算)
    _reverse_dependencies: Dict[str, List[str]] = {}
    
    # 最大级联深度 (防止循环依赖)
    MAX_CASCADE_DEPTH = 3
    
    def __init__(self):
        """初始化级联更新分析器"""
        self._build_reverse_dependencies()
        logger.info(
            f"[CascadeAnalyzer] Initialized with {len(self.SECTION_DEPENDENCIES)} dependency rules"
        )
    
    def _build_reverse_dependencies(self) -> None:
        """构建反向依赖关系"""
        self._reverse_dependencies = {}
        
        for source, deps in self.SECTION_DEPENDENCIES.items():
            for target in deps.get("affects", []):
                if target not in self._reverse_dependencies:
                    self._reverse_dependencies[target] = []
                self._reverse_dependencies[target].append(source)
    
    def analyze_cascade_impact(
        self,
        target_sections: List[str],
        all_sections: List[str],
    ) -> CascadeImpact:
        """
        分析修订目标章节的级联影响
        
        Args:
            target_sections: 被修订的章节列表
            all_sections: 报告中所有章节列表
            
        Returns:
            CascadeImpact: 级联影响分析结果
        """
        if not target_sections or not all_sections:
            return CascadeImpact()
        
        logger.debug(
            f"[CascadeAnalyzer] Analyzing cascade impact for: {target_sections}"
        )
        
        affected: Set[str] = set()
        consistency_checks: List[ConsistencyCheck] = []
        suggested_updates: List[Dict[str, Any]] = []
        
        # BFS 遍历依赖关系
        visited: Set[str] = set()
        queue: List[tuple] = [(s, 0) for s in target_sections]  # (section, depth)
        
        while queue:
            current, depth = queue.pop(0)
            
            if current in visited or depth > self.MAX_CASCADE_DEPTH:
                continue
            
            visited.add(current)
            
            # 获取依赖关系
            deps = self.SECTION_DEPENDENCIES.get(current, {})
            affects = deps.get("affects", [])
            data_points = deps.get("data_points", [])
            check_type = deps.get("check_type", "value_match")
            
            # 收集受影响的章节
            for affected_section in affects:
                if affected_section in all_sections and affected_section not in target_sections:
                    affected.add(affected_section)
                    
                    # 添加数据一致性检查
                    consistency_checks.append(ConsistencyCheck(
                        source=current,
                        target=affected_section,
                        data_points=data_points,
                        check_type=check_type,
                        description=f"修订'{current}'后，需检查'{affected_section}'中的{', '.join(data_points)}是否一致",
                    ))
                    
                    # 添加到队列继续遍历
                    if affected_section not in visited:
                        queue.append((affected_section, depth + 1))
        
        # 生成更新建议
        suggested_updates = self._generate_update_suggestions(
            target_sections, list(affected), consistency_checks
        )
        
        # 计算风险等级
        risk_level = self._calculate_risk_level(len(affected), len(consistency_checks))
        
        result = CascadeImpact(
            affected_sections=list(affected),
            data_consistency_checks=consistency_checks,
            suggested_updates=suggested_updates,
            cascade_depth=max(len(visited), 1) if visited else 0,
            risk_level=risk_level,
        )
        
        logger.info(
            f"[CascadeAnalyzer] Impact: {len(affected)} sections affected, "
            f"{len(consistency_checks)} checks, risk={risk_level}"
        )
        
        return result
    
    def _generate_update_suggestions(
        self,
        target_sections: List[str],
        affected_sections: List[str],
        consistency_checks: List[ConsistencyCheck],
    ) -> List[Dict[str, Any]]:
        """生成级联更新建议"""
        suggestions = []
        
        for check in consistency_checks:
            suggestions.append({
                "type": "verify_consistency",
                "target_section": check.target,
                "action": f"检查并更新 {', '.join(check.data_points)} 相关数据",
                "priority": "high" if check.check_type == "value_match" else "medium",
                "auto_fixable": check.check_type in ["value_match", "ratio_valid"],
            })
        
        return suggestions
    
    def _calculate_risk_level(
        self,
        affected_count: int,
        check_count: int,
    ) -> str:
        """计算风险等级"""
        if affected_count >= 3 or check_count >= 5:
            return "high"
        elif affected_count >= 2 or check_count >= 3:
            return "medium"
        else:
            return "low"
    
    def get_dependencies(self, section: str) -> Optional[Dict[str, Any]]:
        """获取指定章节的依赖关系"""
        return self.SECTION_DEPENDENCIES.get(section)
    
    def get_reverse_dependencies(self, section: str) -> List[str]:
        """
        获取反向依赖 (哪些章节会影响该章节)
        
        Args:
            section: 目标章节
            
        Returns:
            List[str]: 会影响该章节的源章节列表
        """
        return self._reverse_dependencies.get(section, [])
    
    def add_dependency_rule(
        self,
        section: str,
        affects: List[str],
        data_points: List[str],
        check_type: str = "value_match",
    ) -> None:
        """
        添加自定义依赖规则
        
        Args:
            section: 源章节
            affects: 受影响的章节列表
            data_points: 相关数据点
            check_type: 检查类型
        """
        self.SECTION_DEPENDENCIES[section] = {
            "affects": affects,
            "data_points": data_points,
            "check_type": check_type,
        }
        
        # 重建反向依赖
        self._build_reverse_dependencies()
        
        logger.info(
            f"[CascadeAnalyzer] Added dependency rule: {section} → {affects}"
        )
    
    def validate_consistency(
        self,
        section_data: Dict[str, Any],
        check: ConsistencyCheck,
    ) -> Dict[str, Any]:
        """
        验证数据一致性
        
        Args:
            section_data: 章节数据
            check: 一致性检查项
            
        Returns:
            Dict: 验证结果 {"valid": bool, "issues": List[str]}
        """
        issues = []
        
        # 简单验证：检查数据点是否存在
        for data_point in check.data_points:
            if data_point not in section_data:
                issues.append(f"缺少数据点: {data_point}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "check": check.to_dict(),
        }
